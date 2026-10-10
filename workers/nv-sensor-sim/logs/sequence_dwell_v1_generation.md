# sequence_dwell_v1 / sequence_dwell_v1_cues — generation run log

**Dispatch:** `tychon-verification-workbench/tvw/audits/dispatch-nvsim-identity-physics-2026-07-07.md`
**Session:** nv-sensor-sim on ws2, 2026-07-07.
**Branch:** `feat/dwell-identity-lineage` (created from `feat/sequence-generator` HEAD `07ed894`).

## Pre-flight
- Environment: ws2's conda base lacked `simos`/`qutip` (not migrated from the
  decommissioned ws1). Installed the archived-matching pins `qutip==5.2.3`,
  `simos==0.2.3` (numpy already 2.4.2). All local compute.
- Baseline test suite: **165 passed, 4 skipped** (green before changes).
- v1 pins read from the archived v1 manifest (read-only), resolved via the
  **nv-sensor-sim** archive (the odmr-vector-tracking archive path in the
  dispatch is the dangling symlink it warned about):
  `~/archives/ws1-projects-2026-07-05/nv-sensor-sim/artifacts/datasets/sequence_train_v1/manifest.json`
  (dataset.h5 md5 `bf83440ea36f38d0fe6c70c31881c174`):
  - `freq_range_Hz = [2667390522.8636284, 3074609477.1363726]`, `n_freq_points = 951`
  - `bias_B0_T = 0.005`, `bias_direction_uvw = [0.2, 0.1, 1.0]`
  - `linewidth_Hz = 1501174.797659018` (Gamma ~ 1.501 MHz), contract v1
  - contrast ladder `[1.0, 0.85, 0.7, 0.55]`, drift std 0.05, tau 64 frames

## DESIGN DEVIATION (flagged for review) — NV mirror symmetry vs "one coalescing pair"

The dispatch specifies **exactly one coalescing line pair** per sequence with the
**six** non-colliding lines separation-protected. This is **physically impossible**
in the noiseless L=8 model, and I verified it three ways (see
`physics.cross_relaxation` grounding + scratchpad scans):

- The per-axis spectrum depends only on `(|B.n_i|, B_perp,i)`. At any cross-axis
  frequency degeneracy `f_p = f_q`, the first-order condition forces
  `|B.n_i| = |B.n_j|`, which forces `B_perp,i = B_perp,j` (same `|B|`, same
  projection magnitude), hence identical per-axis Hamiltonians — so the **mirror
  pair** `(p^1, q^1)` (the other transition of each axis) coalesces
  **exactly and simultaneously** at the reflected frequency. Direct
  diagonalization shows the mirror separation is `0.000 MHz` at every merge.
- A full field scan (±2.5 mT external along the merge direction, all cross-axis
  pairs) finds **no** point where the target pair is within Gamma while the
  mirror exceeds 2 Gamma inside the pinned window. The second-order shift
  difference is too weak to resolve the mirror within the envelope.
- This is exactly the **cross-relaxation resonance condition** (Espinos & Budker
  arXiv:2512.13835 Eq. 3, `|B.n_i| = |B.n_j|`): a cross-axis merge *is* an
  inter-orientation degeneracy.

**Resolution (physically honest, not invented):** each dwell sequence realizes
**one cross-axis degeneracy event = a target coalescing pair `(p,q)` + its
NV-symmetry mirror pair `(p^1,q^1)`**, coalescing at the two reflected
frequencies `f+/-`, with the **four spectator lines** (the other two axes)
separation-protected. This matches real NV C3v symmetry and unifies with the CR
marker. Per-sequence `exit_topology` and `dwell_frames` refer to the target
pair; the mirror pair is recorded alongside. Building an artificial single-pair
merge would require inventing unphysical asymmetry, which the dispatch forbids.
**The deviation from "six protected" to "four protected" is inherent to the
physics; regenerate with a different merge design if a different structure is
required.**

