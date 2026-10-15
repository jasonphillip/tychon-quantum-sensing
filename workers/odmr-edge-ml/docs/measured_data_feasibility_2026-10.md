# Measured CW-ODMR data feasibility (lane M) — 2026-10-15

Worker: Claude Sonnet subagent dispatched by session f368afc3; about 25 web/API calls; downloads ~108 MB under `downloads/` (nothing executed). Saved by the coordinator from the worker's returned text (the worker could not write files).

(verified) = read in a file or API response the worker opened; (stated) = read on a page or paper only.

**Verdict: all three candidates NOT QUALIFIED as an independently labelled field-accuracy set (≥ 20 settings, independent calibrated reference, stated uncertainty).**

| Candidate | Licence | Spectra | Label provenance | Settings / sessions | Reference uncertainty |
|---|---|---|---|---|---|
| 1. Warwick fiber-coupled, https://wrap.warwick.ac.uk/id/eprint/174035/ | CC BY 4.0 (stated) | Lock-in CW-ODMR, PicoScope voltage vs frequency-ramp channel, `.mat`; ensemble, [100] bias (verified, `ODMR_information.txt`) | Helmholtz coil calibrated with a Magnetics GM07 Hall probe (stated, https://arxiv.org/pdf/2211.09170) | ODMR folders vary modulation, MW power and detection scheme, not field; the field series is 47 lock-in voltage points in an xlsx, not spectra (verified) | GM07 uncertainty not found |
| 2. Limits of absolute vector magnetometry, https://doi.org/10.5281/zenodo.15631435 | CC BY 4.0 (verified) | Lock-in ODMR, 5,500 points, 2,600–3,150 MHz, 0.1 MHz step, `.h5`; ensemble, unknown orientation (verified) | Commanded coil current/angle; coil vectors and diamond orientation fitted from the same spectra (verified in Figure_8 files; paper Appendix B, https://arxiv.org/pdf/2504.20750) | One session of 26 current steps; four same-day files of 19 angles × 2 repeats; one sensor (verified) | None for the coil-to-field map; fitted coil vectors ~98° apart where 90° is expected |
| 3. Randomly oriented micro-diamonds, https://zenodo.org/records/7233869 | CC BY 4.0 (verified) | CW-ODMR image cubes, FITS, 2,700–3,000 MHz, 1.5 MHz step, 200 points (header verified by range request) | Wire current −600 to +600 mA, 25 settings, uncalibrated; 3.2 mT bias estimated from the ODMR itself (stated, https://www.nature.com/articles/s41598-022-22610-5) | One device, one session series | None |

Warwick is the closest: the Hall-referenced fields attach to voltage steps, not spectra. `HelmholtzCalibration.xlsx` sits ~480 MB deep in a solid 7z block (archive listing read by range requests, 7,501 files), beyond the 250 MB cap.

New leads (two search batches, nothing usable): a 2022 Sci Rep nanodiamond paper (https://pmc.ncbi.nlm.nih.gov/articles/PMC9436989/) checked its field with a Lake Shore F71 teslameter to ±0.12 µT, data on request only (not contacted); https://github.com/theo-bensadoun/nv-centers-vector-magnetometry-deep-learning has no raw data and commanded-current labels. Not opened: arXiv 2504.18478; the 2026 polarization-anisotropy paper.

## Recommendation
Stop field-accuracy evaluation on public measured data. Possible later consistency pilot (no training, ≤ 200 spectra, < 2 CPU-hours; needs separate approval, and the two-line scalar model's input contract does not match these ensemble, wide-span spectra, so only classical fitting/background checks apply): Lönard Figure_1 arrays (204, already downloaded), split by acquisition family (2024-06-20 current ramp = A; the four 2024-06-28 angle files held out together = B); report repeatability `_0` vs `_1`, monotonic response with current on A, angular symmetry on B, rejection rate and baseline residuals; label every number "consistency check, not accuracy"; never score against commanded current or the paper's fitted fields.

## Coordinator checks (2026-10-15)
- Zenodo API: 15631435 licence `cc-by-4.0`, 1 file; 7233869 licence `cc-by-4.0`, 25 files, 65.5 GB — both match the table.
- Disk use of `downloads/` is 266 MB: `zen15631435/` 70 MB (31.8 MB zip + extracted arrays), `warwick_header_only/` 197 MB (an 800 MB sparse `h.7z` holding only range-requested blocks, plus decoded blocks). Network transfer is consistent with the worker's ~108 MB; the 250 MB cap was on downloads, not on decoded files.
