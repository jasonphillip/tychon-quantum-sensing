#!/usr/bin/env python3
"""Run the finite public saved-evidence checks. Never install, fetch, train, or infer."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
WORKER = Path("workers/odmr-edge-ml")
KIT_MANIFEST = WORKER / "docs/kit-run-2026-10-14/ARRAYS.manifest.json"
PINS = {
    str(KIT_MANIFEST): "a42630d18db5941b6d72110b2098bb72cc4f5c0611cbd9b35df81421c246a02b",
    str(WORKER / "docs/scalar_repair_cycle_2026-10/BUNDLE.manifest.json"):
        "7150142ed4ffbd318ac3ba9ee8f9b87a85cf82faf8ce2c10a0c74c67a4f9b36b",
    "docs/nv_advantage_search_2026-10/ARTIFACTS.sha256.json":
        "edf9957d309455244c2b1ffff9ac6215f4eef0bafb0a4289330514591571e4cf",
    "docs/nv_vector_development_2026-10/ARTIFACTS.sha256.json":
        "90d07580754aaf95376f433fad84cd074c7b01b394d7eca92b28df80e39bc6b4",
    "docs/nv_vector_development_2026-10/p1/PUBLIC-MANIFEST.json":
        "33227a10dbb88865a4947b7eccc89822e49501f7366443150410fc983f13f22a",
    "docs/nv_vector_development_2026-10/challenge/PUBLIC-MANIFEST.json":
        "c2008011a48b3ce7af69f2334710317072d54f2a6a7c233d38cf2b15d98dd969",
}
MAX_SECONDS = 900
MAX_MEMORY_BYTES = 4 * 1024**3


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def require_file(path: Path, expected: str) -> None:
    if not path.is_file():
        raise ValueError(f"Missing evidence: {path}")
    if digest(path) != expected:
        raise ValueError(f"SHA256 mismatch: {path}")


def checkout_root(path: Path) -> Path:
    for parent in (path, *path.parents):
        if (parent / ".git").exists():
            return parent
    return path


def output_path(value: str | None, kit: Path) -> Path:
    if value:
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("--out must be an absolute path")
        if path.exists():
            raise ValueError("--out must be a new directory")
        path = path.resolve()
    else:
        # Reserve no files until preflight succeeds.
        path = Path(tempfile.gettempdir()).resolve() / ("tychon-evidence-" + os.urandom(8).hex())
    for boundary in (checkout_root(ROOT), checkout_root(kit) if kit.exists() else kit, ROOT, kit):
        if path.is_relative_to(boundary):
            raise ValueError("--out must be outside both checkouts and evidence directories")
    return path


def preflight(kit: Path) -> dict:
    if not kit.is_dir():
        raise ValueError(f"KIT_EVIDENCE_DIR does not exist: {kit}")
    for relative, expected in PINS.items():
        require_file(ROOT / relative, expected)
    manifest = json.loads((ROOT / KIT_MANIFEST).read_text())
    external = manifest["external_kit_evidence"]
    for name, spec in external["files"].items():
        require_file(kit / name, spec["sha256"])
        if (kit / name).stat().st_size != spec["size_bytes"]:
            raise ValueError(f"Size mismatch: {kit / name}")
    return {"repository": external["repo"], "revision": external["revision"],
            "identity": "exact file hashes in pinned ARRAYS.manifest.json"}


def commands(kit: Path, out: Path) -> list[tuple[str, list[str]]]:
    worker = ROOT / WORKER
    run = worker / "docs/kit-run-2026-10-14"
    scalar = worker / "docs/scalar_repair_cycle_2026-10"
    advantage = ROOT / "docs/nv_advantage_search_2026-10"
    vector = ROOT / "docs/nv_vector_development_2026-10"
    def call(relative, *args):
        return [sys.executable, "-B", str(ROOT / relative), *map(str, args)]
    jobs = [
        ("kit", call(WORKER / "scripts/recompute_published_kit_metrics.py",
          "--run-dir", run, "--hardware-evidence-dir", kit,
          "--expected-results", run / "results.json",
          "--expected-constants", worker / "docs/kit_constant_baselines_2026-10.json",
          "--verify-sha256", "--no-network", "--atol-uT", "0.000001", "--out", out / "kit.json")),
        ("scalar-validation", call(WORKER / "scripts/recompute_published_scalar_validation.py",
          "--bundle", scalar, "--no-network", "--cross-check-truth",
          "--expected-bundle-manifest-sha256", PINS[str(WORKER / "docs/scalar_repair_cycle_2026-10/BUNDLE.manifest.json")],
          "--out", out / "scalar-validation.json")),
        ("advantage-package", call("docs/nv_advantage_search_2026-10/check_package.py",
          "--expected-artifacts-sha256", PINS["docs/nv_advantage_search_2026-10/ARTIFACTS.sha256.json"])),
        ("raw-compatibility", call("docs/nv_advantage_search_2026-10/check_raw_compatibility.py",
          "--bundle", advantage / "localisation-raw-compatibility",
          "--protocol", worker / "experiments/localisation_raw_compatibility/protocol.json",
          "--out", out / "raw-compatibility")),
        ("vector-package", call("docs/nv_vector_development_2026-10/check_package.py",
          "--expected-artifacts-sha256", PINS["docs/nv_vector_development_2026-10/ARTIFACTS.sha256.json"])),
    ]
    for name in ("p1", "challenge"):
        jobs.append(("vector-" + name, call(WORKER / ("scripts/vector_public_saved/verify_" + name + "_saved.py"),
          "--bundle", vector / name, "--expected-manifest-sha256",
          PINS["docs/nv_vector_development_2026-10/" + name + "/PUBLIC-MANIFEST.json"],
          "--config", worker / "experiments/vector_direct_screen/config.json",
          "--out", out / ("vector-" + name))))
    return jobs


def child_limit() -> None:
    # RLIMIT_AS is enforced on Linux. It is not a reliable RSS cap on macOS.
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_AS, (MAX_MEMORY_BYTES, MAX_MEMORY_BYTES))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit-evidence-dir", required=True)
    parser.add_argument("--out", help="New absolute directory outside the source and kit checkouts")
    args = parser.parse_args()
    if not __debug__:
        parser.error("Verification requires assertions; do not use Python -O or PYTHONOPTIMIZE")
    if not args.kit_evidence_dir.strip():
        parser.error("Set KIT_EVIDENCE_DIR to the pinned public kit evidence; see docs/reproduce-evidence.md")
    if not Path(args.kit_evidence_dir).is_absolute():
        parser.error("KIT_EVIDENCE_DIR must be an absolute path")
    kit = Path(args.kit_evidence_dir).resolve()
    try:
        out = output_path(args.out, kit)
        external = preflight(kit)
        versions = {name: importlib.metadata.version(name) for name in ("numpy", "scipy")}
    except (ValueError, OSError, importlib.metadata.PackageNotFoundError) as exc:
        print(f"RESULT: FAIL preflight: {exc}", file=sys.stderr)
        return 1
    out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[name] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["CUDA_VISIBLE_DEVICES"] = ""
    env.pop("PYTHONPATH", None)
    started = time.monotonic()
    report = {
        "schema": 1, "status": "FAIL", "scope": "seven named saved-evidence checks only",
        "scientific_pass_is_not_required": True,
        "no_training_or_inference": True, "verification_fetches_no_data": True,
        "python": platform.python_version(), "platform": platform.platform(), "packages": versions,
        "pins": PINS, "kit_provenance": external,
        "wrapper_sha256": digest(Path(__file__)), "checks": [],
        "limits": {"wall_seconds": MAX_SECONDS, "threads_per_child": 1,
                   "linux_address_space_bytes_per_child": MAX_MEMORY_BYTES if sys.platform == "linux" else None},
    }
    try:
        for name, command in commands(kit, out):
            remaining = MAX_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("Overall 900-second verification limit reached")
            step_started = time.monotonic()
            log = out / (name + ".log")
            with log.open("x") as stream:
                result = subprocess.run(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                        timeout=remaining, preexec_fn=child_limit)
            report["checks"].append({"name": name, "exit_code": result.returncode,
                                     "wall_seconds": time.monotonic() - step_started, "log": log.name})
            if result.returncode:
                raise RuntimeError(f"{name} failed; see {log}")
            print(f"PASS {name}", flush=True)
        report["status"] = "PASS"
    except (OSError, RuntimeError, TimeoutError, subprocess.TimeoutExpired) as exc:
        report["error"] = str(exc)
        print(f"RESULT: FAIL: {exc}", file=sys.stderr)
    finally:
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        report["wall_seconds"] = time.monotonic() - started
        report["child_cpu_seconds"] = usage.ru_utime + usage.ru_stime
        report["max_child_rss_bytes"] = int(usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024))
        (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"Report: {out / 'summary.json'}")
    if report["status"] == "PASS":
        print("RESULT: PASS (saved evidence reproduced; this does not establish a scientific advantage)")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
