#!/usr/bin/env python3
"""Pre-registered vector comparison study runner (docs/comparison_study_protocol_2026-10.md).

Scores E1..E5 on one partition of data/comparison_test_vN/ under the protocol's metrics,
Addendum (b) failure accounting and paired sequence-blocked bootstrap.  The decision rule
(`decide`) is wired only for --partition final.  Final is guarded; see `check_partition_guard`.
"""
from __future__ import annotations

import os
for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_k] = "1"

import argparse
import datetime as dt
import hashlib
import itertools
import json
import platform
import struct
import subprocess
import sys
import time
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from odmr_vector_tracking.evaluation.metrics import full_vector_lock, full_vector_lock_stats  # noqa: E402
from odmr_vector_tracking.evaluation.rows import fieldcone_metrics_row  # noqa: E402

ESTIMATORS = ("E1", "E2", "E3", "E4", "E5")
PRIMARY = ("clean", "realistic")
E4_CHECKPOINT = "artifacts/portfolio-n/noassoc_s20260702/best.pt"
E4_SHA256 = "0cc0f9ce5969043dfbe2afbb8337eeb2bd4f3df213a1d1b57f161c49ff6b9f99"
E1_BASE = "ba640fc2b8303ef0c0dc7f6506b8152fd0635e75"
NLS_MODULE = "src/odmr_vector_tracking/tracking/nls_baseline.py"
BOOT_N = 10_000
BOOT_SEED = 20261014
ANGULAR_MARGIN_DEG = 5.0
RMSE_MARGIN_FRAC = 0.10
LOST_FRAME_FRAC = 0.10
NEITHER_LOST_RATE = 0.50
CHOICE_FILE = "docs/best_classical_choice_2026-10.json"


class GuardError(RuntimeError):
    pass


# ----------------------------------------------------------------------------- data hashing

def cell_md5(cell_dir: Path) -> str:
    """Protocol rule: MD5 over sorted relative dataset.h5 paths (4-byte BE length, path, bytes)."""
    cell_dir = Path(cell_dir)
    h = hashlib.md5()
    for path in sorted(cell_dir.rglob("dataset.h5"), key=lambda p: p.relative_to(cell_dir).as_posix()):
        rel = path.relative_to(cell_dir).as_posix().encode()
        h.update(struct.pack(">I", len(rel)))
        h.update(rel)
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                h.update(block)
    return h.hexdigest()


def _has_write_bits(root: Path) -> list[str]:
    bad = []
    for path in [root, *root.rglob("*")]:
        if path.stat().st_mode & 0o222:
            bad.append(str(path))
    return bad


def check_partition_guard(partition, data_dir, manifest, choice_path, results_path,
                          rerun_reason=None, version=1):
    """Raise GuardError unless the partition may be scored.

    val: every manifest cell md5 recomputes.
    final: additionally no write bits under the directory, the best-classical choice file
    exists, and no results file for this partition+version exists (unless rerun_reason).
    dev: no checks.  Never reads anything but hashes (no data decode).
    """
    if partition == "dev":
        return
    data_dir = Path(data_dir)
    if partition == "final":
        # Cheap preconditions first, so a failing guard touches no data bytes.
        if not data_dir.is_dir():
            raise GuardError(f"final directory missing: {data_dir}")
        bad = _has_write_bits(data_dir)
        if bad:
            raise GuardError(f"final directory has write bits ({len(bad)} paths, e.g. {bad[0]})")
        if not Path(choice_path).is_file():
            raise GuardError(f"best-classical choice file missing: {choice_path}")
        if Path(results_path).exists() and not rerun_reason:
            raise GuardError(f"results for final v{version} already exist at {results_path}; "
                             "a second run requires --rerun-reason")
    for cell in manifest["partitions"][partition]["cells"]:
        directory = data_dir / cell["name"]
        if not directory.is_dir():
            raise GuardError(f"{partition} cell missing: {cell['name']}")
        got = cell_md5(directory)
        if got != cell["data_md5"]:
            raise GuardError(f"{partition} cell {cell['name']} md5 {got} != manifest {cell['data_md5']}")


# ----------------------------------------------------------------------------- scoring

