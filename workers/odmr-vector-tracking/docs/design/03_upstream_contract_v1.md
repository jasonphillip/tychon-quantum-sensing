# 03 — Upstream contract v1 (nv-sensor-sim time-series ODMR)

Status: **nv-sensor-sim Increment-1 is built.** The time-series generator (`field_trajectory`
→ `resonances` → `render` → sequence writer) emits HDF5 sequence datasets where a swept field
drags the NV-axis resonances across each other, with per-frame collision labels. The shared
data contract is **v1**. This doc is the consumer-facing summary; the authoritative layout is
`nv-sensor-sim/docs/dataset-contract.md` → "HDF5 Layout — Time-Series (Sequence) Datasets".

Fold the four points below into the **loader**, **synthetic fixtures** (`scripts/make_fixture.py`,
`src/odmr_vector_tracking/data/`), the **classical baseline** (`tracking/classical.py`), and the
**metrics** (`evaluation/`).

## 1. `resonance_freqs` are DIAGONALIZED line centers — not first-order/analytic

Each label is the **true dip position** from the SimOS diagonalization (it sits on the dip in
`spectra`). It is deliberately **not** the first-order projection `D + s·γ·(B·nᵢ)`. A transverse
field adds a second-order **common-mode** shift to *both* transitions of an axis:

```
Δf_common ≈ 1.5 · (γ·B⊥)² / D       # γ/2π ≈ 28.035 GHz/T, D ≈ 2.871 GHz
```

In the honest few-mT regime this is **not small**: ≈6.8 MHz at 5 mT along z, up to ≈24 MHz
off-axis — i.e. **3–16 linewidths** (Γ ≈ 1.5 MHz). First-order centers would sit that far off
the real dips. Consequences for this repo:

- **Recover each axis projection `B·nᵢ` from the SPLITTING, not the absolute center.** The
  half-difference of an axis's two lines cancels the common-mode shift:

  ```
  (f₊ − f₋) / 2 ≈ γ · (B·nᵢ)
  # common-mode cancels EXACTLY; a smaller 2nd-order ASYMMETRIC residual remains:
  # ≲ 0.4·Γ (a few hundred kHz) at the few-mT extremes — measured 0.35·Γ max on sequence_sanity_v0
  ```

  So the splitting is **first-order accurate, not exact**, but ~25× closer than an absolute
  center. Do **not** form `B·nᵢ` from `(f − D)` of a single line, and do **not** feed absolute
  centers into the BLUE A-matrix as pure first-order Zeeman shifts. Build the residual vector for
  `nv_geometry_matrix()` (8×3) from the per-axis splittings.
- **For exact ground-truth projections (labels / metrics), use `B_true·nᵢ`.** `B_true` is stored,
  so the exact per-axis projection needs no spectral reconstruction — score against `B_true·nᵢ`,
  and use the splitting only for what the model observes from `spectra`.
- **Synthetic fixtures MUST include the second-order common-mode center shift.** If a fixture
  places lines at first-order positions, the tracker/baseline trains against unrealistic centers
  and will mismatch real generated data. Either render via the upstream path, or add the
  `Δf_common` term per axis from `B⊥ = |B − (B·nᵢ)·nᵢ|`.

The per-line **association** (`line_axis`, `line_transition`) survives crossings because the
splitting's *sign and order* are first-order robust: the higher line is the `+γ(B·nᵢ)` transition,
which is ms0→+1 iff `B·nᵢ ≥ 0` (the small asymmetric residual never reorders the pair).

## 2. Units are SI

Frequencies in **Hz**, magnetic fields in **Tesla**, time in **seconds**. The generator never
emits GHz/mT. `resonance_freqs` are absolute ~2.6–3.2 GHz values stored as float32 (≈256 Hz
quantization ≪ Γ — fine; use the splitting, not raw precision, for projections).

## 3. `bias` is pinned in the lab frame

The static bias vector is `bias = bias_B0_T · normalize(bias_direction_uvw)`. The repo convention
aligns the diamond crystal [uvw] axes with lab xyz, so the `_uvw` direction is also the lab
direction. The top-level `/bias` (3,) dataset is this lab-frame vector; `B_true` already includes
it (`B_true = bias + swept_external(t)`).

## 4. L = 8 now; L = 24 (hyperfine) is reserved, not implemented

Current datasets are electronic-only: **L = 8** = 4 axes × 2 transitions, `hyperfine = false`.
When the ¹⁴N hyperfine triplet is enabled later, L = 24 and a per-component **`line_mI`**
(N, T, L) field is added to disambiguate the three components per (axis, transition) — keep
loader/model shapes parameterized on `n_lines` and leave room for `line_mI`; do not implement it
now.

## HDF5 layout (per split group `/{train,val,test}/`)

```
spectra          float32 (N, T, F)   normalized PL time-series (≈1 off-resonance)
frequencies      float32 (F,)        MW frequency axis (Hz)
B_true           float32 (N, T, 3)   ground-truth lab-frame B (Tesla) per frame
resonance_freqs  float32 (N, T, L)   diagonalized line centers (Hz) per frame
line_axis        int8    (N, T, L)   NV axis id 0–3   (ℓ // 2)
line_transition  int8    (N, T, L)   0 = ms0→−1, 1 = ms0→+1   (even ℓ = 1, odd ℓ = 0)
collision_mask   bool    (N, T)      any two lines within k·Γ this frame
line_collision   bool    (N, T, L)   which lines are within k·Γ of another  [v1 addition]
seeds            int64   (N,)        per-sequence seed                       [v1 addition]
/bias            float32 (3,)        static bias vector (Tesla), top-level
```

Manifest sidecar (`manifest.json`) adds: `contract_version` (`"v1"`), `sequence_mode`,
`n_timesteps` T, `dt_s`, `n_lines` L, `hyperfine`, `linewidth_Hz` Γ,
`collision_threshold_linewidths` k, `bias_B0_T`, `bias_direction_uvw`, `sweep_description`. Line
index ℓ matches `nv_geometry_matrix()` row ℓ.

`line_collision` and `seeds` are the **v1** additions beyond the initial contract: per-frame
`collision_mask` alone cannot tell the association head *which* lines are crossing, and the
per-sequence `seeds` preserve reproducibility.

## Reference sanity lineage

`sequence_sanity_v0`: 64 / 16 / 16 sequences × T = 128, ~5 mT bias + ≲±2 mT sweep, window
≈ 2.667–3.075 GHz, F = 951 (≈3.5 points/Γ). Every sequence contains ≥1 labeled inter-axis
crossing — enough to reproduce the classical lock-in/PID loss-of-lock (Increment 1). Regenerate:

```bash
# in nv-sensor-sim
python scripts/generate_sequence_dataset.py \
  --config configs/sequence_sanity_v0.yaml \
  --output-dir artifacts/datasets/sequence_sanity_v0/
```

> Trainable sets (later): keep `n_freq_points: null` so F is re-derived from Γ (holds ≈3.5
> points/Γ), or raise `aliasing_safety` to ~5 for comfortable center estimation. A fixed F with
> a smaller Γ degrades resolution (≈2.3 points/Γ at F = 951, Γ ≈ 1 MHz).
