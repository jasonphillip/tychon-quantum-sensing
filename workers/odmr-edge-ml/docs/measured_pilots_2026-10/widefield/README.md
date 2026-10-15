# Measured widefield pilot: development stop

Result recorded 2026-10-15. Independent saved-output verification passed; the scientific gate failed.

All three neural configurations had larger error than the training mean. The selected candidate failed the development gate.
No final blocks or repeat 4 references were opened. There was no Freeze B, further tuning, or retraining.

This is measured fluorescence-repeat prediction. It does not establish magnetic-field accuracy, reliable sensing, or neural advantage.

## Evidence and target

The experiment uses f0, f8, and f24 from [Zenodo 7233869](https://zenodo.org/records/7233869), under CC BY 4.0.
Attribution: Sengottuvel et al., [Scientific Reports 12, 17997 (2022)](https://doi.org/10.1038/s41598-022-22610-5).
These derivative arrays were cropped, patch-averaged, normalized, and combined as the protocol specifies.
The supplied current settings are 0, +600, and -600 mA. They are not independent pixel-field labels.
Current and acquisition time are confounded. Repeat ordinal does not establish chronological order or independent noise.
All three files record 20 ms exposure. The f8 total measurement time is 191.882476 seconds.

Training uses 768 selected patches in 32 spatial blocks; development uses 384 patches in 16 separate blocks.
Repeat 0 supplies observations and brightness-only patch selection. Training targets average normalized repeats 1 and 2.
Development targets use repeat 3. Every spectrum uses its own endpoint normalization, so the target excludes absolute gain.
The [frozen protocol](protocol/PROTOCOL.md), [machine-readable protocol](protocol/protocol.json), and [custody manifest](protocol/custody-manifest.json) specify every partition and transformation.

## All registered methods

| Method | MSE | p90 patch RMSE | Shape derivative MSE | Numerical failures |
|---|---:|---:|---:|---:|
| candidate_16 | 0.0001143991617 | 0.01225266858 | 6.919047966e-05 | 0 |
| candidate_32 | 0.0001191404666 | 0.01285816405 | 6.979489173e-05 | 0 |
| candidate_64 | 0.0001194305892 | 0.01292431293 | 6.961163557e-05 | 0 |
| pca_wiener_16 | 5.288030065e-05 | 0.008811369578 | 3.658804475e-05 | 0 |
| pca_wiener_4 | 5.278186921e-05 | 0.008807284126 | 3.637375299e-05 | 0 |
| pca_wiener_8 | 5.288030065e-05 | 0.008811369578 | 3.658804475e-05 | 0 |
| raw | 0.0002453197521 | 0.01657739627 | 6.878913571e-05 | 0 |
| ridge_0.001 | 0.0001083978454 | 0.01274464128 | 4.555683351e-05 | 0 |
| ridge_0.01 | 0.0001063060468 | 0.01271461824 | 4.345595717e-05 | 0 |
| ridge_0.1 | 0.0001010715496 | 0.01224068707 | 3.983946886e-05 | 0 |
| robust_lorentzian | 0.0002205403831 | 0.01595677663 | 3.518624104e-05 | 0 |
| savgol_11 | 0.0002318014179 | 0.01615857361 | 3.681991775e-05 | 0 |
| savgol_21 | 0.0002297159222 | 0.01607887424 | 3.550000513e-05 | 0 |
| savgol_5 | 0.0002366362383 | 0.01632677568 | 4.289393248e-05 | 0 |
| training_mean | 5.261394555e-05 | 0.008764803159 | 3.637340106e-05 | 0 |

MSE averages normalized fluorescence error equally across spatial blocks. Lower values are better.
The shape metric uses 50 adjacent-frequency edges selected only from training reference spectra.
These edges are a shape diagnostic, not independently labelled physical resonances.
The robust fit reported interpretable-fit flags for 0.0729166667 of development patches. This is separate from numerical failure.
A low mean-spectrum error alone does not show useful peak recovery.

## Registered decision

Widths 16, 32, and 64 used 6,616, 13,032, and 25,864 parameters. Each trained for 100 epochs with one registered seed.
Development MSE selected width 16. The protocol prohibited switching candidates after its quality gate failed.
Its paired MSE-ratio interval against the training mean was [1.9267185560179931, 2.352932873112665].
Only the numerical-failure condition passed. Improvement, tail error, derivative, current-subgroup, and registration-shift conditions failed.
The interval resamples whole spatial blocks. It is conditional evidence from one field of view, not population uncertainty.
All original classical predictions were reused for candidate comparisons.

## Compute and the preserved failure

The first width-16 supervisor rejected an approval-schema mismatch before launching the training child.
The receipt recorded 0.025531 CPU seconds and 0.030508094 wall seconds, with no candidate output.
Accounting conservatively charged 900 CPU, wall, and GPU seconds. That charge was retained.
One approved schema-only retry corrected the approval object. The scientific source, seed, epochs, and thresholds were unchanged.
The successful candidate sequence used 20.5519 CPU seconds and 18.3381554861 wall seconds.
Resource totals below include tests, CUDA smoke, extraction, classical fitting, candidates, scoring, and that failed launch.
They exclude subsequent publication review jobs.

| Resource | Measured or charged seconds |
|---|---:|
| cpu_seconds | 125.625939 |
| wall_seconds | 116.848172056 |
| charged_cpu_seconds | 1025.600408 |
| charged_wall_seconds | 1016.81766396 |
| charged_gpu_seconds | 918.626616655 |

GPU charged seconds record job duration and conservative charges; they are not active GPU kernel time.
Saved batch-1 prediction timings exclude FITS I/O and patch extraction. They do not demonstrate sensing or full-pipeline speed.
The [resource receipt projections](evidence/resource-receipts.json) retain exact values and original receipt hashes.
Private paths, approval documents, and full execution environments are omitted from those projections.

## Recompute from a fresh checkout

Set `PYTHON` to an absolute Python path with NumPy installed. No SciPy, Torch, inference, FITS download, or private approval is required.
Set `WORKER` to the absolute standalone worker root, or the public checkout's `workers/odmr-edge-ml` directory.
Set `PACKAGE` to `$WORKER/docs/measured_pilots_2026-10/widefield`.
Set `VERIFY_OUTPUT` to a new file outside the checkout for each command.

Classical comparison:

```bash
"$PYTHON" "$WORKER/experiments/measured_widefield/verify_saved.py" --targets "$PACKAGE/development-targets" --predictions "$PACKAGE/classical-development" --model "$PACKAGE/classical-model" --metrics "$PACKAGE/classical-development-score/metrics.json" --bootstrap "$PACKAGE/classical-development-score/bootstrap.npz" --manifest "$PACKAGE/verification/classical-manifest.json" --expected-manifest-sha256 f6bb8f18dab00194ac93f1fea6a57ed747bf049a7819b3a89fdb3c92928f482d --out "$VERIFY_OUTPUT"
```

All three candidates against the frozen classical comparison:

```bash
"$PYTHON" "$WORKER/experiments/measured_widefield/verify_saved.py" --targets "$PACKAGE/development-targets" --predictions "$PACKAGE/classical-development" "$PACKAGE/candidate-16-development" "$PACKAGE/candidate-32-development" "$PACKAGE/candidate-64-development" --model "$PACKAGE/classical-model" --metrics "$PACKAGE/candidate-development-score/metrics.json" --bootstrap "$PACKAGE/candidate-development-score/bootstrap.npz" --manifest "$PACKAGE/verification/candidate-manifest.json" --expected-manifest-sha256 5f557a7de3800e20e8eca8119d89e9d72b93817b2589985c09963c0ef4c8815d --out "$VERIFY_OUTPUT"
```

The inventories pin every array, manifest, metric report, resampling file, and verifier source.
The consumed bootstrap seed is public; the checker reproduces every committed resampling index.
All original scientific artifact bytes are preserved, using ordered parts for the large training-target archive, including the mask, fitted classical parameters, candidate weights, flags, and model seeds.
The [provenance record](provenance.json) and [artifact inventory](artifact-manifest.json) bind source and copied evidence.
Independent verification passed 355 classical checks and 460 candidate checks, including independent MSE calculations for all 15 methods.
The exact [classical report](verification/classical-result.json) and [candidate report](verification/candidate-result.json) are included.
Final-public-checkout acceptance remains pending. A verifier PASS confirms the saved negative result; it does not change the failed scientific gate.

## Reassemble the training-target archive, if needed

The original training-target archive is 10,565,564 bytes. The publication filter excludes individual files above 10 MiB.
Two byte-preserving parts retain that archive without decoding or recompression. Each part is below 8 MiB.
The [parts manifest](train-targets/arrays.npz.parts.json) lists the original hash, byte count, ordered parts, and part hashes.
The unchanged training-target manifest continues to identify the reconstructed original archive.
Both metric-check manifests use development targets. The metric commands above require no training-target reassembly.

Set `REASSEMBLED_OUTPUT` to a new file in an existing directory outside the Git checkout.
Run this optional command from a checkout. It requires only Python's standard library.
It checks every part, uses exclusive file creation, and checks the final archive hash.

```bash
"$PYTHON" "$PACKAGE/reassemble_train_targets.py" --manifest "$PACKAGE/train-targets/arrays.npz.parts.json" --expected-manifest-sha256 140c9741243235913b8f4e94d12813dd6693df7de50ca21d8773e41da47a3c37 --out "$REASSEMBLED_OUTPUT"
```

The expected original SHA256 is `4babd435225c24299cb75762ee41885ce9854ebd11921657fe8637f9e5f108d7`.
Byte-only checks passed for exact reassembly, existing-file refusal, checkout-output refusal, and corrupted-part refusal.
These checks did not decode arrays, perform inference, or evaluate numerical results.