def score_sequence(true_B, raw_B, bias_B, dt_s):
    """Score one sequence under Addendum (b).

    raw_B: (T,3) estimator output, NaN/None-row/missing = no estimate.  A missing frame takes
    the estimator's own fallback (last finite estimate, else the bias field) for the error
    metrics and is always unlocked.  >10 % missing frames = lost.
    """
    true_B = np.asarray(true_B, dtype=float)
    raw = np.asarray(raw_B, dtype=float).reshape(true_B.shape)
    missing = ~np.isfinite(raw).all(axis=1)
    scored = raw.copy()
    fallback = np.asarray(bias_B, dtype=float).copy()
    for t in range(len(scored)):
        if missing[t]:
            scored[t] = fallback
        else:
            fallback = scored[t].copy()
    row = fieldcone_metrics_row(true_B, scored, dt_s=dt_s)
    lock = full_vector_lock(true_B, scored) & ~missing
    row.update(full_vector_lock_stats(lock))
    row["lost"] = bool(row["lost"] or missing.mean() > LOST_FRAME_FRAC)
    row["n_valid_frames"] = int((~missing).sum())
    row["nonfinite_frames"] = int(missing.sum())
    row["rmse_mT"] = row["rmse_T"] * 1e3
    row["mag_bias_mT"] = row["mag_err_mean_T"] * 1e3
    return row


def _pct90(x):
    return float(np.percentile(np.asarray(x, dtype=float), 90))


def cell_stats(rows, frame_times_s):
    n = len(rows)
    ae90 = [r["ae_p90_deg"] for r in rows]
    t = np.asarray(frame_times_s, dtype=float)
    return {
        "n_sequences": n,
        "rmse_mean_mT": float(np.mean([r["rmse_mT"] for r in rows])),
        "ae_mean_deg": float(np.mean([r["ae_mean_deg"] for r in rows])),
        "ae_p90_of_seq_p90_deg": _pct90(ae90),
        "mag_bias_mean_mT": float(np.mean([r["mag_bias_mT"] for r in rows])),
        "lock_frac_mean": float(np.mean([r["lock_frac"] for r in rows])),
        "lost_rate": float(np.mean([r["lost"] for r in rows])),
        "nonfinite_frames": int(sum(r["nonfinite_frames"] for r in rows)),
        "sequences_with_nonfinite": int(sum(r["nonfinite_frames"] > 0 for r in rows)),
        "latency_us_median": float(np.median(t) * 1e6) if t.size else float("nan"),
        "latency_us_p90": float(np.percentile(t, 90) * 1e6) if t.size else float("nan"),
    }


def paired_bootstrap(rmse, ae_p90, n_boot=BOOT_N, seed=BOOT_SEED):
    """rmse, ae_p90: {estimator: (n,) per-sequence arrays}, same sequence order.

    Resamples whole sequences once per draw (pairing kept across estimators), recomputes the
    registered statistics (mean RMSE; p90 of per-sequence angular p90) per draw, and returns
    {"A|B": {...}} with difference A - B for every ordered-by-input pair.
    """
    names = list(rmse)
    n = len(next(iter(rmse.values())))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    mean_rmse = {k: np.asarray(v, dtype=float)[idx].mean(axis=1) for k, v in rmse.items()}
    p90 = {k: np.percentile(np.asarray(v, dtype=float)[idx], 90, axis=1) for k, v in ae_p90.items()}
    out = {}
    for a, b in itertools.combinations(names, 2):
        d1 = mean_rmse[a] - mean_rmse[b]
        d2 = p90[a] - p90[b]
        out[f"{a}|{b}"] = {
            "rmse_diff_mT": float(np.mean(rmse[a]) - np.mean(rmse[b])),
            "rmse_diff_ci95_mT": [float(np.percentile(d1, 2.5)), float(np.percentile(d1, 97.5))],
            "ae_p90_diff_deg": _pct90(ae_p90[a]) - _pct90(ae_p90[b]),
            "ae_p90_diff_ci95_deg": [float(np.percentile(d2, 2.5)), float(np.percentile(d2, 97.5))],
            "n_boot": n_boot, "seed": seed,
        }
    return out


# ----------------------------------------------------------------------------- decision rule

def _pair(cell, x, y):
    """Return (rmse_ci, ang_ci) of the difference x - y for a cell, flipping stored order."""
    pairs = cell["pairs"]
    if f"{x}|{y}" in pairs:
        p = pairs[f"{x}|{y}"]
        return p["rmse_diff_ci95_mT"], p["ae_p90_diff_ci95_deg"]
    p = pairs[f"{y}|{x}"]
    r, a = p["rmse_diff_ci95_mT"], p["ae_p90_diff_ci95_deg"]
    return [-r[1], -r[0]], [-a[1], -a[0]]


