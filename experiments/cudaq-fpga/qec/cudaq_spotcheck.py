"""Optional real CUDA-Q circuit check; GPU target is explicit, with no fallback.

The CPU benchmark remains the main code-capacity sampler. This small Clifford
circuit cross-check does not establish GPU speedup or circuit-level tolerance.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import random
import sys
import time

import cudaq

from qec_model import HX, HZ, LX, LZ, N, syndrome, tables


def rref(rows):
    rows = list(rows)
    pivots = []
    position = 0
    for q in range(N):
        match = next((i for i in range(position, len(rows)) if (rows[i] >> q) & 1), None)
        if match is None:
            continue
        rows[position], rows[match] = rows[match], rows[position]
        for i in range(len(rows)):
            if i != position and ((rows[i] >> q) & 1):
                rows[i] ^= rows[position]
        pivots.append(q)
        position += 1
    assert position == len(rows)
    return rows, pivots


def circuit(error, plus=False):
    """Clifford preparation of |0_L> or |+_L>, followed by a known Pauli."""
    kernel = cudaq.make_kernel()
    data = kernel.qalloc(N)
    rows, pivots = rref(list(HX) + ([LX] if plus else []))
    for pivot in pivots:
        kernel.h(data[pivot])
    for row, pivot in zip(rows, pivots):
        for q in range(N):
            if q != pivot and ((row >> q) & 1):
                kernel.cx(data[pivot], data[q])
    for q in range(N):
        if (error >> q) & 1:
            kernel.x(data[q])
        if (error >> (q + N)) & 1:
            kernel.z(data[q])
    return kernel


def pauli(mask, axis):
    result = cudaq.spin.i(0)
    for q in range(N):
        if (mask >> q) & 1:
            result *= getattr(cudaq.spin, axis)(q)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["qpp-cpu", "nvidia"], required=True)
    parser.add_argument("--precision", choices=["fp32", "fp64"], default="fp64")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config_path = Path(__file__).with_name("config.json")
    config = json.loads(config_path.read_text())
    if args.target == "nvidia":
        cudaq.set_target(args.target, option=args.precision)
    else:
        if args.precision != "fp64":
            raise ValueError("qpp-cpu check uses fp64; choose --precision fp64")
        cudaq.set_target(args.target)
    if args.target == "nvidia" and cudaq.num_available_gpus() < 1:
        raise RuntimeError("GPU target requested but CUDA-Q reports no GPU; no fallback")
    # Each eigenvalue term contributes one syndrome bit. Exact expectations,
    # not finite-shot estimates, are appropriate for this deterministic check.
    observable = 0.0 * cudaq.spin.i(0)
    for i, row in enumerate(HZ):
        observable += (2**i / 2) * (cudaq.spin.i(0) - pauli(row, "z"))
    for i, row in enumerate(HX):
        observable += (2**(i + 4) / 2) * (cudaq.spin.i(0) - pauli(row, "x"))
    singles = [((p & 1) << q) | (((p >> 1) & 1) << (q + N))
               for q in range(N) for p in (1, 2, 3)]
    rng = random.Random(config["cudaq_spotcheck_seed"])
    cases = [0] + singles + [rng.randrange(1 << (2 * N)) for _ in range(config["cudaq_random_cases"])]
    results = []
    started = time.perf_counter()
    max_error = 0.0
    for error in cases:
        actual = cudaq.observe(circuit(error), observable).expectation()
        expected = syndrome(error)
        difference = abs(actual - expected)
        max_error = max(max_error, difference)
        results.append({"pauli_word": error, "expected_syndrome": expected,
                        "observed_syndrome_expectation": actual, "absolute_error": difference})
    # Detect all nontrivial logical cosets using both logical basis states.
    logical_checks = []
    for logical_word in (0, LX, LZ << N, LX | (LZ << N)):
        for plus, check, expected in (
            (False, pauli(LZ, "z"), -1 if logical_word & LX else 1),
            (True, pauli(LX, "x"), -1 if logical_word >> N else 1)):
            actual = cudaq.observe(circuit(logical_word, plus), check).expectation()
            difference = abs(actual - expected)
            max_error = max(max_error, difference)
            logical_checks.append({"logical_word": logical_word, "plus_basis": plus,
                                   "expected": expected, "actual": actual, "absolute_error": difference})
    status = "PASS" if max_error <= config["cudaq_syndrome_absolute_tolerance"] else "FAIL"
    receipt = {"status": status, "target_requested": args.target,
               "precision_requested": args.precision,
               "target_reported": str(cudaq.get_target()),
               "cudaq_version": getattr(cudaq, "__version__", "not exposed"),
               "cudaq_distributions": {distribution.metadata["Name"]: distribution.version
                                       for distribution in importlib.metadata.distributions()
                                       if distribution.metadata.get("Name", "").lower().startswith(("cuda-quantum", "cudaq"))},
               "available_gpus": cudaq.num_available_gpus(),
               "python_version": sys.version, "platform": platform.platform(),
               "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
               "wall_seconds": time.perf_counter() - started, "syndrome_cases": len(cases),
               "logical_basis_cases": len(logical_checks), "max_absolute_error": max_error,
               "results": results, "logical_checks": logical_checks,
               "scope": "ideal Clifford state preparation and Pauli injections; no noisy syndrome circuits"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({key: value for key, value in receipt.items() if key not in ("results", "logical_checks")}))
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
