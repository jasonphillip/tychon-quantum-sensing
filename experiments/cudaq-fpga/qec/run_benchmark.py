"""Run the frozen small-code benchmark; output directory must be new."""
import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import shutil
import statistics
import subprocess
import sys
import time
import traceback

from qec_model import (N, STABILIZERS, exact_failure, logical_class,
                       maximum_likelihood_lut, probability_weights, sample_error,
                       syndrome, tables, weight)

ROOT = Path(__file__).resolve().parent


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wilson(successes, n):
    z = 1.959963984540054
    phat = successes / n
    denominator = 1 + z*z/n
    center = (phat + z*z/(2*n)) / denominator
    margin = z * math.sqrt(phat*(1-phat)/n + z*z/(4*n*n)) / denominator
    return [center - margin, center + margin]


def write_header(candidate, joint, x_lut, z_lut):
    content = ["// Generated from frozen config.json by exact stabilizer-coset enumeration.",
               "// Config SHA256: " + sha(ROOT / "config.json"),
               "#ifndef QEC_TABLES_H", "#define QEC_TABLES_H", "#include <stdint.h>"]
    for name, values, ctype in (("QEC_ML_LUT", candidate, "uint32_t"),
                                ("QEC_JOINT_MW_LUT", joint, "uint32_t"),
                                ("QEC_X_LUT", x_lut, "uint16_t"),
                                ("QEC_Z_LUT", z_lut, "uint16_t")):
        content.append("static const %s %s[%d] = {" % (ctype, name, len(values)))
        for start in range(0, len(values), 8):
            content.append("    " + ", ".join(str(v) + "u" for v in values[start:start+8]) + ",")
        content.append("};")
    content.append("#endif")
    (ROOT / "qec_tables.h").write_text("\n".join(content) + "\n")


def run(command, output, name):
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=300)
    (output / (name + ".stdout.txt")).write_text(result.stdout)
    (output / (name + ".stderr.txt")).write_text(result.stderr)
    write_json(output / (name + ".command.json"), {"argv": command, "returncode": result.returncode})
    result.check_returncode()
    return result.stdout


