"""Generate every quantum output with one selected backend, then sample on CPU."""
import time
PROGRAM_START = time.perf_counter()
import argparse
import hashlib
import json
import platform
import resource
import sys
from pathlib import Path
import numpy as np
from scaling import (ROOT, arrays, cpu_density, CudaqEngine, probabilities,
                     physical_metrics, physical_pass, detector_and_pack, ROM_SHA)
from nv_model import probability_features, quantize


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rss_bytes():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(value if sys.platform == 'darwin' else value*1024)


def run(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    cfg = json.loads(args.protocol.read_text())
    if cfg['delay_points'] != 64 or len(cfg['phases_rad']) != 4:
        raise ValueError('Frozen FPGA interface requires four phases and 64 delays')
    report = {'status':'started','backend':args.backend,'synthetic_only':True,
              'protocol_sha256':sha(args.protocol),'protocol':cfg,'python':sys.version,
              'numpy':np.__version__,'platform':platform.platform(),
              'source_sha256':{p.name:sha(p) for p in sorted(ROOT.glob('*.py'))},
              'quantum_generation':'CUDA-Q Dynamics GPU' if args.backend=='cudaq' else 'specialized NumPy Hermitian eigensolver CPU',
              'detector_generation':'CPU NumPy binomial projection then conditional Poisson sampling',
              'timing_definition':'Synchronized wall time; evolutions include operator preparation and implicit Hamiltonian uploads. Explicit state uploads/downloads are separate sub-timings. Process elapsed begins at first Python statement, not interpreter startup.',
              'runs':[]}
    try:
        detuning, delays, phases = arrays(cfg)
        initialization_start = time.perf_counter()
        engine = CudaqEngine(cfg) if args.backend=='cudaq' else None
        report['backend_initialization_seconds'] = time.perf_counter()-initialization_start
        if engine: report['cudaq_environment'] = engine.info
        rho = None
        repeat_error = 0.
        for repeat in range(1+cfg['warm_repetitions']):
            t = time.perf_counter()
            if engine:
                actual, parts = engine.density(detuning)
                engine.sync()
            else:
                actual, parts = cpu_density(cfg,detuning), {}
            elapsed = time.perf_counter()-t
            report['runs'].append({'kind':'first_call' if repeat==0 else 'warm',
                                   'repeat':repeat,'quantum_seconds':elapsed,'parts':parts})
            if rho is None:
                rho = actual
                report['first_call_plus_initialization_seconds'] = elapsed+report['backend_initialization_seconds']
            else:
                repeat_error = max(repeat_error,float(np.max(np.abs(rho-actual))))
            if time.perf_counter()-PROGRAM_START > cfg['limits']['seconds']:
                raise TimeoutError('Registered elapsed limit exceeded')
            if rss_bytes() > cfg['limits']['cpu_rss_gib']*1024**3:
                raise MemoryError('Registered CPU process RSS limit exceeded')
        report['repeated_generation_max_density_difference'] = repeat_error
        report['physical_metrics'] = physical_metrics(rho)
        report['quantum_probability_count'] = int(np.prod(rho.shape[:-2]))
        report['independent_configurations'] = len(detuning)
        report['gpu_generated_fraction'] = 1. if engine else 0.
        # Validation is outside all backend timings. No CPU density is used to fill GPU output.
        t = time.perf_counter()
        reference = cpu_density(cfg,detuning)
        p = probabilities(rho)
        p_ref = probabilities(reference)
        report['validation_seconds'] = time.perf_counter()-t
        report['max_probability_error'] = float(np.max(np.abs(p-p_ref)))
        report['max_density_error'] = float(np.max(np.abs(rho-reference)))
        q_gpu = np.array([quantize(probability_features(x))[0] for x in p])
        q_ref = np.array([quantize(probability_features(x))[0] for x in p_ref])
        report['noiseless_max_q14_difference'] = int(np.max(np.abs(q_gpu.astype(np.int32)-q_ref)))
        report['noiseless_q14_exact_fraction'] = float(np.mean(q_gpu==q_ref))
        del reference
        t = time.perf_counter()
        inputs, indices, scores, counts, cases, clipping = detector_and_pack(cfg,p)
        report['cpu_detector_and_integer_reference_seconds'] = time.perf_counter()-t
        report['board_record_count'] = len(inputs)
        report['clipped_feature_count'] = clipping
        report['integer_expected_outputs'] = 'Frozen CPU integer reference; C independent replay validation required separately.'
        report['gates'] = {'physical':physical_pass(report['physical_metrics'],cfg['gates']),
                           'all_probabilities':report['max_probability_error'] <= cfg['gates']['probability_atol'],
                           'all_density_elements':report['max_density_error'] <= cfg['gates']['density_atol'],
                           'q14_max_one_lsb':report['noiseless_max_q14_difference'] <= 1,
                           'repeat_reproducibility':repeat_error <= cfg['gates']['density_atol']}
        t = time.perf_counter()
        np.savez(output/'quantum_dataset.npz',detuning_mhz=detuning,delays_us=delays,
                 phases_rad=phases,density=rho,probabilities=p)
        np.savez(output/'detector_counts.npz',counts=counts)
        pack = output/'board_vectors'
        pack.mkdir()
        for name,data in [('inputs_i16.bin',inputs),('expected_indices_u16.bin',indices),('expected_scores_u64.bin',scores)]:
            (pack/name).write_bytes(data.tobytes())
        manifest = {'schema':'nv_scaling_board_pack_v1','count':len(inputs),'abi':{
                    'input':'128 int16 little endian, I[0:64] followed by Q[0:64], Q14',
                    'output':'uint16 lowest-index argmin and uint64 full squared-distance score',
                    'template_count':121,'rom_sha256':ROM_SHA,'board_executed':False},
                    'files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(pack.glob('*.bin'))},
                    'cases':cases}
        (pack/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        report['output_write_seconds'] = time.perf_counter()-t
        report['artifact_sha256'] = {p.name:sha(p) for p in output.glob('*.npz')}
        if engine:
            report['gpu_memory'] = {'method':'CUDA memGetInfo and CuPy pool at synchronized stage checkpoints; CUDA-Q allocations are not all in the CuPy pool. Device free-memory changes are device-wide and sampled, not an allocation peak or exclusive process usage. Unified host RAM availability is not GPU allocation.',
                'baseline_device_free_bytes':engine.baseline_free,
                'maximum_observed_device_free_decrement_bytes':max(0,max(engine.baseline_free-c['device_free_bytes'] for c in engine.checkpoints)),
                'max_observed_cupy_pool_used_bytes':max(c['cupy_pool_used_bytes'] for c in engine.checkpoints),
                'checkpoints':engine.checkpoints}
        report['status'] = 'passed' if all(report['gates'].values()) else 'failed'
        if report['status'] != 'passed': raise AssertionError('Frozen numerical gates failed')
    except Exception as exc:
        report['status'] = 'failed'
        report['error'] = repr(exc)
        raise
    finally:
        report['process_peak_rss_bytes'] = rss_bytes()
        report['process_elapsed_seconds'] = time.perf_counter()-PROGRAM_START
        (output/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:report.get(k) for k in ['status','backend','quantum_probability_count','board_record_count','max_probability_error','max_density_error','process_elapsed_seconds','error']}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--protocol',type=Path,required=True)
    p.add_argument('--backend',choices=['cpu','cudaq'],required=True)
    p.add_argument('--output',type=Path,required=True)
    run(p.parse_args())
