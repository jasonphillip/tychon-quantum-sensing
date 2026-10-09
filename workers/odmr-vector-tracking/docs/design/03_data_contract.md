# 03 — Shared data contract (v1), consumer side

**Status:** v1, reconciled against the **real upstream output** (the `nv-sensor-sim` time-series
generator is built and a dataset exists on disk). `nv-sensor-sim` **produces**;
`odmr-vector-tracking` **consumes**.

**Authoritative producer specs** (this doc is the consumer-side mapping, not the source of truth):
- `nv-sensor-sim/docs/dataset-contract.md` → "HDF5 Layout — Time-Series (Sequence) Datasets"
- `docs/design/03_upstream_contract_v1.md` (the producer session's consumer-facing summary)

Consumer implementation here:
- validator — `src/odmr_vector_tracking/data/contract.py`
- loader — `src/odmr_vector_tracking/data/loaders.py` (`SequenceDatasetLoader`)
- synthetic fixtures (a MOCK conforming to this schema) — `tests/fixtures/synthetic.py`
  (CLI: `scripts/make_fixture.py`)

## HDF5 layout

`N` = sequences, `T` = frames, `F` = MW points, `L` = resonances. Per split group
`/{train,val,test}`:

| dataset | dtype | shape | meaning |
|---|---|---|---|
| `spectra` | float32 | `(N, T, F)` | normalized PL time-series (~1 off-resonance) |
| `frequencies` | float32 | `(F,)` | MW frequency axis (Hz) |
| `B_true` | float32 | `(N, T, 3)` | ground-truth lab-frame B (Tesla) per frame |
| `resonance_freqs` | float32 | `(N, T, L)` | **diagonalized** line centers (Hz) per frame |
| `line_axis` | int8 | `(N, T, L)` | NV axis id 0–3 (association ground truth); `ℓ // 2` |
| `line_transition` | int8 | `(N, T, L)` | 0 = ms0→−1, 1 = ms0→+1 (even ℓ = 1, odd ℓ = 0) |
| `collision_mask` | bool | `(N, T)` | any two resonances within k·Γ this frame |
| `line_collision` | bool | `(N, T, L)` | **[v1]** each line within k·Γ of another |
| `seeds` | int64 | `(N,)` | **[v1]** per-sequence RNG seed |

Plus **one top-level dataset** (not per-split):

| dataset | dtype | shape | meaning |
|---|---|---|---|
| `/bias` | float32 | `(3,)` | static bias vector (Tesla) = `bias_B0_T · normalize(bias_direction_uvw)` |

Line index `ℓ` matches `nv_geometry_matrix()` row `ℓ`. `L = 8` electronic now; `L = 24` reserved
for ¹⁴N hyperfine (would add a `line_mI` field — deferred; coordinate before enabling).

## Manifest (`manifest.json`) — actual upstream field names

Provenance `generator_git_sha`, `config_hash`, `generated_at`, `backend`,
`simos_version`/`qutip_version`; seeds `master_seed`, `train_seeds`/`val_seeds`/`test_seeds`
(pairwise-disjoint; per-sequence `seeds` ⊆ the split's list); split sizes
`n_spectra_train`/`n_spectra_val`/`n_spectra_test`; temporal/spectral `sequence_mode`,
`n_timesteps`, `dt_s`, `n_lines`, `hyperfine`, `linewidth_Hz` (Γ),
`collision_threshold_linewidths` (k), `n_freq_points` (F), `freq_range_Hz` (start, stop);
bias `bias_B0_T`, `bias_direction_uvw` (raw `[uvw]`, **not normalized**); `sweep_description`;
`units`. `contract_version` is optional (the upstream manifest does not carry it; if present it
must be `"v1"`).

## Consumer notes (physics)

- **Diagonalized centers — invert the splitting, not `f − D`.** `resonance_freqs` are the true
  dip positions from SimOS diagonalization, carrying a second-order common-mode shift
  `Δf ≈ 1.5·(γ·B⊥)²/D` (3–16·Γ even in the few-mT regime — verified to ~0.1% against the real
  data). Recover each axis projection from the **splitting** `(f₊ − f₋)/2 = γ·(B·n_i)`: the
  common-mode cancels exactly, and it is **first-order accurate** — a small 2nd-order *asymmetric*
  residual (≲ 0.4·Γ, measured ~0.35·Γ on `sequence_sanity_v0`) remains, the source of the ~0.08%
  per-axis γ scatter. Then 4 projections → BLUE. Implemented in
  `vector.geometry.axis_projections_from_resonances` + `vector.blue.blue_invert_field`. (The full
  8-line `(f − D)` lstsq is also robust — the symmetric common-mode cancels in the antisymmetric
  ± pairing — but a single-transition `f − D` is biased.)
- **For exact ground-truth projection labels (metrics/training), use `B_true·n_i`** — `B_true` is
  stored, so exact per-axis projections need no spectral reconstruction. Use the splitting only for
  what the model *observes* from `spectra`.
- **Association ground truth** is `line_axis` / `line_transition`. Score association accuracy and
  ID-switch rate on `line_collision`-flagged lines (the hard regime).
- **First-order labels caveat:** valid in the compact few-mT regime; do not assume validity toward
  ~50 mT (ESLAC/GSLAC nonlinearity — see `00_problem.md`).

## Reconciliation log — discrepancies vs. the orchestrator's prose contract

The integration interface as initially paraphrased differed from the real producer output; the
consumer was reconciled to the **actual upstream** (and flagged here for the orchestrator):

1. **`/bias` is top-level**, not a per-split dataset. (Validator/loader accept top-level, with a
   per-split fallback for back-compat.)
2. **`resonance_freqs` are diagonalized** (common-mode shift), not first-order analytic. BLUE
   inverts the splitting; the synthetic fixtures add the common-mode term.
3. **Manifest names:** `n_spectra_*` (not `n_sequences_*`), `freq_range_Hz` (not `mw_window_Hz`);
   `contract_version` is absent upstream (made optional).
4. **`bias_direction_uvw` is the raw `[uvw]`** (non-unit); validator requires only nonzero norm,
   loader normalizes (`bias = bias_B0_T · normalize(uvw)`), matching top-level `/bias`.

Verified: `validate_dataset_dir`, `SequenceDatasetLoader`, and the classical baseline all run on
the real `sequence_sanity_v0` dataset; the baseline loses per-axis lock at the labeled crossings
(Increment-1 result on real data). The real dataset is a local gitignored artifact, so the
committed real-data contract test (`tests/contract/test_real_dataset_contract.py`) stays
env-driven (`ODMR_VT_REAL_DATASET`) for 3-machine portability.
