# 00 — The problem

## Two regimes, two different problems

NV vector magnetometry reads a full 3-component **B** by resolving the four crystallographic
⟨111⟩ axes (8 ODMR resonances = 4 axes × 2 transitions; 24 with the ¹⁴N hyperfine triplet) and
inverting their Zeeman shifts. Two distinct failure regimes share the symptom "lines overlap, so
direction is unrecoverable":

1. **Low-field congestion (static).** At Earth-field magnitudes (~20–70 µT) the Zeeman splitting
   (~1.4–2.8 MHz) is *below* typical CW-ODMR linewidths, so the 8 lines never separate. The
   spectrum→direction map is non-injective; a single-frame regressor recovers |B| (aggregate
   width) but not direction (~57° error ≈ random). **Fix:** add a known bias (~5 mT, off-axis)
   to resolve the lines, then invert (classical BLUE is near-exact once resolved). *This regime
   is `odmr-edge-ml`'s/`nv-sensor-sim`'s territory and is essentially solved by acquisition +
   classical math; ML adds little.*

2. **Dynamic-range / crossing (temporal) — THIS REPO.** With the bias present and lines
   resolved, a *large external field* drags the resonances until lines from **different axes
   cross** in frequency space. A lock-in + PID loop tracks a *frequency, not an identity*, so at
   the crossing it mis-associates the lines and **loses lock** — the control loop breaks. The
   conventional fix is a larger bias field (more spacing), at real hardware cost (magnet mass,
   heat, gradient-broadening that *worsens* sensitivity, drift) and conops constraints.

## Why this is the right problem to attack with ML

- The *static* inversion is a solved least-squares problem (BLUE) once lines resolve — so an ML
  model is largely redundant there. This is exactly why an earlier scalar-residual model added
  only ~5 % over a PID baseline: it was attacking the wrong regime.
- The *crossing* problem is a **sequential multi-target tracking / data-association** problem —
  temporal, ambiguous, control-coupled. That is squarely where learning beats fixed filters, and
  it is the function that justifies a learned block alongside the FPGA PID (the model does
  association/estimation; the PID does the fast loop; a safety layer bounds the model).

## The originating insight

The framing is Jason Phillip's own: conventionally the per-axis ODMR degeneracy is lifted by a
bias field and tracked with lock-in + PID; a large external field can shift the signatures until
they overlap again, at which point lock-in + PID cannot track the individual signatures and the
loop breaks; the obvious fix (bigger bias) carries hardware risk and limits conops; **using ML to
track through the overlaps was not something he had seen others consider.** A literature +
prior-art sweep (see `01_research_findings.md`, `../landscape_ip.md`) confirms that read: the
failure mode is recognized, but every published remedy is classical, and no ML through-crossing
tracker exists.

## Honest ceilings (do not overclaim)

The prize is *not* "arbitrarily large field." Physical walls: **ESLAC ~51 mT** (fluorescence /
contrast loss for off-axis fields), **GSLAC ~102.4 mT** (MW-ODMR contrast → 0; only MW-free
schemes operate above it), and transverse-field nonlinearity throughout (a ~1.5 µT accuracy floor
at 10 mT from g-factor uncertainty). The realistic, defensible target is **robust vector lock
through crossings in the ~few-mT-to-~50-mT regime.**