def beats(cell, winner, loser):
    """Registered win test of `winner` over `loser` on one cell.

    Needs: angular p90 improvement >= 5 deg, RMSE improvement (loser-winner)/loser >= 10 %
    (loser RMSE > 0), and both paired 95 % CIs excluding zero in the winner's direction.
    """
    s = cell["stats"]
    ang_imp = s[loser]["ae_p90_of_seq_p90_deg"] - s[winner]["ae_p90_of_seq_p90_deg"]
    lr = s[loser]["rmse_mean_mT"]
    rmse_imp = (lr - s[winner]["rmse_mean_mT"]) / lr if lr > 0 else float("nan")
    rci, aci = _pair(cell, winner, loser)       # winner - loser: want < 0
    ok = bool(ang_imp >= ANGULAR_MARGIN_DEG and lr > 0 and rmse_imp >= RMSE_MARGIN_FRAC
              and rci[1] < 0 and aci[1] < 0)
    return {"win": ok, "angular_improvement_deg": float(ang_imp),
            "rmse_improvement_frac": float(rmse_imp), "rmse_diff_ci95_mT": rci,
            "ae_p90_diff_ci95_deg": aci}


def decide(results):
    """Apply the registered rule.

    results = {"best_classical": "E2"|"E3", "cells": {name: {"stats": {E: {...}},
    "pairs": {"A|B": {...}}}}}.  Primary = clean, realistic; every other cell is secondary
    (extrapolation included, labelled).  Precedence: neither_reliable, two-primary win,
    niche_to_confirm, inconclusive.
    """
    cells = results["cells"]
    classical = results["best_classical"]
    lost = [cells["clean"]["stats"][e]["lost_rate"] for e in ("E2", "E3", "E4")
            if e in cells["clean"]["stats"]]
    detail = {}
    for name, cell in cells.items():
        detail[name] = {"classical_beats_E4": beats(cell, classical, "E4"),
                        "E4_beats_classical": beats(cell, "E4", classical)}
    out = {"best_classical": classical, "detail": detail,
           "clean_lowest_lost_rate_E2_E3_E4": min(lost) if lost else None}
    if lost and min(lost) > NEITHER_LOST_RATE:
        out.update(outcome="neither_reliable", qualifying=[])
        return out
    side_keys = {"classical": "classical_beats_E4", "network": "E4_beats_classical"}
    prim = {s: [c for c in PRIMARY if c in cells and detail[c][k]["win"]] for s, k in side_keys.items()}
    sec = {s: [c for c in cells if c not in PRIMARY and detail[c][k]["win"]] for s, k in side_keys.items()}
    if len(prim["classical"]) == 2 and len(PRIMARY) == 2:
        out.update(outcome="classical_wins", qualifying=[("classical", c) for c in PRIMARY])
    elif len(prim["network"]) == 2:
        out.update(outcome="network_wins", qualifying=[("network", c) for c in PRIMARY])
    else:
        q = []
        for s in side_keys:
            if len(prim[s]) == 1 or len(sec[s]) >= 3:
                q += [(s, c) for c in prim[s]] + ([(s, c) for c in sec[s]] if len(sec[s]) >= 3 else [])
        out.update(outcome="niche_to_confirm" if q else "inconclusive", qualifying=q)
    return out


# ----------------------------------------------------------------------------- estimators

def frozen_nls_module():
    source = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{E1_BASE}:{NLS_MODULE}"], text=True)
    module = types.ModuleType("e1_frozen_nls")
    module.__package__ = "odmr_vector_tracking.tracking"
    exec(compile(source, f"git:{E1_BASE}:{NLS_MODULE}", "exec"), module.__dict__)
    return module, hashlib.sha256(source.encode()).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