def execute(output):
    start = time.perf_counter()
    config = json.loads((ROOT / "config.json").read_text())
    resource.setrlimit(resource.RLIMIT_CPU, (config["limits"]["cpu_seconds"], config["limits"]["cpu_seconds"]))
    test_output = run([sys.executable, "-m", "unittest", "-v", "test_qec"], output, "tests")
    joint, separate, counts, _, x_lut, z_lut = tables()
    candidate = maximum_likelihood_lut(config["design_error_probability"])
    decoders = {"fixed_ml": candidate, "separate_css": separate, "joint_min_weight": joint}
    write_header(candidate, joint, x_lut, z_lut)
    write_json(output / "correction_tables.json", decoders)
    write_json(output / "coset_weight_enumerators.json", counts)

    # Independent exact probability reference: membership in the complete
    # stabilizer group, instead of the two-bit logical observable formula.
    failures_by_weight = {name: [0] * (N + 1) for name in decoders}
    for error in range(1 << (2*N)):
        s, w = syndrome(error), weight(error)
        for name, lut in decoders.items():
            if (error ^ lut[s]) not in STABILIZERS:
                failures_by_weight[name][w] += 1
    write_json(output / "reference_failure_weight_counts.json", failures_by_weight)

    results = []
    shots = config["heldout_shots_per_probability"]
    for p, seed in zip(config["evaluation_error_probabilities"], config["heldout_seeds"]):
        exact = {}
        for name, lut in decoders.items():
            failure, total = exact_failure(lut, p)
            independent = sum(n * pr for n, pr in zip(failures_by_weight[name], probability_weights(p)))
            assert abs(total - 1) < config["acceptance"]["probability_normalization_absolute_tolerance"]
            assert abs(failure - independent) < 1e-13
            exact[name] = failure
        oracle, _ = exact_failure(maximum_likelihood_lut(p), p)
        rng = random.Random(seed)
        failures = {name: 0 for name in decoders}
        digest = hashlib.sha256()
        begin = time.perf_counter()
        for _ in range(shots):
            error = sample_error(rng, p)
            digest.update(error.to_bytes(3, "little"))
            s = syndrome(error)
            for name, lut in decoders.items():
                failures[name] += logical_class(error ^ lut[s]) != 0
        sampling_seconds = time.perf_counter() - begin
        comparisons = {}
        for name in decoders:
            observed = failures[name] / shots
            sigma = math.sqrt(exact[name]*(1-exact[name])/shots)
            z = abs(observed - exact[name]) / sigma
            assert z <= config["acceptance"]["monte_carlo_exact_z_max"], (p, name, z)
            comparisons[name] = {"logical_failures": failures[name], "shots": shots,
                                 "logical_failure_rate": observed, "wilson_95_interval": wilson(failures[name], shots),
                                 "exact_logical_failure_probability": exact[name], "absolute_z_from_exact": z}
        results.append({"physical_pauli_error_probability": p, "seed": seed,
                        "paired_error_stream_sha256": digest.hexdigest(),
                        "sampling_and_three_decoders_seconds": sampling_seconds,
                        "oracle_exact_logical_failure_probability": oracle, "decoders": comparisons})

    compiler = shutil.which(os.environ.get("CXX", "clang++")) or shutil.which("g++")
    if compiler is None:
        raise RuntimeError("A C++ compiler is required for the host parity gate")
    compiler_version = run([compiler, "--version"], output, "compiler_version")
    binary = output / "host_benchmark"
    run([compiler, "-std=c++11", "-O3", "-Wall", "-Wextra", "-Werror",
         str(ROOT / "qec_decoder.cpp"), str(ROOT / "host_benchmark.cpp"), "-o", str(binary)], output, "compile")
    dump = run([str(binary), "--dump"], output, "host_dump")
    rows = [list(map(int, line.split())) for line in dump.splitlines()]
    assert len(rows) == 256
    for s, ml, css, mw in rows:
        assert [ml, css, mw] == [candidate[s], separate[s], joint[s]]
    runtime = json.loads(run([str(binary), "--benchmark"], output, "host_benchmark"))
    for measurement in runtime["measurements"]:
        measurement["median_ns_per_lookup"] = statistics.median(measurement["ns_per_lookup_repeats"])
    design_row = next(row for row in results if row["physical_pauli_error_probability"] == config["design_error_probability"])
    design_metrics = design_row["decoders"]
    advantage = design_metrics["fixed_ml"]["exact_logical_failure_probability"] < design_metrics["separate_css"]["exact_logical_failure_probability"]
    metrics = {"status": "PASS", "completed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "scope": "synthetic single-round perfect-syndrome code capacity; CPU/host execution",
               "config_sha256": sha(ROOT / "config.json"), "platform": platform.platform(),
               "machine": platform.machine(), "python_version": sys.version,
               "compiler_version": compiler_version.splitlines()[0],
               "exhaustive_pauli_errors": 4**N, "syndromes": 256, "stabilizer_group_size": len(STABILIZERS),
               "single_pauli_errors_corrected": 27, "verified_code_parameters": [9, 1, 3],
               "unittest_count": 6, "host_table_comparisons": 768, "host_table_mismatches": 0,
               "candidate_fixed_rom_bits": 256*18, "candidate_uint32_storage_bytes": 256*4,
               "separate_css_fixed_rom_bits": 2*16*9, "separate_css_uint16_storage_bytes": 2*16*2,
               "candidate_operations_per_decode": {"lookup": 1, "allocation": 0, "data_dependent_loop": 0},
               "design_point_advantage_over_separate_css": advantage, "results": results,
               "host_runtime": runtime, "wall_seconds": time.perf_counter() - start,
               "fpga_synthesis": "NOT_RUN", "fpga_execution": "NOT_RUN", "cudaq_execution": "separate optional receipt",
               "peak_rss_platform_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
               "interpretation": "small-code reproduction; no novelty, scalability, GPU advantage, radiation, or real-time hardware claim"}
    write_json(output / "metrics.json", metrics)
    files = sorted([path for path in ROOT.iterdir() if path.is_file() and path.suffix in (".py", ".cpp", ".h", ".json")])
    write_json(output / "source_manifest.json", {path.name: sha(path) for path in files})
    print(json.dumps({"status": metrics["status"], "output": str(output),
                      "wall_seconds": metrics["wall_seconds"], "tests": 6,
                      "exhaustive_errors": metrics["exhaustive_pauli_errors"],
                      "host_mismatches": 0, "design_point_advantage": advantage,
                      "design_point_results": design_metrics}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        execute(output)
    except BaseException as error:
        write_json(output / "failure.json", {"error": repr(error), "traceback": traceback.format_exc(),
                                            "config_sha256": sha(ROOT / "config.json")})
        raise


if __name__ == "__main__":
    main()
