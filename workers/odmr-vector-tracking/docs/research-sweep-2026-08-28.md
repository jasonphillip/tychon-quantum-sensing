# External research sweep snapshot

*External-sweep snapshot. TVW, 2026-08-28. Coverage: 2025-09 -> 2026-08-28.*

This document is informational. It orders no work. TVW dispatches direction separately.

## Papers most relevant to this tracker

| arXiv ID / DOI | Paper | Tracker relevance | Report grade |
|---|---|---|---|
| 2607.22521 | Critical Sensing with Autonomous Devices: The Self-Oscillation Threshold of a Frequency-Locked NV-Centre Magnetometer | Studies the exact frequency-lock stability limit and lock-loss physics that motivates through-crossing tracking. Missed by keyword scoring; found via full-text abstract read. | **P1 — must-pull** |
| 10.1088/1674-1056/ae77cb | A symmetry-aware geometric framework for resolving ambiguity in NV ensemble magnetometry | Targets NV-axis and orientation ambiguity. This is the same problem class as the through-crossing tracker. No arXiv preprint found. | **P1 — must-pull**; Exa-reported, single-source, not independently verified |
| 2607.22410 | A Kalman Filter Based Approach to NV Diamond Data Fusion For Improved Temperature Sensing | Provides an NV-specific KF comparison, though it addresses temperature rather than vector tracking. | P2 — useful |
| 2510.11884 | Optimal and efficient inference tools for field tracking with precessing spins | Frames field-tracking inference around magnetic-navigation applications. | P2 — useful |

### Strategic context: microwave-free and zero-field vector magnetometry

This cluster validates the magnet-free direction and increases competitive pressure. It does not replace through-crossing identity tracking.

| arXiv ID | Paper | Tracker relevance | Report grade |
|---|---|---|---|
| 2512.13835 | Microwave-free vector magnetometry and crystal orientation determination with NV centers using Bayesian inference | Combines zero-field vector magnetometry with Bayesian orientation determination. | **P1 — must-pull** |
| 2602.12090 | Unconditional full vector magnetometry using spin selectivity in Nitrogen Vacancy centers in diamond | Offers full vector magnetometry without bias-field axis separation. | **P1 — must-pull** |
| 2511.11561 | Vector magnetometry using cavity-enhanced microwave readout in nitrogen-vacancy diamond | Demonstrates 4π-steradian vector sensing. This directly compares with the v6 angular-coverage framing. | **P1 — must-pull** |
| 2606.02749 | Vector Magnetometry with Broadband Microwave Fields in Nitrogen-Vacancy Centers in Diamond | Uses broadband microwaves instead of frequency locking. It is an alternative response to lock loss. | P2 — useful |
| 2505.24574 | Bias-field-free operation of nitrogen-vacancy ensembles in diamond for accurate vector magnetometry | Supports the magnet-free strategic angle. It predates the sweep window by three months. | Pre-window context |
| 2504.20750 | Limits of absolute vector magnetometry with NV centers in diamond | Defines accuracy limits that frame the tracker's dynamic-range extension. | Pre-window context |

## Competitor scan

The sweep found no existing paper doing exactly `"through-crossing identity tracking"`.
This is absence-from-sweep, not proof of non-existence.

ML for ODMR is still scattered, no dominant paradigm.
The sweep found neural fields, regression readout, deep-learning frameworks, and quantum-ML approaches.
No method repeated across papers.

## Tracker-library landscape

Evidence classes follow the source report. `[API]` fields come from direct API reads.
`[Fetch]` fields come from one page read. `[Search]` fields come from search results only.

