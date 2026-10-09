# Real NV Dataset Hunt - 2026-06-21

## Status

PARTIAL search only. No public dataset was confirmed as regime-matched and immediately usable for the existing fidelity/evaluation harness.

The current defensible claim remains: the deployed model was trained and evaluated on physics-simulator data, and public real-NV leads found so far are literature/platform leads or regime mismatches, not a confirmed 20-70 uT ensemble CW-ODMR validation set.

## Target Regime

The useful dataset should match the simulator and deployment story:

- ensemble NV diamond, not single-NV scanning microscopy unless explicitly justified
- CW-ODMR or frequency-locked ODMR spectra/traces
- magnetic field near the current simulator regime, roughly 20-70 uT or clearly convertible to that regime
- enough raw spectra or time traces to run the PCA/sim-to-real fidelity check and a small validation/fine-tune split
- license/access clear enough to cite in a reviewer-facing report

## Local Leads

The local corpus has strong real-time ODMR tracking references but not a confirmed downloadable, regime-matched dataset:

- `~/.corpus/odmr-pnt-nv-docs/manifest.json` includes [arXiv:2209.11360](https://arxiv.org/abs/2209.11360), a closed-loop frequency-locked NV ensemble magnetometer lead with 10 kHz bandwidth and high tracking-rate claims. This is architecturally relevant, but no usable dataset was confirmed today.
- `~/.corpus/polarfire-control-corpus/processed/CONTEXT.md` includes a board-level ensemble NV CLFL system with TFM intrinsic dynamic range near 50 uT and a 46 uT square-wave tracking example. This is a close regime clue, not a dataset artifact.
- `~/.corpus/polarfire-control-corpus/raw/zenodo.org/records5521108.md` is the old Zenodo lead called out elsewhere as a mismatch; it should not be treated as regime-matched without a fresh fidelity pass.
- `docs/odmr_demo_credibility_2026-06-02.md` and `docs/skeptic_qa_honest_claims.md` already warn that "real NV data" and "sim-to-real validated" wording is not currently supported.

## Web Leads Checked

- [NV-ODMR simulation](https://arxiv.org/pdf/2301.04106): useful simulation/open tooling context, not confirmed as real regime-matched data.
- [Open-source ODMR platform](https://ar5iv.labs.arxiv.org/html/2205.00005): useful bench/platform lead, not a confirmed dataset.
- [Magnetic-field orientation dependence of CW-ODMR with NV ensembles](https://arxiv.org/abs/2504.18478): relevant ensemble CW-ODMR physics lead, not confirmed as a dataset source.
- [SciPost open-source ODMR platform preprint page](https://www.scipost.org/preprints/scipost_202307_00017/): useful platform trail, not enough by itself for training/evaluation data.

## Current Finding

No CONFIRMED public dataset was found today that satisfies the target regime and can be dropped into the existing ML/fidelity pipeline.

The most promising next search is not generic "NV data"; it is queries around the close-regime phrases:

- "ensemble CW ODMR spectra dataset microtesla"
- "frequency locked NV ensemble magnetometer dataset"
- "closed-loop frequency locked ODMR data"
- "NV ensemble ODMR 50 uT supplementary data"
- "three-frequency modulation ODMR spectra data"

## Next Actions

1. Inspect supplementary information and data availability statements for the CLFL and CW-ODMR ensemble papers in the corpus.
2. Query Zenodo/Figshare/OSF directly for exact title/author combinations from the close-regime papers.
3. If no public set appears, start the benchtop/borrow path: one recorded CW-ODMR sweep set in the target 20-70 uT regime would be more valuable than another broad literature search.
4. Keep dashboard/report phrasing at "simulator-trained; real-NV validation pending" until a dataset passes the fidelity check.
