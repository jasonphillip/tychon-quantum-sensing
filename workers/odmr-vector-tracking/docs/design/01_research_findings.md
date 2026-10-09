# 01 — Founding research findings

Distilled from a multi-agent literature + prior-art sweep (2026-06-29). Citations are collected
in `../references.md`. Two rounds: (A) can we recover vector at all, and (B) the dynamic-range /
crossing problem this repo targets.

## A. Recovering vector (the static regime) — background

**One governing variable: the resolving ratio R = γ|B| / Γ** (Zeeman separation ÷ linewidth;
γ ≈ 28 kHz/µT). At ~50 µT with CW lines, R ≈ 1 → the ~24 resonances cluster in ≲7 MHz, overlap,
and the Fisher-information matrix for *direction* goes near-singular → the ~57°/≈random collapse.
Need **R ≳ 10** to condition the 4-axis BLUE inversion. [2507.00215; 2311.06055]

**Fixes (raise R):** (i) a static **bias ~5 mT off-axis** spreads the 8 lines over hundreds of
MHz and breaks the 48-fold (O_h) sign/axis degeneracy [2504.20750; Schloss 2018]; (ii) narrow the
lines — **double-quantum Ramsey** (2× spacing + common-mode temperature/strain rejection) [Bauch
2018], pulsed/Ramsey, or ¹²C-purified low-N diamond; (iii) passive **flux concentrators** (ε≈19)
[2507.00215]. Once lines resolve, **classical BLUE is near-exact (~98 % of 4π, ≲0.2°)**, and every
2022–2026 NN full-vector demonstration first fixes acquisition, then applies even a small net.
**Conclusion: in the static regime the bottleneck is the physics input, not the model.**
[2606.02749; 2409.12820; 2603.14728]

## B. The dynamic-range / crossing problem (this repo)

### The failure mode is recognized — cite it, don't claim discovery
- **MIT Lincoln Lab — Clevenson et al., APL 112, 252406 (2018) / arXiv:1802.09713** (the
  foundational closed-loop vector paper): dynamic range "is limited by the **ambiguity when
  resonances of different NV orientation classes cross each other**," to be overcome "by
  simultaneously detecting along all four … directions and … the redundancy of the overdetermined
  system." Proposed, **never demonstrated** (they locked one axis at a time).
- **Loss-of-lock mechanism**: if the field moves more than **Γ/2 per loop cycle**, the loop
  "deviates from feedback" and the field "cannot be determined." [Micromachines 15, 662 (2024)]
- **Static ambiguity** formalized (16 sign × 24 axis-permutation = 48-fold) and solved only by
  *avoiding* degeneracy with a bias. [Lönard et al., PRR 2025 / arXiv:2504.20750]

### Classical state of the art (the baseline to beat)
- **Vector, real-time:** ±150–260 µT/axis [Liu 2024 (IEEE Sensors J. 24:14068); Fu 2025 (Opt.
  Express 33:22385)]. Highest-sensitivity vector: ~50 pT/√Hz/axis but small-field AC only
  [Schloss 2018]. Newest: locking + DDS hopping [Wang/Wrachtrup, APL 2026, 5.0310526].
- **Single-projection** closed-loop reaches ~4–6.4 mT (Clevenson 2018; Wang 2023; Micromachines
  2024) but tracks one line at a time.
- **Every classical method assumes resolved, correctly-ordered lines held apart by a bias, and
  breaks at a crossing.** The lock-in tracks a *frequency, not an identity*; hopping/sequential
  schemes re-acquire from a fixed spectral map and silently mis-assign if line order changes.
- **No classical method does real-time multi-line data association at collisions.** It is named
  analyzed only statically (Lönard 2025).

### ML prior art — the core niche is OPEN
- Closest: **Haim/Caruso, arXiv:2409.12820 (MLST 2025)** — an MLP predicts 8 resonance positions
  even through *overlapping* Lorentzians, in the large-DR regime. But it is **static,
  feed-forward, single-frame** — no temporal state, no cross-frame association, no closed loop;
  authors flag the overlap case as needing "further investigation."
- RL/learned control in NV exists only for pulses / decoupling / protocol selection — **never the
  lock-in/PID line-tracking loop.**
- **Not found anywhere:** a recurrent / transformer / KalmanNet / particle-filter tracker that
  holds NV *vector* lock *through* crossings. The niche is unclaimed (defensible as novel **iff**
  framed as sequential, closed-loop association-through-collisions, and vector — generic
  "ML for ODMR" is crowded).

### Transferable methods (mature, directly mappable) → see `02_approach_and_testbed.md`
Physics-informed recurrent filtering (**KalmanNet**, arXiv:2107.10043) for the known-Zeeman /
unknown-association split; **learned multi-target tracking with data association** that beats
classical filters as association complexity rises (Pinto/Wymeersch arXiv:2202.07909; MT3; DeepDA);
and the cleanest analogue, **multi-pitch / formant tracking through crossings** (US6453284; Liu &
Wang 2017) — exploit each axis's hyperfine triplet + Zeeman slope as the "fingerprint" that
re-identifies a line after a crossing.
