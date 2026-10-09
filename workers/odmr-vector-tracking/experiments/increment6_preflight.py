"""Increment-6 pre-flight — consumer-side verification of the v3 coverage handoff.

Verifies `data/sequence_train_v3` + `data/sequence_eval_fieldcone_v1` against the nv-sim
handoff (`data/sequence_train_v3_HANDOFF.md`) and the TVW dispatch-6 GO (audit Addendum C)
BEFORE any training or scoring — dispatch stop-and-report condition 1 (md5 mismatch or
manifest/contract surprise) is decided here.

Checks: raw dataset.h5 md5s vs the handoff table (bit-identical delivery) + manifest
`data_md5` vs the dispatch/handoff values; dataset contract; split counts; the 951-point grid
pinned to v1; seed disjointness vs v1/v2 and across the new pair; cues-OFF manifest purity;
coverage aggregates recomputed from the label arrays vs both the manifest and handoff prose.

NOTE on `data_md5`: it is a generation-side determinism signal (nv-sim `datasets/hashing.py`:
same seed -> same digest on regeneration) hashed over the IN-MEMORY arrays; `DatasetWriter`
casts to the contract dtypes at write time, so the digest is NOT recomputable from the
delivered h5 (verified: recomputation from the h5 yields a different digest while the raw
file md5 matches the handoff bit-for-bit). Consumer-side integrity = raw-file md5 chain,
same convention as the increment-5 dwell handoff table.

    python experiments/increment6_preflight.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import h5py
import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = _REPO_ROOT / "data"

from odmr_vector_tracking.data.contract import validate_dataset_dir  # noqa: E402

# TVW dispatch-6 GO / handoff-note expectations (Addendum C, TVW db107c9).
EXPECTED = {
    "sequence_train_v3": {
        "data_md5": "be28fab5a129ff3b757ce77a92e60b47",
        "raw_md5": "f32bcd72b7bf6f5eaf0125853b03fcb4",
        "splits": {"train": 2048, "val": 512, "test": 512},
    },
    "sequence_eval_fieldcone_v1": {
        "data_md5": "92dc06692d1975f6fcd101e70cc02d99",
        "raw_md5": "b152cb6bd1b5090b54389f6404856c23",
        "splits": {"test": 120},
    },
}
def raw_md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    failures: list[str] = []

    def check(ok: bool, msg: str) -> None:
        print(("  [ok] " if ok else "  [FAIL] ") + msg)
        if not ok:
            failures.append(msg)

    seeds_by_ds: dict[str, np.ndarray] = {}
    for name in ("sequence_train_v1", "sequence_train_v2"):
        with h5py.File(DATA / name / "dataset.h5", "r") as f:
            seeds_by_ds[name] = np.concatenate(
                [f[f"{s}/seeds"][:] for s in f.keys() if isinstance(f[s], h5py.Group)])

    for name, exp in EXPECTED.items():
        d = DATA / name
        print(f"\n== {name} ==")
        m = validate_dataset_dir(d)  # raises on contract violation
        print("  [ok] dataset contract validates")
        manifest = json.loads((d / "manifest.json").read_text())

        with h5py.File(d / "dataset.h5", "r") as f:
            splits = {s: int(f[f"{s}/spectra"].shape[0])
                      for s in f.keys() if isinstance(f[s], h5py.Group)}
            check(splits == exp["splits"], f"split counts {splits} == {exp['splits']}")
            check(manifest.get("data_md5") == exp["data_md5"],
                  f"manifest data_md5 {manifest.get('data_md5')} == dispatch/handoff "
                  f"{exp['data_md5']}")
            T = next(f[f"{s}/spectra"] for s in splits).shape[1]
            check(T == 256, f"T={T} == 256")
            with h5py.File(DATA / "sequence_train_v1" / "dataset.h5", "r") as fv1:
                v1_freq = fv1["train/frequencies"][:]
            freq = f[f"{next(iter(splits))}/frequencies"][:]
            check(freq.shape == (951,) and np.array_equal(freq, v1_freq),
                  "951-point frequency grid pinned to v1 (exact array equality)")
            ds_seeds = np.concatenate([f[f"{s}/seeds"][:] for s in splits])
            check(len(np.unique(ds_seeds)) == len(ds_seeds), "per-sequence seeds unique")
            for other, oseeds in seeds_by_ds.items():
                inter = np.intersect1d(ds_seeds, oseeds)
                check(inter.size == 0, f"seeds disjoint from {other} ({inter.size} shared)")
            seeds_by_ds[name] = ds_seeds

        rgot = raw_md5(d / "dataset.h5")
        check(rgot == exp["raw_md5"], f"raw dataset.h5 md5 {rgot} == handoff {exp['raw_md5']}")
        check(manifest.get("axis_offsets_hz") in (None,), "cues OFF: axis_offsets_hz is null")
        check(manifest.get("nv_density_ppm") in (None,), "cues OFF: nv_density_ppm is null")
        check(manifest.get("contract_version") == "v1", "contract_version == v1")
        del m

    print("\n== v3 coverage aggregates (recomputed from label arrays vs handoff) ==")
    with h5py.File(DATA / "sequence_train_v3" / "dataset.h5", "r") as f:
        ang = f["train/max_offbias_angle_deg"][:]
        minb = f["train/min_B_T"][:]
        dti = f["train/directed_template_idx"][:]
        sm = f["train/start_mode"][:]
        check(abs(float(ang.max()) - 65.5) < 0.1, f"train max off-bias {ang.max():.1f}° ≈ 65.5°")
        check(abs(float(np.mean(ang >= 53.2)) - 0.076) < 0.005,
              f"frac ≥53.2° {np.mean(ang >= 53.2):.3f} ≈ 0.076")
        check(abs(float(np.mean(ang >= 60.0)) - 0.023) < 0.005,
              f"frac ≥60° {np.mean(ang >= 60.0):.3f} ≈ 0.023")
        check(abs(float(minb.min()) * 1e3 - 3.01) < 0.05,
              f"|B| floor {minb.min() * 1e3:.2f} mT ≈ 3.01 mT")
        check(abs(float(np.mean(dti >= 0)) - 0.278) < 0.005,
              f"directed fraction {np.mean(dti >= 0):.3f} ≈ 0.278")
        cold = float(np.mean(sm[sm >= 0] == 0))
        check(abs(cold - 0.531) < 0.01,
              f"cold-start fraction of angle-stratified {cold:.3f} ≈ 0.531")
        fam = f["train/sampling_family"][:]
        check(set(np.unique(fam)) <= {0, 1, 2, 3, 4}, f"sampling_family codes {set(np.unique(fam))}")
        check(set(np.unique(sm)) <= {-1, 0, 1}, f"start_mode codes {set(np.unique(sm))}")
        d_tmpl = set(np.unique(dti[dti >= 0]))
        print(f"  directed templates present: {sorted(d_tmpl)}")

    print("\n== fieldcone bucket structure ==")
    with h5py.File(DATA / "sequence_eval_fieldcone_v1" / "dataset.h5", "r") as f:
        bc = f["test/bucket_class"][:]
        rang = f["test/realized_max_offbias_angle_deg"][:]
        rb = f["test/realized_min_B_T"][:] * 1e3
        p, q = f["test/merge_pair_p"][:], f["test/merge_pair_q"][:]
        counts = {int(c): int((bc == c).sum()) for c in np.unique(bc)}
        check(set(counts) == {0, 1, 2}, f"bucket classes {counts} (0 failure/1 control/2 beyond)")
        check(9.5 <= float(rang.min()) and float(rang.max()) <= 70.5,
              f"realized angles {rang.min():.1f}–{rang.max():.1f}° within 10–70°")
        check(1.9 <= float(rb.min()) and float(rb.max()) <= 5.1,
              f"realized |B| {rb.min():.2f}–{rb.max():.2f} mT within 1.98–5.0")
        pairs = {(int(a), int(b)) for a, b in zip(p[bc == 0], q[bc == 0])}
        check(pairs <= {(0, 2), (4, 6)}, f"failure-bucket merge pairs {pairs} ⊆ {{(0,2),(4,6)}}")
        check(bool(np.all(p[bc != 0] == -1)) and bool(np.all(q[bc != 0] == -1)),
              "merge pairs are -1 off the failure buckets")
        with h5py.File(DATA / "sequence_train_v3" / "dataset.h5", "r") as f3:
            check(np.array_equal(f["bias"][:], f3["bias"][:]),
                  "fieldcone bias vector == v3 bias vector")

    if failures:
        print(f"\n[preflight] FAILED — {len(failures)} check(s): stop-and-report per dispatch")
        return 1
    print("\n[preflight] ALL CHECKS PASS — §2 execution may proceed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
