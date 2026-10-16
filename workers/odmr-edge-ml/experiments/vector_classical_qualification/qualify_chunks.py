"""One registered fixed-case job; no RNG, population, training or subprocess."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from experiments.vector_classical_qualification.access import authorize, source_pins


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--approval-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--phase", choices=("fixtures", "chunk_profile"), required=True)
    parser.add_argument("--variant", choices=("affine", "peaks", "calibrated", "lm"), default="affine")
    parser.add_argument("--dtype", choices=("float32", "float64"), default="float64")
    parser.add_argument("--chunk", choices=(256, 1024, 4096), type=int, default=256)
    args = parser.parse_args()
    gate, context = authorize(args.gate, args.approval_sha256, args.phase)
    signature = {k: getattr(args, k) for k in ("phase", "variant", "dtype", "chunk")}
    if gate.get("execution") != signature:
        raise PermissionError("Execution differs from the root-frozen condition")
    args.out.mkdir(parents=True, exist_ok=False)
    write(args.out / "started.json", {"status": "running", "execution": signature,
          "additive_source_sha256": source_pins(), "approval_sha256": args.approval_sha256,
          "reservation_id": context["central_reservation_id"]})
    if args.phase == "fixtures":
        import unittest
        from experiments.vector_classical_qualification import test_contracts
        with (args.out / "fixtures.txt").open("w") as stream:
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromModule(test_contracts))
        write(args.out / "result.json", {"passed": result.wasSuccessful(),
              "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors)})
        return 0 if result.wasSuccessful() else 2
    # GPU jobs use the existing approved one-process Torch allocator policy.
    import numpy as np
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("Approved CUDA host unavailable")
    available = torch.cuda.get_device_properties(0).total_memory
    torch.cuda.set_per_process_memory_fraction(min(1., 16 * 1024**3 / available), 0)
    from experiments.vector_direct_screen.physics import CFG, Engine
    from experiments.vector_direct_screen.independent import manufactured_parameters
    from experiments.vector_direct_screen.baseline import policy_device as original
    from experiments.vector_classical_qualification.adapter import policy_device, fit_counts
    params = manufactured_parameters()
    reference_counts = Engine().spectrum(params) * CFG["photons_per_bin"]
    engine = Engine("torch", "cuda", args.dtype)
    small = engine.array(reference_counts)
    old = original(engine, small, args.variant)
    new = policy_device(engine, small, args.variant, chunk_size=args.chunk)
    # Roundoff agreement only. These are not field-accuracy or adoption gates.
    tolerance = 1e-8 if args.dtype == "float64" else 1e-3
    differences = {}
    for name in ("accepted", "fallback"):
        if not np.array_equal(engine.numpy(old[name]), engine.numpy(new[name])):
            raise AssertionError("Manufactured flag mismatch: " + name)
    for name in ("parameters", "reduced_deviance"):
        left, right = engine.numpy(old[name]), engine.numpy(new[name])
        if name == "parameters":
            left, right = left / np.asarray(CFG["scales"]), right / np.asarray(CFG["scales"])
        differences[name] = float(np.max(np.abs(left - right)))
        if not np.allclose(left, right, rtol=0., atol=tolerance):
            raise AssertionError("Manufactured numerical mismatch: " + name)
    write(args.out / "equivalence.json", {"passed": True, "tolerance": tolerance,
          "max_abs_differences": differences, "scope": "five fixed cases; roundoff check only"})
    index = np.arange(4096) % len(params)
    host_counts = reference_counts[index]
    setup_start = time.perf_counter()
    resident_counts = engine.array(host_counts)
    engine.affine_calibration()
    engine.sync()
    setup = time.perf_counter() - setup_start
    policy_device(engine, resident_counts, args.variant, chunk_size=args.chunk)
    engine.sync()
    timings = []
    last = None
    for repetition in range(3):
        engine.sync()
        start = time.perf_counter()
        policy_device(engine, resident_counts, args.variant, chunk_size=args.chunk)
        engine.sync()
        resident_time = time.perf_counter() - start
        start = time.perf_counter()
        last = fit_counts(host_counts, backend="torch", device="cuda", dtype=args.dtype,
                          variant=args.variant, chunk_size=args.chunk)
        engine.sync()
        host_time = time.perf_counter() - start
        timing = {"repetition": repetition, "resident_seconds": resident_time,
                  "end_to_end_seconds": host_time, "resident_spectra_per_second": 4096/resident_time,
                  "end_to_end_spectra_per_second": 4096/host_time,
                  "million_spectra_seconds_extrapolated": host_time*1000000/4096}
        timings.append(timing)
        write(args.out / ("timing-"+str(repetition)+".json"), timing)
    np.savez_compressed(args.out / "profile.npz", parameters=params[index], counts=host_counts,
        predictions=last["parameters"], accepted=last["accepted"], fallback=last["fallback"],
        reduced_deviance=last["reduced_deviance"])
    passed = bool(last["accepted"].all() and np.isfinite(last["parameters"]).all()
                  and np.isfinite(last["reduced_deviance"]).all())
    write(args.out / "result.json", {"status": "fixed_case_chunk_qualification_only", "passed": passed,
          "timings": timings, "batch": 4096, "chunk": args.chunk, "dtype": args.dtype,
          "variant": args.variant, "calibration_and_initial_transfer_seconds": setup,
          "warmup_calls": 1, "accepted_count": int(last["accepted"].sum()),
          "fallback_count": int(last["fallback"].sum()), "population_accuracy_evaluated": False})
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
