# References

Founding citation set (2026-06-29 sweep). Verify figures before external citation; a few are
recent/press-reported (flagged). Intended to seed a local search corpus.

## Dynamic range, crossings, closed-loop tracking (core)
- Clevenson, Pham, Teale, Johnson, Englund, Braje. "Robust high-dynamic-range vector
  magnetometry with NV centers." *APL* 112, 252406 (2018). doi:10.1063/1.5034216 / arXiv:1802.09713.
  — states the inter-axis crossing ambiguity as the DR limit; proposes overdetermined fix.
- "High-Dynamic-Range Integrated NV Magnetometers." *Micromachines* 15, 662 (2024).
  doi:10.3390/mi15050662. — the Γ/2-per-cycle loss-of-lock rule.
- Lönard, Cardoso Barbosa, …, Widera. *Phys. Rev. Research* (2025). arXiv:2504.20750. — 48-fold
  static axis-assignment ambiguity; bias-to-separate resolution; g_NV accuracy floor.
- Wang, …, Wrachtrup. "High-dynamic-range vector magnetometry in solid-state systems." *APL*
  (2026). doi:10.1063/5.0310526. *(recent — verify)*
- Wang et al. *Rev. Sci. Instrum.* 94, 015109 (2023). arXiv:2209.11360. — frequency-agile FPGA lock.
- Liu et al. *IEEE Sensors J.* 24(9), 14068 (2024). doi:10.1109/jsen.2024.3374732. — vector hopping ±130/110/260 µT.
- Fu et al. *Opt. Express* 33(11), 22385 (2025). doi:10.1364/oe.548080. — 4-source simultaneous vector.
- Kumar et al. (Quantum MagPI). *Rev. Sci. Instrum.* 95, 075002 (2024). arXiv:2402.15748. — PI lock, 20× DR.

## Vector magnetometry, bias, protocols, materials (static regime)
- Schloss, Barry, Turner, Walsworth. *Phys. Rev. Applied* 10, 034044 (2018). arXiv:1803.03718. — multichannel lock-in vector, ~50 pT/√Hz/axis.
- Saleh Ziabari, …, Jarmola, Acosta. *Phys. Rev. Research* 7, 043044 (2025). arXiv:2507.00215. — spectral congestion, CRB, flux concentrator (ε≈19). **Key paper.**
- Bauch et al. *Phys. Rev. X* 8, 031025 (2018). arXiv:1801.03793. — double-quantum Ramsey.
- Barry et al. *Rev. Mod. Phys.* 92, 015004 (2020). arXiv:1903.08176. — ensemble NV review.
- Zheng et al. *Phys. Rev. Applied* 13, 044023 (2020). arXiv:1904.04361. — GSLAC (102.4 mT) MW-free vector.
- Chatzidrosos et al. *Front. Photonics* 2, 732748 (2021). arXiv:2102.11902. — ≥100 mT Halbach vector.
- Childress + SBQuantum. *PRX Quantum* (2025). arXiv:2505.24574. — bias-field-free Rabi-labeled vector.
- SBQuantum. arXiv:2509.19179 (2025). — LEO/drone vector, <5 nT heading. *(press/recent — verify)*
- Yu et al. (USTC). *Natl. Sci. Rev.* 12(4), nwae478 (2025). doi:10.1093/nsr/nwae478. — deep-sea FPGA-PID vector, 5 mT bias.

## ML for ODMR / NV (prior art)
- Haim, Martina, Howell, Bar-Gill, Caruso. "Machine-learning based high-bandwidth magnetic
  sensing." *Mach. Learn. Sci. Technol.* (2025). arXiv:2409.12820. — MLP predicts 8 peaks through
  overlapping Lorentzians; static/feed-forward. **Closest prior ML work.**
- Rieckmann et al. arXiv:2606.02749 (2026) — NN vector magnetometry, full vector at Earth field
  via broadband-MW dual polarization. **STATIC single-shot solver — no tracking / identity /
  crossing dynamics; cited to distinguish from this work's dynamic through-crossing tracking.**
- Yao et al. arXiv:2603.14728 (2026) — 1D-CNN vector+temp+stress (25 G bias).
- Homrighausen et al. *Sensors* 23, 1119 (2023). doi:10.3390/s23031119 — edge-ANN scalar.

## Transferable: learned tracking / data association through crossings
- Revach, Shlezinger, …. "KalmanNet." *IEEE TSP* 70, 1532 (2022). arXiv:2107.10043.
- Pinto, Wymeersch, Svensson. "Can Deep Learning be Applied to Model-Based MOT?" arXiv:2202.07909 (2022).
- MT3: arXiv:2104.00734. DeepDA (LSTM association through crossings): arXiv:1907.09915.
- "IF Estimation of Frequency-Crossing Signals." *Sensors* 25, 2030 (2025). doi:10.3390/s25072030.
- Liu & Wang. *JASA* 141(2) (2017). doi:10.1121/1.4973687 — DNN+FHMM joint pitch estimation + speaker assignment through crossings.

## Track coalescence + unresolved-measurement association (increment-4 overlay decoders)
- Svensson, Svensson, Guerriero, Willett. "Set JPDA filter for multitarget tracking." *Proc. SPIE*
  8050, 805010 (2011). — identity as a decode-side overlay decoupled from the label-free state
  estimate (basis for D-OV).
- Koch, van Keuk. "Multiple hypothesis track maintenance with possibly unresolved measurements."
  *IEEE Trans. Aerosp. Electron. Syst.* 33(3), 883 (1997). — unresolved-measurement merged
  hypotheses through a dwell (basis for D-UM).
- Blom, Bloem. "Probabilistic data association avoiding track coalescence." *IEEE Trans. Autom.
  Control* 45(2), 247 (2000). — the coalescence phenomenon of marginal-style association, and that
  it is structural rather than a defect.
- Kropfreiter, Meyer, et al. arXiv:2308.06326 (2023). — belief-propagation / marginal association
  reduces coalescence (the JPDAwithLBP reference; basis for D-BP).
- Saucan, Meyer, Willett. arXiv:2606.31716 (2026). — generalized loopy-BP with an
  unresolved-measurement form. *(recent — verify)*
- García-Fernández. arXiv:1604.00082 (2016). — labeled-RFS "mixed labelling": identity through
  *long* merges may be only partially recoverable — the increment-4 graceful-degradation caveat.
- Maggiolino, Ahmad, Cao, Kitani. "Deep OC-SORT." arXiv:2302.11813 (2023). — SNR-graceful
  appearance gating; reference for a *future* appearance retry, NOT used in the zero-retrain
  overlay decoders here.

- **MIT US11346904B2** (2022) — 8-channel through-crossover tracking (prospective; no reduction to practice).
- **Lockheed US11187765B2** — quadrature/SMAC dynamic-range extension.
- **Q.ANT JP2025518254A** — automatic resonance control for NV magnetometers (control-side; not ML).
- Lockheed US10545200B2 / US9541610B2; Walsworth US10545200B2 / WO2017213928A1 (simultaneous vector lock-in).