class Runner:
    """Holds estimator factories; each `run_<E>` returns (raw_B (T,3), frame_times_s (T,))."""

    def __init__(self, selected):
        self.selected = list(selected)
        self.identity = {}
        if "E1" in selected:
            self.frozen, digest = frozen_nls_module()
            self.identity["E1"] = {"module": f"git:{E1_BASE}:{NLS_MODULE}", "source_sha256": digest,
                                   "flags": "published defaults"}
        if "E2" in selected:
            self.identity["E2"] = {"module": NLS_MODULE, "source_sha256": sha256_file(ROOT / NLS_MODULE),
                                   "flags": {"multi_start": True, "profile": "lorentzian",
                                             "estimate_linewidth": True}}
        if "E3" in selected:
            p = "src/odmr_vector_tracking/tracking/exact_inversion_baseline.py"
            self.identity["E3"] = {"module": p, "source_sha256": sha256_file(ROOT / p)}
        if "E5" in selected:
            p = "src/odmr_vector_tracking/tracking/kf_baseline.py"
            self.identity["E5"] = {"module": p, "source_sha256": sha256_file(ROOT / p),
                                   "note": "truth line centers at frame 0; diagnostic only"}
        if "E4" in selected:
            import torch
            torch.set_num_threads(1)
            from odmr_vector_tracking.tracking.learned import (
                build_tracker, config_from_checkpoint, load_tracker_state)
            ck_path = ROOT / E4_CHECKPOINT
            digest = sha256_file(ck_path)
            if digest != E4_SHA256:
                raise SystemExit(f"E4 checkpoint sha256 {digest} != registered {E4_SHA256}")
            ck = torch.load(ck_path, map_location="cpu", weights_only=False)
            cfg = config_from_checkpoint(ck["model_cfg"], ck["model_state"])
            self.e4 = build_tracker(cfg, core=ck["meta"]["core"], association=ck["meta"]["association"])
            load_tracker_state(self.e4, ck["model_state"])
            self.e4.eval()
            self.torch = torch
            self.identity["E4"] = {"checkpoint": E4_CHECKPOINT, "checkpoint_sha256": digest,
                                   "device": "cpu", "n_freq": cfg.n_freq}

    def run(self, est, spectra, freqs, width, bias, resonance0):
        T = len(spectra)
        started = time.perf_counter()
        if est in ("E1", "E2"):
            from odmr_vector_tracking.tracking.acquisition import acquire_centers_with_diagnostics
            from odmr_vector_tracking.tracking.nls_baseline import NLSTracker
            initial, _ = acquire_centers_with_diagnostics(spectra[0], freqs, linewidth_Hz=width, bias_field_t=bias)
            opts = dict(frequencies=freqs, linewidth_Hz=width, line_depths=None)
            tr = (self.frozen.NLSTracker(**opts) if est == "E1" else
                  NLSTracker(**opts, multi_start=True, estimate_linewidth=True))
            res = tr.run(spectra, initial)
            raw = np.asarray(res.B_est, dtype=float)
            total = time.perf_counter() - started
            fs = getattr(tr, "diagnostics_", {}).get("frame_seconds") if est == "E2" else None
            if fs is not None and len(fs) == T:
                times = np.asarray(fs, dtype=float)
                times[0] += max(0.0, total - float(times.sum()))
            else:
                times = np.full(T, total / T)
            return raw, times
        if est == "E3":
            from odmr_vector_tracking.tracking.exact_inversion_baseline import ExactInversionTracker
            tr = ExactInversionTracker(freqs, linewidth_Hz=width, bias_field_t=bias)
            raw, times = np.full((T, 3), np.nan), np.empty(T)
            for t, frame in enumerate(spectra):
                tick = time.perf_counter()
                try:
                    state = tr.step(frame)
                    b = None if state is None else np.asarray(state.B_est, dtype=float)
                except Exception:
                    b = None
                times[t] = time.perf_counter() - tick
                if b is not None and b.shape == (3,):
                    raw[t] = b
            return raw, times
        if est == "E4":
            torch = self.torch
            x = torch.as_tensor(np.asarray(spectra, dtype=np.float32))[None]
            with torch.no_grad():
                out = self.e4(x)
            raw = out.b_est[0].numpy().astype(float)
            return raw, np.full(T, (time.perf_counter() - started) / T)
        if est == "E5":
            from odmr_vector_tracking.tracking.classical import auto_peak_min_depth
            from odmr_vector_tracking.tracking.kf_baseline import KFHungarianTracker
            tr = KFHungarianTracker(freqs, linewidth_Hz=width, peak_min_depth=auto_peak_min_depth(spectra))
            raw = np.asarray(tr.run(spectra, init_freqs=resonance0).B_est, dtype=float)
            return raw, np.full(T, (time.perf_counter() - started) / T)
        raise ValueError(est)


# ----------------------------------------------------------------------------- driver

def git_info():
    def g(*a):
        return subprocess.check_output(["git", "-C", str(ROOT), *a], text=True).strip()
    return {"commit": g("rev-parse", "HEAD"), "dirty": bool(g("status", "--porcelain", "--untracked-files=no"))}


