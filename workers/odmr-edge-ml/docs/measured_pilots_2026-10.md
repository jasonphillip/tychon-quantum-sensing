# Measured-data pilots, 2026-10-15: three public datasets, all closed without a confirmed advantage

Status: **all three cycles are CLOSED, with no confirmed practical advantage.**
Widefield and localisation stopped at their registered development gates.
Cardiac stopped earlier, at a reference-eligibility check, before any method comparison.
Every gate was fixed before the results it judges. No final held-out data was opened after a failed gate.
Independent saved-output verification passed for all three lanes.

These pilots used measured data from three public datasets. They followed the simulation screens in [the NV contribution screen](nv_contribution_screen_2026-10.md).
They do not establish magnetic-field accuracy, reliable sensing, hardware performance, or neural advantage.

## Data

| Lane | Public source | Used here | Licence |
|---|---|---|---|
| Widefield | Zenodo [10.5281/zenodo.7233869](https://doi.org/10.5281/zenodo.7233869); paper: Sengottuvel et al., [Sci. Rep. 12, 17997 (2022)](https://doi.org/10.1038/s41598-022-22610-5) | Files f0, f8, and f24 (0, +600, and −600 mA wire current) | CC BY 4.0 |
| Localisation | Zenodo [10.5281/zenodo.19855773](https://doi.org/10.5281/zenodo.19855773) | Published fitted features and stage coordinates | CC BY 4.0 |
| Cardiac | Zenodo [10.5281/zenodo.20703822](https://doi.org/10.5281/zenodo.20703822); paper: [PMC13580569](https://pmc.ncbi.nlm.nih.gov/articles/PMC13580569/) | One participant's ten NV recording sessions for the reference check | CC BY 4.0 |

Each download was checked against the repository's MD5 and kept read-only with SHA-256 receipts.
The raw originals are not republished here. Each evidence package contains only its derived arrays, with attribution.
Cardiac participants appear only as neutral IDs.

## Widefield: fluorescence-repeat prediction (stopped at development)

The task was to predict a held measured fluorescence repeat from another repeat of the same pixels.
It is not a magnetic-field estimate. The wire currents are setpoints, not independent pixel-field labels.
Current and acquisition time are confounded.

The training mean had the lowest development error (MSE 5.261e-05), and the PCA–Wiener baselines were nearly equal.
The selected neural candidate (width 16, 6,616 parameters) had a mean squared error about 2.17 times the training mean's.
Its paired MSE-ratio interval against the training mean was [1.93, 2.35]. The gate failed, and no final blocks were opened.
The interval resamples spatial blocks within one field of view; it is not population uncertainty.
The [widefield package](measured_pilots_2026-10/widefield/README.md) lists every registered method, the verifier, and the reassembly of the byte-split training-target archive.

## Localisation: development-only trade-off (stopped at development)

The task was to estimate the stage position from the published fitted ODMR features of an eight-sensor array.
The claim scope is limited to published fitted features paired with stage coordinates.
The raw-to-fit lineage is unresolved: the model-loaded parameter file differs from the file the published fit notebook saves.

On the validation set used for selection (44 measurements at 34 positions):

| Method | Calibration positions | Mean error (µm) | 95th-percentile error (µm) |
|---|---:|---:|---:|
| Compact MLP, width 96 | 83 | 112.4 | 188.1 |
| Same-budget kNN, k = 3 | 83 | 134.0 | 364.1 |
| Full-budget kNN, k = 9 | 248 | 99.5 | 206.0 |

The model beat the same-budget reference, but its mean error was 1.13 times the full-budget reference's. The limit was 1.05, so the combined gate failed.
This is an exploratory development trade-off between fewer calibration positions and some loss of accuracy. It is not a confirmed result.
Checkpoint, width, and classical configurations were all selected on this validation set. No held-group features were scored.
A calibrated physical inversion is not possible from the archive: the needle moment, sensor frame, and NV axes are missing.
See the [localisation package](measured_pilots_2026-10/localisation/README.md).

## Cardiac: protocol feasibility failure (stopped before comparison)

The protocol first required two classical reference averages of each recording to agree before any estimator was compared.
The conditions were: normalised RMS error at most 0.5, correlation at least 0.8, the same peak sign, and peak amplitude, peak timing, and width within fixed tolerances.
At least nine of ten sessions had to pass.
None of the ten sessions passed. Their reference normalised RMS errors were 1.21 to 2.65, against the 0.5 limit.
The protocol therefore stopped. No candidate comparison was made, and no waveform from the other two participants was accessed.

This is a feasibility failure of this protocol's reference proxy.
It is not a failure of cardiac NV sensing or of the source data.
The tolerances are engineering limits for this proxy, and they can reject valid recordings with biological change or poor trigger placement.
The recordings are lock-in voltages without a verified volts-to-field calibration, so no field amplitude is claimed.
See the [cardiac package](measured_pilots_2026-10/cardiac/README.md).

## What these pilots show

- No confirmed practical advantage on any of the three measured datasets. Cardiac did not reach a learned-model comparison.
- The localisation trade-off is development evidence only. A fresh held-out test would be needed to confirm it.
- All three negative results are published with saved outputs and verifiers. They are not claims about the datasets' scientific value.

## Reproduce

Each package README gives the exact saved-output verification commands. They need NumPy and the standard library and do not run inference.
The lane tests run on manufactured inputs in CI, one process per lane.
