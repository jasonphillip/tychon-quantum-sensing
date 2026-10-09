# Landscape + IP


## Niche assessment

- **Umbrella space (NV vector magnetometry for nav/defense/space): crowded and hot** — 10+
  companies, multiple national programs, several 2026 papers.
- **The specific niche (robust closed-loop *vector* tracking through resonance crossings, with
  ML): open.** The crossing/association failure is recognized but fixed only classically; no ML
  through-crossing tracker exists (see `design/01_research_findings.md`).

## Players (most relevant first)

**Academic / national lab**
- **MIT Lincoln Lab (Braje) + Englund/MIT** — originators of closed-loop high-DR *vector*
  (Clevenson 2018); airborne vector MagNav. Closest to this problem.
- **USTC (Du/Rong)** — only *deployed* PID frequency-locked vector (deep-sea, 5 mT bias; Natl.
  Sci. Rev. 2025).
- **Stuttgart (Wrachtrup)** — newest locking + hopping high-DR vector (APL 2026).
- **Mainz/Berkeley (Budker/Wickenbrock/Zheng)** — highest-*field* vector (GSLAC 102.4 mT, MW-free;
  architecturally *avoids* crossings).
- **UMD (Walsworth)** — highest-sensitivity full vector (Schloss 2018). **UNM (Acosta) / ODMR
  Technologies** — Earth-field vector via flux concentrators ("spectral congestion"). **McGill
  (Childress) / SBQuantum** — bias-field-*free* vector (avoids crossings by design).

**Companies (NV diamond)**
- **SBQuantum (CA)** — strongest NV *vector* nav/space/defense pure-play; ~400 pT/√Hz, <5 nT
  heading; LEO satellite ~Mar 2026 (NGA MagQuest). Uses ML for *platform-noise compensation*, not
  line tracking. Plausible collaborator.
- **Q.ANT (DE)** — Q.M 10, the only *published* vector specs: 10 pT/√Hz, **±500 µT dynamic**,
  Earth-field-native (avail. Apr 2025). The commercial benchmark to beat — and an IP-adjacent
  party (see below).
- **Lockheed Martin "Dark Ice"** — vector, "very large dynamic range"; CW swept + bias-to-separate
  (status quiet since ~2019 — unverified).
- Others: Bosch (+ Element Six JV), Thales (ASTERIQs), CIQTEK, Quantum Brilliance, QuantumDiamonds
  /EuQlid (chip inspection), Qnami/QZabre (scanning imaging), Adámas/Element Six/Diatope
  (materials).

**Correction (not NV — do not list as NV competitors):** **Q-CTRL "Ironstone Opal"** and
**SandboxAQ "AQNav"** use *scalar optically-pumped alkali-vapor* magnetometers (+ classical
fluxgate for vector). They are MagNav competitors, not NV competitors.

## IP to watch

- **MIT US11346904B2** (priority 2016, granted 2022) — *prospectively* claims an "8-channel
  magnetometer … robustly tracking the magnetic field through ambiguous crossover points," to the
  full >1 T range. "May/can" language, **no reduction to practice**, and the *classical*
  overdetermined-redundancy mechanism. An ML data-association/state-estimation tracker looks
- **Lockheed US11187765B2** — dynamic-range extension via **quadrature/SMAC** curves (classical).
- **Q.ANT JP2025518254A** — "automatic resonance control for NV magnetometers": closed-loop
  operating-point auto-adjustment to increase dynamic range. Nearest *control-side* prior art;
  not described as ML.
  not ODMR line tracking.

is inferred from a non-ML description; APL 2026 (5.0310526) and SBQuantum 2026 launch specs are
recent/press-reported — verify figures before external citation.