| repo | URL | stars | last commit | license | fit |
|---|---|---:|---|---|---|
| dstl/Stone-Soup | https://github.com/dstl/Stone-Soup | 640 | 2026-08-26 [API] | MIT | **[Fetch-confirmed active]** Comprehensive UK-MOD-DSTL tracking framework, 3834 commits, PyPI+conda-forge, Python 3.10+. JPDA/MHT/particle-filter/IMM coverage is documented on the project's own docs site — **not directly confirmed by this fetch** (page excerpt didn't list algorithms; recommend stonesoup.readthedocs.io before committing). Strongest general upgrade path beyond the CV-KF+Hungarian baseline. |
| borglab/gtsam | https://github.com/borglab/gtsam | 3658 | 2026-08-28 [API] | NOASSERTION (BSD-style historically) | The standard factor-graph / smoothing-and-mapping library — directly answers the "factor-graph libs suited to through-crossing ambiguity" ask; C++ with Python bindings. |
| tryolabs/norfair | https://github.com/tryolabs/norfair | 2679 | 2025-04-30 [API] | BSD-3-Clause | **[Fetch-confirmed]** Kalman-filter-based, SORT generalized to a variable-count-per-detection **point tracker** (not bounding boxes) — directly matches treating each ODMR resonance peak as a tracked point. ~16 mo since last push as of this report — mature/stable, not abandoned, but slower-moving. |
| erikliland/pyMHT | https://github.com/erikliland/pyMHT | 106 | 2023-09-19 [API] | BSD-3-Clause | Track-oriented multi-hypothesis tracker — algorithmically the most direct fit for through-crossing ambiguity (keeps multiple hypotheses, which CV-KF+Hungarian by design does not), but ~3 yr unmaintained. |
| rlabbe/filterpy | https://github.com/rlabbe/filterpy | 3862 | 2024-02-07 [API] | MIT | The standard Python Kalman/particle-filter primitives library — likely underlies or could formalize the existing CV-KF baseline; mature/low-churn rather than abandoned. |
| Tsingpeng/HO-MHT | https://github.com/Tsingpeng/HO-MHT | 61 | 2021-06-22 [API] | MIT | Hypothesis-oriented MHT, but vision-detection-oriented — would need rework for spectral peaks. |
| matchms (readthedocs) | https://matchms.readthedocs.io | n/a [Search] | actively documented | n/a | **[Search-only]** Mass-spectrometry spectral-similarity/peak-matching library — cross-domain analog; MS peak assignment across spectra is methodologically close to ODMR resonance-identity tracking across a trajectory sequence. |
| ilastik/multiHypothesesTracking | https://github.com/ilastik/multihypothesesTracking | 12 | ~2015-era [Search] | MIT | Old (2015), C++/Python, bio-image cell-tracking MHT — niche but confirms the "MHT adaptable beyond vision" pattern exists in another scientific domain. |
| srianant/kalman_filter_multi_object_tracking | https://github.com/srianant/kalman_filter_multi_object_tracking | 562 | 2023-06-02 [API] | MIT | Popular reference implementation of exactly the existing baseline pattern (Kalman + Hungarian) — demo-quality, not a novel upgrade. |

## Candidate evaluation datasets

| dataset | source and license | evidence | what it would test |
|---|---|---|---|
| Meneses elevator QDM set | https://github.com/Fertmeneses/ML_QDM_Meneses_et_al; MIT | opened | Tests tracking on real 3-axis QDM data against the elevator's known 1D ground truth. |
| Mag4D-SLAM | mag4d-dataset.github.io/Mag4d-Dataset/; arXiv:2607.21986; license not stated | opened | Tests repeatability across seven known-path traversals. LiDAR-ICP provides 6-DoF ground truth. |
| Borealis rotation sweep | doi:10.5683/SP3/DRTLGW; CC BY-SA 4.0 | opened | Tests identity tracking and generator validation across a real NV field-rotation sweep. This is the **strongest match to "trajectory families as B rotates" found anywhere in the sweep**. |
| AaltoML/magnetic-data | github.com/AaltoML/magnetic-data; none stated ("as is") | opened | Tests a domain gap created by a deliberate mid-session field perturbation. Vicon supplies 2D pose truth. |

Borealis integration into `nv-sensor-sim` is in progress (TVW downloaded all 271 files, 2026-08-28, execution-verified; loader work follows in that repo).

## Ingested-paper locations

The ingested papers live in the `odmr-pnt-nv-docs` and `synthetic-data-methods` corpora.
Search both through `/search-corpus`.

Ingest happened after the sweep reports were written: TVW ran the ETL the same day (execution-verified counts: odmr-pnt-nv-docs 1149->1172 chunks; synthetic-data-methods new, 44 chunks).
