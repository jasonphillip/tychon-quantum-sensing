"""Synthetic conditional-cavity readout, portable CPU checks, optional CUDA-Q.

All solver times are microseconds. Hamiltonian coefficients are rad/us.
The noisy records are classical receiver simulations, not quantum trajectories.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent


def load_config(path=ROOT / "config.json"):
    c = json.loads(Path(path).read_text())
    if c["schema"] != "synthetic_dispersive_readout_v1":
        raise ValueError("unsupported schema")
    if c["samples"] < 2 or c["sample_interval_us"] <= 0 or c["kappa_rad_per_us"] <= 0:
        raise ValueError("invalid physical domain")
    if not 0 <= c["noise_ar1"] < 1:
        raise ValueError("AR1 correlation must be in [0, 1)")
    if any(v < 2 for v in c["devices"].values()):
        raise ValueError("each split requires at least two devices")
    return c


def time_axis(c):
    return np.arange(c["samples"]) * c["sample_interval_us"]


def analytic_alpha(t, delta, drive, kappa):
    """Exact coherent amplitude for constant drive, vacuum initial state."""
    t = np.asarray(t, dtype=float)
    if not (np.isfinite(delta) and np.isfinite(drive) and np.isfinite(kappa)) or kappa <= 0:
        raise ValueError("finite parameters and positive damping required")
    if np.any(t < 0) or not np.all(np.isfinite(t)):
        raise ValueError("finite nonnegative time required")
    rate = kappa / 2 + 1j * delta
    return -1j * drive * (-np.expm1(-rate * t)) / rate


def density_evolve(t, delta, drive, kappa, levels, max_step):
    """Independent truncated Fock-basis Lindblad RK4. No state repair/clipping."""
    t = np.asarray(t)
    if t[0] != 0 or np.any(np.diff(t) <= 0) or levels < 2 or max_step <= 0:
        raise ValueError("invalid density evolution grid")
    a = np.diag(np.sqrt(np.arange(1, levels)), 1).astype(complex)
    n = a.conj().T @ a
    h = delta * n + drive * (a + a.conj().T)
    rho = np.zeros((levels, levels), dtype=complex)
    rho[0, 0] = 1
    def rhs(r):
        return -1j * (h @ r - r @ h) + kappa * (a @ r @ a.conj().T - (n @ r + r @ n) / 2)
    states = [rho.copy()]
    for interval in np.diff(t):
        steps = math.ceil(interval / max_step)
        dt = interval / steps
        for _ in range(steps):
            k1 = rhs(rho)
            k2 = rhs(rho + dt * k1 / 2)
            k3 = rhs(rho + dt * k2 / 2)
            k4 = rhs(rho + dt * k3)
            rho = rho + dt * (k1 + 2*k2 + 2*k3 + k4) / 6
        states.append(rho.copy())
    states = np.array(states)
    return {
        "alpha": np.einsum("ij,tji->t", a, states),
        "number": np.einsum("ij,tji->t", n, states).real,
        "trace_error": float(np.max(abs(np.trace(states, axis1=1, axis2=2)-1))),
        "hermiticity_error": float(np.max(abs(states-states.conj().transpose(0, 2, 1)))),
        "minimum_eigenvalue": float(np.min(np.linalg.eigvalsh(states))),
        "boundary_population": float(np.max(states[:, -1, -1].real)),
    }


def reference_cases(c):
    # Named physical checks fixed independently of any dataset realization.
    return [(name, c["detuning_rad_per_us"] + z*c["chi_rad_per_us"] + shift,
             c["drive_rad_per_us"]*scale)
            for name, z, shift, scale in (
                ("ground_nominal", -1, 0, 1), ("excited_nominal", 1, 0, 1),
                ("ground_drift", -1, c["stress"]["detuning_add_rad_per_us"], 1.1),
                ("excited_drift", 1, c["stress"]["detuning_add_rad_per_us"], 1.1))]


def verify_physics(c):
    rows, passed = [], True
    tol = c["acceptance"]
    for name, delta, drive in reference_cases(c):
        t = time_axis(c)
        ref = analytic_alpha(t, delta, drive, c["kappa_rad_per_us"])
        a = density_evolve(t, delta, drive, c["kappa_rad_per_us"], c["fock_levels"], c["rk4_max_step_us"])
        b = density_evolve(t, delta, drive, c["kappa_rad_per_us"], c["reference_fock_levels"], c["rk4_max_step_us"])
        half = density_evolve(t, delta, drive, c["kappa_rad_per_us"], c["fock_levels"], c["rk4_max_step_us"]/2)
        row = {"case": name, "delta_rad_per_us": delta, "drive_rad_per_us": drive,
               "alpha_max_abs_error": float(np.max(abs(a["alpha"]-ref))),
               "truncation_difference": float(np.max(abs(a["alpha"]-b["alpha"]))),
               "step_halving_difference": float(np.max(abs(a["alpha"]-half["alpha"]))),
               "number_max_abs_error": float(np.max(abs(a["number"]-abs(ref)**2))),
               "peak_mean_photons": float(np.max(abs(ref)**2)),
               **{key: a[key] for key in ("trace_error", "hermiticity_error", "minimum_eigenvalue", "boundary_population")}}
        gates = [row["alpha_max_abs_error"] <= tol["cpu_alpha_max_abs_error"],
                 row["truncation_difference"] <= tol["truncation_alpha_max_abs_difference"],
                 row["step_halving_difference"] <= tol["step_halving_alpha_max_abs_difference"],
                 row["trace_error"] <= tol["trace_max_abs_error"],
                 row["hermiticity_error"] <= tol["hermiticity_max_abs_error"],
                 row["minimum_eigenvalue"] >= tol["density_min_eigenvalue"],
                 row["boundary_population"] <= tol["boundary_population_max"]]
        row["passed"] = all(gates)
        passed &= row["passed"]
        rows.append(row)
    return {"passed": passed, "cases": rows}


def generate(c):
    """Separate physical groups per split; stress reuses test groups, not noise."""
    streams = np.random.SeedSequence(c["seed"]).spawn(5)
    rng_p, rng_n, rng_stress = [np.random.default_rng(s) for s in streams[:3]]
    rows, labels, splits, ids, params = [], [], [], [], []
    t, did = time_axis(c), 0
    for split, count in c["devices"].items():
        for _ in range(count):
            p = {
                "device_id": did, "split": split,
                "delta": c["detuning_rad_per_us"] + rng_p.normal(0, c["detuning_sigma_rad_per_us"]),
                "drive": c["drive_rad_per_us"] * (1 + rng_p.normal(0, c["drive_relative_sigma"])),
                "phase": rng_p.normal(0, c["phase_sigma_rad"]),
                "gain": 1 + rng_p.normal(0, c["gain_relative_sigma"]),
                "offset_i": rng_p.normal(0, c["offset_sigma"]),
                "offset_q": rng_p.normal(0, c["offset_sigma"]),
            }
            params.append(p)
            for stress in ([False, True] if split == "test" else [False]):
                d = p["delta"] + (c["stress"]["detuning_add_rad_per_us"] if stress else 0)
                phase = p["phase"] + (c["stress"]["phase_add_rad"] if stress else 0)
                gain = p["gain"] * (c["stress"]["gain_factor"] if stress else 1)
                sigma = c["noise_sigma_per_quadrature"] * (c["stress"]["noise_factor"] if stress else 1)
                rng = rng_stress if stress else rng_n
                for label in (0, 1):
                    alpha = analytic_alpha(t, d+(2*label-1)*c["chi_rad_per_us"], p["drive"], c["kappa_rad_per_us"])
                    signal = gain*np.exp(1j*phase)*alpha + p["offset_i"] + 1j*p["offset_q"]
                    for _ in range(c["repeats_per_class_per_device"]):
                        noise = rng.normal(size=(len(t), 2))
                        phi = c["noise_ar1"]
                        for k in range(1, len(t)):
                            noise[k] = phi*noise[k-1]+np.sqrt(1-phi*phi)*noise[k]
                        record = np.column_stack((signal.real, signal.imag))+sigma*noise
                        rows.append(record.reshape(-1))
                        labels.append(label)
                        splits.append("stress" if stress else split)
                        ids.append(did)
            did += 1
    return {"x": np.array(rows), "y": np.array(labels, dtype=np.uint8),
            "split": np.array(splits), "device_id": np.array(ids), "time_us": t}, params


def train_models(x, y, c):
    m0, m1 = x[y == 0].mean(0), x[y == 1].mean(0)
    center, delta = (m0+m1)/2, m1-m0
    residual = x-np.where(y[:, None] == 0, m0, m1)
    covariance = residual.T @ residual/(len(y)-2)
    shrink = c["lda_covariance_shrinkage"]
    covariance = (1-shrink)*covariance+shrink*np.trace(covariance)/len(delta)*np.eye(len(delta))
    full = np.linalg.solve(covariance, delta)
    n = c["samples"]
    b = x.reshape(-1, n, 2).mean(1)
    bm0, bm1 = b[y == 0].mean(0), b[y == 1].mean(0)
    residual_b = b-np.where(y[:, None] == 0, bm0, bm1)
    cb = residual_b.T @ residual_b/(len(y)-2)
    bw = np.linalg.solve(cb, bm1-bm0)
    candidates = [("boxcar", np.tile(bw/n, n)), ("matched_filter", delta), ("lda", full)]
    # Normalize using only training-derived coefficients. Threshold is zero.
    return {name: {"weight": w/max(abs(w)), "bias": -float(w@center)/max(abs(w))}
            for name, w in candidates}


def accuracy(scores, labels):
    return float(np.mean((scores >= 0) == labels))


def quantize_input(x, frac=11):
    if not np.all(np.isfinite(x)):
        raise ValueError("nonfinite receiver input")
    raw = np.rint(x*(1 << frac))
    clipped = np.count_nonzero((raw < -32768) | (raw > 32767))
    return np.clip(raw, -32768, 32767).astype(np.int16), int(clipped)


def quantize_model(model, c):
    q = c["fixed_point"]
    wi = np.rint(model["weight"]*(1 << q["weight_fraction_bits"])).astype(np.int16)
    bias = int(np.rint(model["bias"]*(1 << (q["weight_fraction_bits"]+q["input_fraction_bits"]))))
    bound = sum(abs(int(a))*32768 for a in wi)+abs(bias)
    if bound >= 1 << 63:
        raise OverflowError("accumulator range exceeds int64")
    return wi, bias, bound


def compile_c(out):
    compiler = shutil.which("cc")
    if not compiler:
        raise RuntimeError("a C11 compiler is required for host equivalence")
    suffix = ".dylib" if sys.platform == "darwin" else ".so"
    libpath = out / ("libreadout"+suffix)
    command = [compiler, "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC", str(ROOT/"fixed_readout.c"), "-o", str(libpath)]
    run = subprocess.run(command, check=True, capture_output=True, text=True)
    (out/"compile.json").write_text(json.dumps({"command": command, "stdout": run.stdout, "stderr": run.stderr}, indent=2)+"\n")
    lib = ctypes.CDLL(str(libpath))
    fn = lib.readout_score
    fn.argtypes = [ctypes.POINTER(ctypes.c_int16), ctypes.POINTER(ctypes.c_int16), ctypes.c_uint32, ctypes.c_int64]
    fn.restype = ctypes.c_int64
    return fn


def c_scores(fn, xq, wq, bias):
    ptr = ctypes.POINTER(ctypes.c_int16)
    wq = np.ascontiguousarray(wq, dtype=np.int16)
    return np.array([fn(np.ascontiguousarray(row).ctypes.data_as(ptr), wq.ctypes.data_as(ptr), len(wq), bias) for row in xq], dtype=np.int64)


def benchmark(c, out):
    start = time.perf_counter()
    physics = verify_physics(c)
    (out/"physics.json").write_text(json.dumps(physics, indent=2)+"\n")
    if not physics["passed"]:
        raise RuntimeError("physical correctness gate failed; no data evaluation performed")
    data, params = generate(c)
    np.savez_compressed(out/"synthetic_data.npz", **data)
    (out/"physical_groups.json").write_text(json.dumps(params, indent=2)+"\n")
    train = data["split"] == "train"
    val = data["split"] == "validation"
    models = train_models(data["x"][train], data["y"][train], c)
    validation = {name: accuracy(data["x"][val]@m["weight"]+m["bias"], data["y"][val]) for name, m in models.items()}
    selected = max(models, key=lambda k: validation[k])
    model = models[selected]
    wq, bias, bound = quantize_model(model, c)
    xq, clipped = quantize_input(data["x"], c["fixed_point"]["input_fraction_bits"])
    scores_q = xq.astype(np.int64)@wq.astype(np.int64)+bias
    fn = compile_c(out)
    scores_c = c_scores(fn, xq, wq, bias)
    edge = np.stack([np.full(len(wq), -32768, dtype=np.int16), np.full(len(wq), 32767, dtype=np.int16),
                     np.where(wq >= 0, 32767, -32768).astype(np.int16), np.where(wq >= 0, -32768, 32767).astype(np.int16)])
    edge_ref = edge.astype(np.int64)@wq.astype(np.int64)+bias
    parity = bool(np.array_equal(scores_q, scores_c) and np.array_equal(edge_ref, c_scores(fn, edge, wq, bias)))
    scale = 1 << (c["fixed_point"]["input_fraction_bits"]+c["fixed_point"]["weight_fraction_bits"])
    scores_float = data["x"]@model["weight"]+model["bias"]
    partition = {}
    for split in ("train", "validation", "test", "stress"):
        mask = data["split"] == split
        partition[split] = {"records": int(mask.sum()), "devices": int(len(np.unique(data["device_id"][mask]))),
                            "models": {name: accuracy(data["x"][mask]@m["weight"]+m["bias"], data["y"][mask]) for name, m in models.items()},
                            "fixed_accuracy": accuracy(scores_q[mask], data["y"][mask]),
                            "float_fixed_disagreement": float(np.mean((scores_q[mask] >= 0) != (scores_float[mask] >= 0)))}
    gate = bool(parity and clipped == 0 and partition["test"]["fixed_accuracy"] >= c["acceptance"]["nominal_test_accuracy_min"] and
                partition["test"]["float_fixed_disagreement"] <= c["acceptance"]["fixed_point_max_float_disagreement_fraction"])
    model_json = {"selected": selected, "features": "I0,Q0,I1,Q1,...,I63,Q63", "weight_float": model["weight"].tolist(),
                  "bias_float": model["bias"], "weight_int16": wq.tolist(), "bias_int64": bias,
                  "fixed_point": c["fixed_point"], "decision": "score >= 0 means class 1"}
    (out/"model.json").write_text(json.dumps(model_json, indent=2)+"\n")
    np.savez_compressed(out/"fixed_test_vectors.npz", x_int16=xq, score_int64=scores_q, label=data["y"], split=data["split"])
    metrics = {"passed": gate, "scope": "synthetic receiver data and host C inference; no FPGA execution",
               "selected_model": selected, "validation_selection": validation, "partitions": partition,
               "physics": physics, "host_c_bit_exact": parity, "clipped_input_values": clipped,
               "max_score_quantization_error": float(np.max(abs(scores_q/scale-scores_float))),
               "accumulator_worst_case_abs_bound": bound, "signed_accumulator_bits_sufficient": bound.bit_length()+1,
               "macs_per_record": len(wq), "coefficient_bytes": 2*len(wq)+8,
               "input_bytes_per_record": 2*len(wq), "elapsed_s": time.perf_counter()-start,
               "versions": {"python": platform.python_version(), "numpy": np.__version__, "platform": platform.platform()}}
    (out/"metrics.json").write_text(json.dumps(metrics, indent=2)+"\n")
    return metrics


def gpu_check(c, out):
    """Real CUDA-Q Dynamics only. Absence/failure never falls back to CPU."""
    import cudaq
    import cupy as cp
    import importlib.metadata
    from cudaq import operators, Schedule, RungeKuttaIntegrator
    cudaq.set_target("dynamics")
    levels = c["fock_levels"]
    a = np.diag(np.sqrt(np.arange(1, levels)), 1).astype(complex)
    n = a.conj().T@a
    # Explicit matrices avoid basis-convention ambiguity and boson API variation.
    # Custom operator API is public. The environment must provide it unchanged.
    def register(name, matrix):
        operators.custom.define(name, [levels], lambda: matrix)
        return operators.custom.instantiate(name, [0])
    aop = register("readout_annihilation", a)
    nop = register("readout_number", n)
    xop = register("readout_real_alpha", (a+a.conj().T)/2)
    yop = register("readout_imag_alpha", (a-a.conj().T)/(2j))
    driveop = register("readout_drive", a+a.conj().T)
    identity = register("readout_identity", np.eye(levels, dtype=complex))
    rho = cp.zeros((levels, levels), dtype=cp.complex128)
    rho[0, 0] = 1
    state = cudaq.State.from_data(rho)
    t, rows, outputs = time_axis(c), [], []
    start = time.perf_counter()
    for name, delta, drive in reference_cases(c):
        result = cudaq.evolve(delta*nop+drive*driveop, {0: levels}, Schedule(t, ["t_us"]), state,
                              observables=[xop, yop, nop, identity], collapse_operators=[np.sqrt(c["kappa_rad_per_us"])*aop],
                              store_intermediate_results=cudaq.IntermediateResultSave.EXPECTATION_VALUE,
                              integrator=RungeKuttaIntegrator(order=4, max_step_size=c["gpu_max_step_us"]))
        values = np.array([[float(e.expectation()) for e in row] for row in result.expectation_values()])
        if values.shape != (len(t), 4) or not np.all(np.isfinite(values)):
            raise RuntimeError("CUDA-Q observable shape/value failure")
        expected = analytic_alpha(t, delta, drive, c["kappa_rad_per_us"])
        row = {"case": name, "alpha_max_abs_error": float(np.max(abs(values[:, 0]+1j*values[:, 1]-expected))),
               "number_max_abs_error": float(np.max(abs(values[:, 2]-abs(expected)**2))),
               "trace_max_abs_error": float(np.max(abs(values[:, 3]-1)))}
        row["passed"] = (row["alpha_max_abs_error"] <= c["acceptance"]["gpu_alpha_max_abs_error"] and
                         row["number_max_abs_error"] <= c["acceptance"]["gpu_number_max_abs_error"] and
                         row["trace_max_abs_error"] <= c["acceptance"]["gpu_trace_max_abs_error"])
        rows.append(row)
        outputs.append(values)
    np.savez_compressed(out/"cudaq_observables.npz", values=np.array(outputs), time_us=t)
    name = cp.cuda.runtime.getDeviceProperties(cp.cuda.runtime.getDevice())["name"]
    metrics = {"passed": all(r["passed"] for r in rows), "backend": "real CUDA-Q Dynamics", "cases": rows,
               "elapsed_evolution_s": time.perf_counter()-start, "device": name.decode() if isinstance(name, bytes) else name,
               "cudaq": importlib.metadata.version("cuda-quantum-cu13"), "cupy": cp.__version__,
               "python": platform.python_version(), "numpy": np.__version__, "fock_levels": levels,
               "integrator": {"method": "RK4", "max_step_us": c["gpu_max_step_us"]}}
    (out/"metrics.json").write_text(json.dumps(metrics, indent=2)+"\n")
    return metrics


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("cpu", "gpu"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT/"config.json")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    config = load_config(args.config)
    shutil.copy2(args.config, args.output/"config.json")
    provenance = {"utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                  "argv": sys.argv, "mode": args.mode,
                  "sha256": {str(p.name): hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.config, ROOT/"readout_pilot.py", ROOT/"fixed_readout.c")}}
    (args.output/"provenance.json").write_text(json.dumps(provenance, indent=2)+"\n")
    try:
        result = benchmark(config, args.output) if args.mode == "cpu" else gpu_check(config, args.output)
    except Exception as exc:
        (args.output/"failure.json").write_text(json.dumps({"type": type(exc).__name__, "message": str(exc)}, indent=2)+"\n")
        raise
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
