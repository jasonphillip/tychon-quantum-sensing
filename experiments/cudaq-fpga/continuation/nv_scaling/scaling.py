"""Matched four-level CPU/CUDA-Q evolution and immutable FPGA interface."""
from __future__ import annotations
import hashlib
import time
from pathlib import Path
import numpy as np
from nv_model import hamiltonian, RHO0, P0, quantize, integer_match, sample_counts, count_features

ROOT = Path(__file__).resolve().parent
ROM_SHA = 'b4c8515c0c4842d613a58fc7a23e528c956343bf86ba515cda5715ca57110f8f'


def arrays(cfg):
    rng = np.random.default_rng(cfg['parameter_seed'])
    detuning = rng.uniform(*cfg['detuning_range_mhz'], cfg['configurations'])
    return detuning, np.linspace(0, cfg['maximum_delay_us'], cfg['delay_points']), np.array(cfg['phases_rad'])


def unitary_batch(h, duration):
    values, vectors = np.linalg.eigh(h)
    phase = np.exp(-1j * values * np.asarray(duration)[..., None])
    return (vectors * phase[..., None, :]) @ vectors.conj().swapaxes(-1, -2)


def cpu_density(cfg, detuning):
    """Specialized batched Hermitian solver, reusing free eigenvectors over delays."""
    _, delays, phases = arrays(cfg)
    model = cfg['model']
    pulse = 1 / (4 * model['rabi_mhz'])
    prep_h = np.stack([hamiltonian(d, model, np.pi/2, True) for d in detuning])
    prep_u = unitary_batch(prep_h, pulse)
    prep = prep_u @ RHO0 @ prep_u.conj().swapaxes(-1, -2)
    free_h = np.stack([hamiltonian(d, model) for d in detuning])
    e, v = np.linalg.eigh(free_h)
    u = (v[:, None, :, :] * np.exp(-1j * e[:, None, :] * delays[None, :, None])[:, :, None, :]) @ v.conj().swapaxes(-1, -2)[:, None]
    free = u @ prep[:, None] @ u.conj().swapaxes(-1, -2)
    read_h = np.stack([[hamiltonian(d, model, p-np.pi/2, True) for p in phases] for d in detuning])
    read_u = unitary_batch(read_h, pulse)
    return read_u[:, :, None] @ free[:, None] @ read_u.conj().swapaxes(-1, -2)[:, :, None]


def probabilities(rho):
    return np.trace(rho[..., :2, :2], axis1=-2, axis2=-1).real


def physical_metrics(rho):
    herm = rho.conj().swapaxes(-1, -2)
    return {'trace_error': float(np.max(np.abs(np.trace(rho, axis1=-2, axis2=-1)-1))),
            'hermiticity_error': float(np.max(np.abs(rho-herm))),
            'minimum_eigenvalue': float(np.linalg.eigvalsh((rho+herm)/2).min()),
            'purity_error': float(np.max(np.abs(np.trace(rho @ rho, axis1=-2, axis2=-1)-.5))),
            'probability_min': float(probabilities(rho).min()),
            'probability_max': float(probabilities(rho).max())}


def physical_pass(metrics, gates):
    return bool(metrics['trace_error'] <= gates['trace_atol']
                and metrics['hermiticity_error'] <= gates['hermiticity_atol']
                and metrics['minimum_eigenvalue'] >= gates['minimum_eigenvalue']
                and metrics['purity_error'] <= gates['purity_atol']
                and metrics['probability_min'] >= -gates['probability_atol']
                and metrics['probability_max'] <= 1+gates['probability_atol'])