## Physics cues — grounding (all sources verified in the local `odmr-pnt-nv-docs` corpus)

- **`axis_offsets_hz` (per-axis static strain / E-field ZFS ladder).** A common-mode
  per-orientation ZFS shift: both transitions of an axis move by `delta_i`, so the line
  center moves but the split is preserved -> invisible to the splitting-based decode, a
  static center-only identity fingerprint recoverable by integrating a long dwell.
  Default cues values = Meneses M_z fit `(19.6, -4.2, -3.5, -11.9) kHz`. **Caveat:** the
  cited arXiv:2502.14683 has a *title collision* with an object-tracking paper (2026-07-02
  TVW memo, Tier 4); the values are used as the per-axis strain ladder, the physics
  (per-orientation axial-strain ZFS shift) is standard NV and citation-independent.
- **`nv_density_ppm` (NV-NV cross-relaxation PL feature).** Resonance condition = inter-
  orientation degeneracy `|B.n_i|=|B.n_j|` (Espinos & Budker arXiv:2512.13835 Eq. 3;
  phenomenological Lorentzian-dip model Eq. 8); mechanism confirmed by Wickenbrock/Budker
  arXiv:1505.02253 (T1 shortens at inter-orientation degeneracy, amplitude scales with
  density). Density calibration = Dhungel arXiv:2301.09666 two points (3.8 ppm -> 0.78 mT
  FWHM / ~1.79 %; 16 ppm -> 1.42 mT / 3.95 %; visible >~0.9 ppm), power-law interpolated.
  Rendered as extra PL dips at the degenerate transition frequencies (does NOT add lines
  to `resonance_freqs`); a merge marker, identity value measured downstream not asserted.
  Modeling choices documented in `docs/dataset-contract.md` and
  `src/nv_sensor_sim/physics/cross_relaxation.py`. **Cited sources were sufficient to
  ground the model credibly — stop-condition 2 not triggered.**

## Results (generated 2026-07-07 on ws2, all local)

Environment: numpy 2.4.2, simos 0.2.3, qutip 5.2.3 (match the archived v1 lineage).
Test suite green throughout: **188 passed, 4 skipped** (165 baseline + 23 new).

- **`sequence_dwell_v1`** (cues OFF): 288 sequences (test split), T=256, 951-pt pinned grid.
  Realized dwell = target **exactly** for all 12 (D, topology) buckets; four spectators
  never within Gamma; exit topology balanced 24/24 cross/bounce per D bucket. Rendered in
  105 s. `config_hash 1abb3b21e1f8`; content `data_md5 f84d40ea98d173ec135c360909788a2a`;
  raw `dataset.h5` md5 `41509ee65d68e652d3d1b10418188908`.
- **`sequence_dwell_v1_cues`** (strain ON + 3.8 ppm): seed-paired to `sequence_dwell_v1`
  (**`B_true` and `seeds` byte-identical** — verified), cues shift the labels (per-axis
  center shifts `[19584, -4096, -3584, -12032] Hz` ~ Meneses, float32-quantized) and the
  spectra (dwell-frame PL dip deepens `0.9955 -> 0.9769`, the ~1.79 % CR marker). Rendered
  in 109 s. `config_hash 0788efed53e6`; content `data_md5 30642d11a1b18a91b6be1983d8b46c82`;
  raw `dataset.h5` md5 `29aa923526273d1e7e485fac0658ea1b`.

**Determinism check (pre-flight):** regenerating a dataset with the same seed reproduces the
content `data_md5` identically (verified in the mini-run and the `test_dwell_pipeline`
smoke test — cues-off generation is byte-identical across runs). The content md5 is used
rather than the raw HDF5 file md5 because HDF5 embeds per-object timestamps.

**Knob byte-identity:** with both cues off the generation is byte-identical to the same
call without the knob code path (offset=None / density=0 short-circuit); covered by the
render-level tests (`test_axis_offsets`, `test_cross_relaxation`, `test_render_sequence_knobs`)
and the dwell smoke test.
