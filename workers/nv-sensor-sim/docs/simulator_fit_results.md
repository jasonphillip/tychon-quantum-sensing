# Simulator fit to external ODMR

Date: 2026-10-10
Git SHA: 1ce32afc9bc57d783d42ffdf6dd0d4e54138a06d

Minimize squared log simulated-to-measured linewidth ratio, plus squared log contrast ratio when contrast is used.

Inputs: `docs/external_validation_results.json` (sha256 5465f608ef83); data folder `~/projects/nv-sensor-sim/data/experimental`, harvard tree sha256 9936294d2432; zenodo_odmr tree sha256 f744d2d081fd; zenodo_zerofield tree sha256 49b1fdeffb60. Wall 4.5 s on CPU, 0 GPU job-hours; no dataset regenerated. Every row below was used for the fit, so every row is in-sample.

| Dataset | Item | Default linewidth (MHz) | Fitted linewidth (MHz) | Measured linewidth (MHz) | Default shape MSE | Fitted shape MSE | Fitted contrast | Contrast ratio |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| zenodo_zerofield | Position 1 | 0.658305 | 6.30253 | 6.30253 | 0.231585 | 0.13865 | 0.0522856 | 1 |
| zenodo_zerofield | Position 2 | 0.658305 | 7.24758 | 7.24759 | 0.167472 | 0.075553 | 0.0479444 | 0.999999 |
| zenodo_zerofield | Position 3 | 0.658305 | 6.62939 | 6.62939 | 0.144312 | 0.068448 | 0.0507915 | 1 |
| harvard | 0.40579 | 0.575892 | 2.47375 | 2.47375 | 0.548974 | 0.354376 | not fitted | 0.000868589 |
| harvard | 0.40781894999999996 | 0.575892 | 2.47375 | 2.47375 | 0.548974 | 0.354376 | not fitted | 0.000868589 |
| harvard | 0.40984790000000004 | 0.575892 | 2.29433 | 2.29434 | 0.532825 | 0.355873 | not fitted | 0.000877181 |
| zenodo_odmr | f0_odmr.csv | 1.60049 | 3.78605 | 3.78605 | 0.284618 | 0.269496 | 0.0104499 | 1 |
| zenodo_odmr | f12_odmr.csv | 1.60049 | 3.06147 | 3.06147 | 0.333246 | 0.32601 | 0.0118007 | 0.999999 |
| zenodo_odmr | f24_odmr.csv | 1.60049 | 4.24203 | 4.24203 | 0.409802 | 0.391599 | 0.00857469 | 0.999999 |

Median fitted inhomogeneous FWHM (Hz): 2688913.6904152087
Median fitted base contrast: 0.029872511664386057
