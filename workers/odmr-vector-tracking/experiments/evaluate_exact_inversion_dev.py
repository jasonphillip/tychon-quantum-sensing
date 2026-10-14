"""Bounded Task 4 development check; refuses val/final and other dev cells."""
from __future__ import annotations
import os
for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[key] = "1"
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time
import importlib.metadata
import h5py
import numpy as np

from odmr_vector_tracking.tracking.exact_inversion_baseline import ExactInversionTracker
from odmr_vector_tracking.evaluation.rows import fieldcone_metrics_row
from odmr_vector_tracking.evaluation.metrics import full_vector_lock, full_vector_lock_stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--cpu", type=int, default=0)
    args = parser.parse_args()
    root = args.data.resolve()
    if root.parts[-4:] != ("comparison_test_v1", "dev", "clean", "seed_0"):
        raise SystemExit("This check only accepts comparison_test_v1/dev/clean/seed_0")
    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {args.cpu})
    manifest = json.loads((root / "manifest.json").read_text())
    bias = manifest["bias_B0_T"] * np.array(manifest["bias_direction_uvw"], dtype=float)
    bias /= np.linalg.norm(manifest["bias_direction_uvw"])
    linewidth = manifest.get("linewidth_rendered_Hz", manifest["linewidth_Hz"])
    start_wall, start_cpu = time.perf_counter(), time.process_time()
    with h5py.File(root / "dataset.h5", "r") as h5:
        grid = h5["test/frequencies"][:].astype(float)
        factory = lambda: ExactInversionTracker(grid, linewidth_Hz=linewidth, bias_field_t=bias)
        if args.pilot:
            tracker = factory()
            states = []
            for frame in h5["test/spectra"][0, :16]:
                states.append(tracker.step(frame))
            result = dict(mode="pilot", n_frames=16, wall_seconds=time.perf_counter()-start_wall,
                          cpu_seconds=time.process_time()-start_cpu,
                          n_finite=int(sum(np.isfinite(x.B_est).all() for x in states)),
                          acquisition=tracker.acquisition_diagnostics)
        else:
            warmup = factory()
            for frame in h5["test/spectra"][0]:
                warmup.step(frame)
            rows, times = [], []
            for index in range(h5["test/spectra"].shape[0]):
                tracker = factory()
                predicted, ambiguous, fit_failed = [], 0, 0
                for frame in h5["test/spectra"][index]:
                    tick = time.perf_counter()
                    state = tracker.step(frame)
                    times.append(time.perf_counter()-tick)
                    predicted.append(state.B_est)
                    ambiguous += int(state.ambiguous)
                    fit_failed += int(not state.fit_success)
                raw = np.array(predicted)
                missing = ~np.isfinite(raw).all(axis=1)
                scored = raw.copy()
                fallback = bias.copy()
                for t in range(len(scored)):
                    if missing[t]:
                        scored[t] = fallback
                    else:
                        fallback = scored[t].copy()
                # Truth is accessed only now, after inference for the whole sequence.
                true = h5["test/B_true"][index]
                row = fieldcone_metrics_row(true, scored, dt_s=manifest["dt_s"])
                lock = full_vector_lock(true, scored) & ~missing
                row.update(full_vector_lock_stats(lock))
                row["lost"] = bool(row["lost"] or missing.mean() > .1)
                row.update(sequence_index=index, n_valid_frames=int((~missing).sum()),
                           nonfinite_frames=int(missing.sum()), ambiguous_frames=ambiguous,
                           fit_failed_frames=fit_failed, acquisition=tracker.acquisition_diagnostics)
                rows.append(row)
                print(json.dumps({"sequence": index, "lock_frac": row["lock_frac"],
                                  "ae_p90_deg": row["ae_p90_deg"], "nonfinite": row["nonfinite_frames"]}), flush=True)
                if time.process_time()-start_cpu > 1800:
                    raise SystemExit("Task 4 CPU cap exceeded")
            result = dict(mode="development", n_sequences=len(rows), n_frames=len(times),
                          mean_lock_fraction=float(np.mean([r["lock_frac"] for r in rows])),
                          angular_p90_of_sequence_p90_deg=float(np.percentile([r["ae_p90_deg"] for r in rows],90)),
                          mean_sequence_rmse_T=float(np.mean([r["rmse_T"] for r in rows])),
                          lost_sequences=sum(r["lost"] for r in rows),
                          nonfinite_frames=sum(r["nonfinite_frames"] for r in rows),
                          sequences_with_nonfinite=sum(r["nonfinite_frames"] > 0 for r in rows),
                          latency_us_median=float(np.median(times)*1e6),
                          latency_us_p90=float(np.percentile(times,90)*1e6),
                          warmup_sequences=1, wall_seconds=time.perf_counter()-start_wall,
                          cpu_seconds=time.process_time()-start_cpu, rows=rows)
    result.update(data_directory=str(root), manifest_sha256=hashlib.sha256((root/"manifest.json").read_bytes()).hexdigest(),
                  data_sha256=hashlib.sha256((root/"dataset.h5").read_bytes()).hexdigest(),
                  python=platform.python_version(), machine=platform.machine(),
                  cpu_affinity=sorted(os.sched_getaffinity(0)) if hasattr(os,"sched_getaffinity") else None,
                  versions={n: importlib.metadata.version(n) for n in ("numpy","scipy","h5py","torch")},
                  thread_limits={k:os.environ[k] for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS")},
                  estimator_constants={"D_Hz": 2.871e9,"E_Hz":0.,"gamma_Hz_per_T":2.8035e10},
                  truth_use="scoring only after sequence inference", partition="dev", cell="clean", replicate="seed_0")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ("rows",)},indent=2))


if __name__ == "__main__":
    main()
