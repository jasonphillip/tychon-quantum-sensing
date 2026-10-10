# External ODMR validation

| dataset | item | n_points | overlap_fraction | overlap_ok | shape_mse | contrast_exp | contrast_sim | contrast_ratio | linewidth_exp_hz | linewidth_sim_hz | max_abs_peak_offset_hz | noise_exp | sim_field_source | B_lab_mT | comparable | reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| zenodo_ml_scan | x_1 | 600 | 1.0 | True | 0.7237211934459659 | 1.096189741332081 | 0.0036113080899652394 | 0.0032944187979508065 | — | 1271265.0860857964 | — | 0.04450281462123129 | fitted-grid | -1.1547, 1.1547, -1.1547 | True |  |
| zenodo_ml_scan | x_2 | 600 | 1.0 | True | 0.7094469327823542 | 1.142859717590763 | 0.0036113080899652394 | 0.0031598874598346652 | 109824230.07489729 | 1271265.0860857964 | — | 0.045856593792754065 | fitted-grid | -1.1547, 1.1547, -1.1547 | True |  |
| zenodo_ml_scan | x_2_1 | 600 | 1.0 | True | 0.4417566078083423 | 1.7809852495764118 | 0.0036113080899652394 | 0.0020277024140565735 | 24721071.391522884 | 1271265.0860857964 | — | 0.05521433022191399 | fitted-grid | -1.1547, 1.1547, -1.1547 | True |  |
| zenodo_zerofield | Position 1 | 130 | 1.0 | True | 0.23158495975366966 | 0.05170627007497946 | 0.029997306416428546 | 0.5801483335179531 | 6302534.847597599 | 658305.454773426 | 3000000.0 | 0.005874439346406519 | zero | 0, 0, 0 | True |  |
| zenodo_zerofield | Position 2 | 130 | 1.0 | True | 0.16747235019684462 | 0.047234650888579685 | 0.029997306416428546 | 0.6350699296410222 | 7247587.367552757 | 658305.454773426 | 3000000.0 | 0.004499847789911437 | zero | 0, 0, 0 | True |  |
| zenodo_zerofield | Position 3 | 130 | 1.0 | True | 0.14431201583552597 | 0.0501669711291811 | 0.029997306416428546 | 0.5979493228559642 | 6629389.6613230705 | 658305.454773426 | 4000000.0 | 0.00394352068311701 | zero | 0, 0, 0 | True |  |
| harvard | 0.40579 | 121 | 1.0 | True | 0.5489735801017059 | 1.0659070385414913 | 0.011064527617699643 | 0.010380387048423593 | 2473745.4093704224 | 575891.853415966 | — | 0.10946072246490447 | documented | 0.288675, 0.288675, 0.288675 | True | 0.5 mT documented; direction assumed first NV axis |
| harvard | 0.40781894999999996 | 121 | 1.0 | True | 0.5489735801017059 | 1.0659070385414913 | 0.011064527617699643 | 0.010380387048423593 | 2473745.4093704224 | 575891.853415966 | — | 0.10946072246490447 | documented | 0.288675, 0.288675, 0.288675 | True | 0.5 mT documented; direction assumed first NV axis |
| harvard | 0.40984790000000004 | 121 | 1.0 | True | 0.5328247885596175 | 1.081120463720615 | 0.011064527617699643 | 0.010234315221100982 | 2294335.7897405624 | 575891.853415966 | — | 0.1119646392362074 | documented | 0.288675, 0.288675, 0.288675 | True | 0.5 mT documented; direction assumed first NV axis |
| borealis | 0_2867000-1.csv | 328350 | — | — | — | — | — | — | — | — | — | — | — | — | False | Pulsed calibration data: each file sweeps pulse and interpulse duration at one fixed detuning; the simulator models CW ODMR |
| borealis | 0_2867000-2.csv | 328350 | — | — | — | — | — | — | — | — | — | — | — | — | False | Pulsed calibration data: each file sweeps pulse and interpulse duration at one fixed detuning; the simulator models CW ODMR |
| borealis | 0_2867000-3.csv | 328350 | — | — | — | — | — | — | — | — | — | — | — | — | False | Pulsed calibration data: each file sweeps pulse and interpulse duration at one fixed detuning; the simulator models CW ODMR |
| zenodo_odmr | f0_odmr.csv | 200 | 1.0 | True | 0.2846176061121379 | 0.0034472656157459695 | 0.002515401172135885 | 0.7296801153489201 | 3786053.792019367 | 1600494.9497227669 | — | 0.0006727078841151455 | fitted-grid | -0.288675, -0.288675, 0.288675 | True |  |
| zenodo_odmr | f12_odmr.csv | 200 | 1.0 | True | 0.3332462255092276 | 0.003045694239230536 | 0.002515401172135885 | 0.8258876218550999 | 3061467.2152318954 | 1600494.9497227669 | — | 0.0006483242349365748 | fitted-grid | -0.288675, -0.288675, 0.288675 | True |  |
| zenodo_odmr | f24_odmr.csv | 200 | 1.0 | True | 0.4098024295987461 | 0.003007182503262597 | 0.002515401172135885 | 0.8364644212337756 | 4242032.930529594 | 1600494.9497227669 | — | 0.0007384153592828244 | fitted-grid | -0.288675, -0.288675, 0.288675 | True |  |
| darus_gradiometry | dataset | — | — | — | — | — | — | — | — | — | — | — | — | — | False | Allan-deviation tables, not spectra |

## How to read this

overlap_ok false means the comparison is not valid; contrast_ratio far from 1 means the simulation's contrast model disagrees even when the shape agrees.

## Reading notes (2026-10-09)

- Every spectrum row passes the overlap gate: the simulated range is set from each experimental range, and units are declared per loader.
- Shape agreement (normalized MSE over the overlap) is best for the zero-field set (0.14–0.23) and the Zenodo ODMR sweeps (0.29–0.41), and poor for the ML-scan and Harvard low-field rows (0.44–0.72).
- Where the measured linewidth is meaningful (zero-field, Zenodo ODMR and Harvard rows), the simulator's default lines are 2–10× narrower: simulated FWHM 0.58–1.6 MHz against 2.3–7.3 MHz measured. The ML-scan linewidths (25 and 110 MHz) are not meaningful, for the same reason as their contrast (below).
- Contrast is comparable only where the experimental signal is a positive photoluminescence trace (zero-field, Zenodo ODMR): there the simulated contrast is 0.6–0.8× the measured one. The ML-scan and Harvard signals give contrast_exp > 1, so they are not positive PL traces (baseline-subtracted or differently normalized) and their contrast ratio is not meaningful.
- The field for the ML-scan and Zenodo ODMR rows is a coarse grid fit (sim_field_source = fitted-grid), not a documented value.
- Excluded: the Borealis files are pulsed calibration data (pulse and interpulse duration swept at one detuning per file), and the DaRUS set holds Allan-deviation tables. Neither is a CW ODMR spectrum.
- These rows use the simulator's default configuration; no parameter was tuned to the experiments.
