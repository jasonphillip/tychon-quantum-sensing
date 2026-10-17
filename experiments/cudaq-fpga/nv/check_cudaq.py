"""Optional real CUDA-Q Dynamics check, executed only by the coordinator."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
import time
from pathlib import Path
import numpy as np
from nv_model import ROOT, config, hamiltonian, sequence_density, RHO0, P0


def run(output):
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    cfg = config()
    started = time.perf_counter()
    report = {"status":"started", "synthetic_only":True,
              "config_sha256":hashlib.sha256((ROOT/"config.json").read_bytes()).hexdigest(),
              "source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "model_source_sha256":hashlib.sha256((ROOT/"nv_model.py").read_bytes()).hexdigest(),
              "python":sys.version,"numpy":np.__version__,"platform":platform.platform(),
              "step_us":cfg["cudaq_rk4_max_step_us"],"cases":[]}
    try:
        import cudaq
        import cupy as cp
        from cudaq import operators, Schedule, RungeKuttaIntegrator
        if cp.cuda.runtime.getDeviceCount() < 1:
            raise RuntimeError("No NVIDIA device; CPU substitution is forbidden")
        props = cp.cuda.runtime.getDeviceProperties(0)
        report["gpu"] = str(props.get("name"))
        report["cupy"] = cp.__version__
        report["cudaq"] = importlib.metadata.version("cuda-quantum-cu13")
        cudaq.set_target("dynamics")
        counter = 0
        def evolve_gpu(h,state,duration):
            nonlocal counter
            if duration == 0:
                return state
            name = "nv_constant_h_" + str(counter)
            counter += 1
            matrix = np.asarray(h,dtype=np.complex128)
            def make_matrix(dimension):
                if dimension != 4:
                    raise ValueError("expected four-dimensional system")
                return matrix
            operators.define(name,[4],make_matrix)
            op = operators.instantiate(name,[0])
            result = cudaq.evolve(op,{0:4},Schedule([0.,duration],["t"]),state,
                        collapse_operators=[],observables=[],
                        store_intermediate_results=False,
                        integrator=RungeKuttaIntegrator(order=4,max_step_size=cfg["cudaq_rk4_max_step_us"]))
            value = result.final_state
            return value() if callable(value) else value
        cases = [(-.75,0.,0.),(-.75,4.,np.pi/2),(.75,4.,0.),(.75,.13,np.pi),
                 (0.,4.,3*np.pi/2),(0.,0.,np.pi/2),(.123,2.17,.73),(-.213,.318,3*np.pi/2)]
        for detuning,delay,phase in cases:
            model = cfg["model"]
            pulse = 1/(4*model["rabi_mhz"])
            state = cudaq.State.from_data(cp.asarray(RHO0,dtype=cp.complex128))
            state = evolve_gpu(hamiltonian(detuning,model,np.pi/2,True),state,pulse)
            state = evolve_gpu(hamiltonian(detuning,model),state,delay)
            state = evolve_gpu(hamiltonian(detuning,model,phase-np.pi/2,True),state,pulse)
            actual = np.asarray(state.to_numpy()).reshape((4,4))
            expected = sequence_density(detuning,delay,phase,model)
            prob_error = float(abs(np.trace(P0@(actual-expected))))
            matrix_error = float(np.max(np.abs(actual-expected)))
            trace_error = float(abs(np.trace(actual)-1))
            hermitian_error = float(np.max(np.abs(actual-actual.conj().T)))
            minimum_eigenvalue = float(np.linalg.eigvalsh((actual+actual.conj().T)/2).min())
            row = {"detuning_mhz":detuning,"delay_us":delay,"phase_rad":phase,
                   "probability_error":prob_error,"density_max_error":matrix_error,
                   "trace_error":trace_error,"hermitian_error":hermitian_error,
                   "minimum_eigenvalue":minimum_eigenvalue}
            report["cases"].append(row)
            if not (prob_error <= cfg["gates"]["cudaq_probability_atol"]
                    and matrix_error <= cfg["gates"]["cudaq_density_atol"]
                    and trace_error <= cfg["gates"]["cudaq_density_atol"]
                    and hermitian_error <= cfg["gates"]["cudaq_density_atol"]
                    and minimum_eigenvalue >= -cfg["gates"]["cudaq_density_atol"]):
                raise AssertionError("CUDA-Q physicality or numerical gate failed: "+str(row))
        report["status"] = "passed"
        report["max_probability_error"] = max(c["probability_error"] for c in report["cases"])
        report["max_density_error"] = max(c["density_max_error"] for c in report["cases"])
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = repr(exc)
        raise
    finally:
        report["wall_seconds"] = time.perf_counter()-started
        output.write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report,indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    run(args.output.resolve())