class CudaqEngine:
    """All three quantum segments use CUDA-Q Dynamics. No CPU evolution fallback."""
    def __init__(self, cfg):
        import inspect
        import importlib.metadata
        import cudaq
        import cupy as cp
        self.cudaq, self.cp, self.cfg = cudaq, cp, cfg
        if cp.cuda.runtime.getDeviceCount() < 1:
            raise RuntimeError('NVIDIA device required; no fallback')
        if 'max_batch_size' not in inspect.signature(cudaq.evolve).parameters:
            raise RuntimeError('Installed CUDA-Q lacks required batching API')
        cudaq.set_target('dynamics')
        self.info = {'cudaq': importlib.metadata.version('cuda-quantum-cu13'),
                     'cupy': cp.__version__, 'gpu': str(cp.cuda.runtime.getDeviceProperties(0)['name']),
                     'evolve_signature': str(inspect.signature(cudaq.evolve))}
        self.ops = {}
        self.counter = 0
        self.checkpoints = []
        self.sync()
        self.baseline_free = cp.cuda.runtime.memGetInfo()[0]
        self.memory_checkpoint('initialized')

    def sync(self):
        self.cp.cuda.runtime.deviceSynchronize()

    def memory_checkpoint(self, label):
        free, total = self.cp.cuda.runtime.memGetInfo()
        pool = self.cp.get_default_memory_pool()
        self.checkpoints.append({'label': label, 'device_free_bytes': int(free),
                                 'device_total_bytes': int(total), 'cupy_pool_used_bytes': int(pool.used_bytes()),
                                 'cupy_pool_reserved_bytes': int(pool.total_bytes())})
        if self.baseline_free-free > self.cfg['limits']['gpu_incremental_gib']*1024**3:
            raise MemoryError('Observed device free-memory decrement exceeds registered limit')

    def operator(self, matrix):
        from cudaq import operators
        matrix = np.asarray(matrix, dtype=np.complex128)
        key = matrix.tobytes()
        if key not in self.ops:
            name = f'nv_scaling_h_{self.counter}'
            self.counter += 1
            def make_matrix(dimension):
                if dimension != 4:
                    raise ValueError('Expected four-level Hamiltonian')
                return matrix
            operators.define(name, [4], make_matrix)
            self.ops[key] = operators.instantiate(name, [0])
        return self.ops[key]

    def evolve(self, matrices, states, max_physical_duration):
        from cudaq import Schedule, RungeKuttaIntegrator
        # s=t/duration; H_scaled=duration*H. Every sequence segment spans s in [0,1].
        step = self.cfg['rk4_max_step_us']/max_physical_duration
        ops = [self.operator(m) for m in matrices]
        result = self.cudaq.evolve(ops, {0:4}, Schedule([0., 1.], ['t']), states,
                    collapse_operators=[], observables=[], store_intermediate_results=False,
                    integrator=RungeKuttaIntegrator(order=4, max_step_size=step),
                    max_batch_size=self.cfg['max_batch_size'])
        self.sync()
        states_out = []
        for item in result:
            state = item.final_state
            states_out.append(state() if callable(state) else state)
        if len(states_out) != len(matrices):
            raise RuntimeError('CUDA-Q batch result length mismatch')
        return states_out

    def density(self, detuning):
        cfg = self.cfg
        _, delays, phases = arrays(cfg)
        model = cfg['model']
        pulse = 1/(4*model['rabi_mhz'])
        output = []
        timings = dict(initial_state_upload_seconds=0., preparation_seconds=0.,
                       free_evolution_seconds=0., readout_seconds=0., final_download_seconds=0.)
        for start in range(0, len(detuning), cfg['configurations_per_chunk']):
            ds = detuning[start:start+cfg['configurations_per_chunk']]
            t = time.perf_counter()
            initial = [self.cudaq.State.from_data(self.cp.asarray(RHO0, dtype=self.cp.complex128)) for _ in ds]
            self.sync()
            timings['initial_state_upload_seconds'] += time.perf_counter()-t
            t = time.perf_counter()
            prep = self.evolve([pulse*hamiltonian(d, model, np.pi/2, True) for d in ds], initial, pulse)
            timings['preparation_seconds'] += time.perf_counter()-t
            t = time.perf_counter()
            free = self.evolve([delay*hamiltonian(d, model) for d in ds for delay in delays],
                               [state for state in prep for _ in delays], cfg['maximum_delay_us'])
            timings['free_evolution_seconds'] += time.perf_counter()-t
            t = time.perf_counter()
            # Identical ordering throughout: configuration, phase, delay.
            final = self.evolve([pulse*hamiltonian(d, model, phase-np.pi/2, True)
                                for d in ds for phase in phases for _ in delays],
                               [free[i*len(delays)+j] for i in range(len(ds)) for _ in phases for j in range(len(delays))], pulse)
            timings['readout_seconds'] += time.perf_counter()-t
            self.memory_checkpoint(f'chunk_{start}_before_download')
            t = time.perf_counter()
            block = np.stack([np.asarray(s.to_numpy()).reshape(4,4) for s in final])
            self.sync()
            output.append(block.reshape(len(ds),len(phases),len(delays),4,4))
            timings['final_download_seconds'] += time.perf_counter()-t
            self.memory_checkpoint(f'chunk_{start}_after_download')
        return np.concatenate(output), timings


def detector_and_pack(cfg, p):
    """Classical CPU projection/Poisson sampler; no claim of GPU detector generation."""
    binary = (ROOT/'frozen/templates_i16le.bin').read_bytes()
    if hashlib.sha256(binary).hexdigest() != ROM_SHA:
        raise ValueError('Frozen FPGA ROM hash mismatch')
    rom = np.frombuffer(binary, dtype='<i2').reshape(121,128)
    rng = np.random.default_rng(cfg['noise_seed'])
    inputs, indices, scores, cases, counts_all = [], [], [], [], []
    clipping = 0
    for config_id, probability in enumerate(p):
        for shots in cfg['shots_per_point']:
            detector = cfg | {'repetitions':shots}
            for replicate in range(cfg['noise_realizations']):
                counts = sample_counts(probability, detector, rng)
                q, clipped = quantize(count_features(counts,detector))
                index, score = integer_match(q,rom)
                inputs.append(q); indices.append(index); scores.append(score); counts_all.append(counts)
                clipping += clipped
                cases.append({'id':f'{cfg["split"]}-{config_id:05d}-r{shots}-n{replicate}',
                              'configuration':config_id,'shots_per_point':shots,'replicate':replicate,
                              'clipped_features':clipped})
    return (np.array(inputs,dtype='<i2'), np.array(indices,dtype='<u2'),np.array(scores,dtype='<u8'),
            np.array(counts_all,dtype=np.int32), cases, clipping)