def environment(cpu):
    import scipy
    versions = {"numpy": np.__version__, "scipy": scipy.__version__}
    try:
        import torch
        versions["torch"] = torch.__version__
    except Exception:
        pass
    model = ""
    try:
        for line in open("/proc/cpuinfo"):
            if line.lower().startswith(("model name", "cpu part")):
                model = line.strip()
                break
    except OSError:
        pass
    return {"python": platform.python_version(), "machine": platform.machine(), "cpu": model,
            "affinity": sorted(os.sched_getaffinity(0)), "cpu_arg": cpu, "versions": versions,
            "thread_limits": {k: os.environ[k] for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")}}


def load_cell(cell_dir, max_sequences):
    import h5py
    seqs = []
    for seed_dir in sorted(Path(cell_dir).glob("seed_*")):
        manifest = json.loads((seed_dir / "manifest.json").read_text())
        direction = np.asarray(manifest["bias_direction_uvw"], dtype=float)
        bias = float(manifest["bias_B0_T"]) * direction / np.linalg.norm(direction)
        width = manifest.get("linewidth_rendered_Hz") or manifest["linewidth_Hz"]
        with h5py.File(seed_dir / "dataset.h5", "r") as h5:
            test = h5["test"]
            freqs = test["frequencies"][:].astype(float)
            for i in range(test["spectra"].shape[0]):
                if max_sequences and len(seqs) >= max_sequences:
                    return seqs
                seqs.append(dict(id=(seed_dir.name, i), spectra=test["spectra"][i].astype(float),
                                 B_true=test["B_true"][i].astype(float), freqs=freqs, width=width,
                                 bias=bias, dt_s=manifest["dt_s"], resonance0=test["resonance_freqs"][i, 0].astype(float)))
    return seqs


def fmt(x, p=3):
    return "nan" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{p}f}"


def write_md(results, path):
    L = [f"# Comparison study results: {results['partition']} v{results['version']}", "",
         f"Date {results['date']}; commit {results['git']['commit']} (dirty={results['git']['dirty']}).", ""]
    for name, cell in results["cells"].items():
        L += [f"## Cell {name} (n={next(iter(cell['stats'].values()))['n_sequences']}, md5 {cell['data_md5']['computed']}, manifest match {cell['data_md5']['match']})", "",
              "| Est | RMSE mT | AE mean deg | AE p90 deg | mag bias mT | lock | lost | nonfinite fr | seq w/ nonfinite | lat med us | lat p90 us |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for e, s in cell["stats"].items():
            L.append(f"| {e} | {fmt(s['rmse_mean_mT'])} | {fmt(s['ae_mean_deg'],2)} | {fmt(s['ae_p90_of_seq_p90_deg'],2)} | "
                     f"{fmt(s['mag_bias_mean_mT'])} | {fmt(s['lock_frac_mean'])} | {fmt(s['lost_rate'])} | "
                     f"{s['nonfinite_frames']} | {s['sequences_with_nonfinite']} | {fmt(s['latency_us_median'],0)} | {fmt(s['latency_us_p90'],0)} |")
        L += ["", "| Pair (A-B) | dRMSE mT [95% CI] | dAE p90 deg [95% CI] |", "|---|---|---|"]
        for k, p in cell["pairs"].items():
            r, a = p["rmse_diff_ci95_mT"], p["ae_p90_diff_ci95_deg"]
            L.append(f"| {k} | {fmt(p['rmse_diff_mT'])} [{fmt(r[0])}, {fmt(r[1])}] | {fmt(p['ae_p90_diff_deg'],2)} [{fmt(a[0],2)}, {fmt(a[1],2)}] |")
        L.append("")
    if "decision" in results:
        d = results["decision"]
        L += ["## Decision", "", f"Outcome: {d['outcome']}", f"Qualifying: {d['qualifying']}", ""]
    Path(path).write_text("\n".join(L) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--partition", choices=("dev", "val", "final"), required=True)
    ap.add_argument("--cells", default="all")
    ap.add_argument("--estimators", default=",".join(ESTIMATORS))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cpu", type=int, default=None)
    ap.add_argument("--version", type=int, default=1)
    ap.add_argument("--rerun-reason", default=None)
    ap.add_argument("--max-sequences", type=int, default=0, help="first N sequences per cell (0 = all); never for final")
    args = ap.parse_args(argv)
    if args.cpu is not None and hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {args.cpu})
    est = [e for e in args.estimators.split(",") if e]
    if any(e not in ESTIMATORS for e in est):
        raise SystemExit(f"estimators must be from {ESTIMATORS}")
    if args.partition == "final" and args.max_sequences:
        raise SystemExit("--max-sequences is not allowed for final")
    manifest_path = ROOT / f"docs/comparison_test_v{args.version}.manifest.json"
    manifest = json.loads(manifest_path.read_text())
    data_dir = ROOT / f"data/comparison_test_v{args.version}/{args.partition}"
    results_path = args.out / "results.json"
    check_partition_guard(args.partition, data_dir, manifest, ROOT / CHOICE_FILE, results_path,
                          args.rerun_reason, args.version)
    manifest_cells = {c["name"]: c for c in manifest["partitions"][args.partition]["cells"]}
    names = list(manifest_cells) if args.cells == "all" else args.cells.split(",")
    for n in names:
        if n not in manifest_cells:
            raise SystemExit(f"unknown cell {n}")
    runner = Runner(est)
    warmed = set()
    results = {"partition": args.partition, "version": args.version, "estimators": est,
               "date": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "git": git_info(), "environment": environment(args.cpu), "estimator_identity": runner.identity,
               "protocol": "docs/comparison_study_protocol_2026-10.md (Addendum (b) failure accounting)",
               "max_sequences": args.max_sequences or None, "rerun_reason": args.rerun_reason,
               "manifest_sha256": sha256_file(manifest_path), "cells": {}}
    t0 = time.time()
    for name in names:
        seqs = load_cell(data_dir / name, args.max_sequences)
        md5 = cell_md5(data_dir / name)
        data_md5 = {"computed": md5, "manifest": manifest_cells[name]["data_md5"],
                    "match": md5 == manifest_cells[name]["data_md5"]}
        rows = {e: [] for e in est}
        times = {e: [] for e in est}
        for e in est:
            if e not in warmed:                  # one-sequence warm-up, discarded
                s = seqs[0]
                runner.run(e, s["spectra"], s["freqs"], s["width"], s["bias"], s["resonance0"])
                warmed.add(e)
            for s in seqs:
                try:
                    raw, ft = runner.run(e, s["spectra"], s["freqs"], s["width"], s["bias"], s["resonance0"])
                    err = None
                except Exception as exc:         # a crash is an all-missing sequence, never a drop
                    raw, ft, err = np.full((len(s["spectra"]), 3), np.nan), np.zeros(0), repr(exc)
                row = score_sequence(s["B_true"], raw, s["bias"], s["dt_s"])
                row.update(replicate=s["id"][0], sequence_index=s["id"][1], error=err)
                rows[e].append(row)
                times[e].extend(np.asarray(ft).tolist())
        stats = {e: cell_stats(rows[e], times[e]) for e in est}
        pairs = (paired_bootstrap({e: [r["rmse_mT"] for r in rows[e]] for e in est},
                                  {e: [r["ae_p90_deg"] for r in rows[e]] for e in est})
                 if len(est) > 1 else {})
        keep = ("replicate", "sequence_index", "rmse_mT", "ae_mean_deg", "ae_p90_deg", "mag_bias_mT",
                "lock_frac", "lost", "nonfinite_frames", "n_valid_frames", "error")
        results["cells"][name] = {"rung": manifest_cells[name]["rung"], "data_md5": data_md5,
                                  "stats": stats, "pairs": pairs,
                                  "rows": {e: [{k: r[k] for k in keep} for r in rows[e]] for e in est}}
        print(f"[cell {name}] n={len(seqs)} md5_match={data_md5['match']} "
              + " ".join(f"{e}:rmse={stats[e]['rmse_mean_mT']:.3f}mT,p90={stats[e]['ae_p90_of_seq_p90_deg']:.2f}deg,lost={stats[e]['lost_rate']:.2f}" for e in est)
              + f" ({time.time()-t0:.0f}s)", flush=True)
    if args.partition == "final":
        choice = json.loads((ROOT / CHOICE_FILE).read_text())
        results["best_classical"] = choice["choice"]
        needed = {"E2", "E3", "E4"}
        if needed <= set(est) and {"clean", "realistic"} <= set(names):
            results["decision"] = decide(results)
    args.out.mkdir(parents=True, exist_ok=True)
    if results_path.exists():                    # a rerun never overwrites: keep the earlier file
        results_path.rename(args.out / f"results.superseded-{int(time.time())}.json")
    results_path.write_text(json.dumps(results, indent=1, default=str) + "\n")
    write_md(results, args.out / "results.md")
    print(f"wrote {results_path}")
    return results


if __name__ == "__main__":
    main()
