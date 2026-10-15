# Sparse acquisition qualification: stopped

The approximate Bayesian baseline failed its preregistered numerical qualification.
All seven manufactured beliefs failed at least one gate.
The planned eight-case development comparison did not run.

This result concerns one numerical approximation.
It does not show that adaptive classical sensing fails.
It establishes no adaptive-policy performance gain, neural advantage, or physical sensor result.

## What was checked

The check compared 16 posterior representatives / five quadrature nodes against 32 / nine.
It also refined a 101 x 5 x 3 parameter grid to 201 x 9 x 5.
Every comparison used the same manufactured observations and calibrated model.

All 15 unit tests passed before qualification.
Those tests did not establish numerical convergence.

The frozen specification, observations, likelihood tables, posterior weights, utilities,
and complete results are in [qualification/](qualification/).
The [corrected verdict](verification/qualification-verdict-v2.json) contains every failed gate.

One focused belief illustrates the failure.
Grid refinement changed its posterior field mean by 4.452639 uT.
The declared limit was 0.25 uT.
An interval endpoint changed by 8.5 uT, against a 0.5 uT limit.
These numbers are differences between approximations, not measured field errors.
The finer grid is not asserted to be ground truth.

No gate, tolerance, observation, or policy was changed after qualification.
The stopping rule prevented the development comparison.
No unused case manifest, noise seed, custody certificate, or private approval is published here.

## Verifier correction

The original saved-output verifier stopped with a utility arithmetic mismatch.
It substituted an independently reconstructed posterior into an identity based on the original saved weights.
Small permitted posterior differences were amplified by division by dwell time.

The separate v2 verifier uses the saved weights for that arithmetic identity.
It still uses independent reconstruction for posterior agreement and every grid-convergence gate.
It changed no scientific threshold.
The original qualifier, original verifier, raw observations, and raw qualification outputs remain unchanged.

Both verifier source versions remain in experiments/sparse_acquisition_screen/.
Their exact hashes appear in [provenance.json](provenance.json).
The [v1 error record](verification/v1-stderr-redacted.txt) retains the original error and stack.
Its private workspace prefix is redacted; provenance records the original file hash.

The corrected verification completed and returned qualification_fail.
Its exit code 2 records the expected scientific failure.
It did not crash or rerun the acquisition policy.

## Recompute from the original source checkout

Run from the repository root.
Use Python 3.10 or newer and choose a new output filename.
This command uses only the standard library and saved outputs.
It requires no private data, approvals, NumPy, inference, or training.

```sh
python3 "$(pwd)/experiments/sparse_acquisition_screen/verify_saved_v2.py" --kind qualification --input "$(pwd)/docs/nv_contribution_screen_2026-10/sparse/qualification" --out /tmp/tychon-sparse-qualification-verdict.json
```

Expected: a new verdict file with status qualification_fail, empty stderr, and exit code 2.
A traceback or missing verdict is a checker failure.
Exit code 2 alone does not prove successful reproduction.

The source hashes are checked before the saved arithmetic.
Run this at a checkout containing the exact source versions recorded in the artifact.

The public publication filter removes private home prefixes from documentation.
A sanitized public checkout therefore uses experiments/sparse_acquisition_screen/verify_public.py with --sanitization and the declared publication manifest.
Integration must publish that manifest and the exact portable command before release.
The adapter permits only explicit documentation hash mappings.
It does not permit changes to scientific code, data, protocols, or tolerances.

## Evidence and resource record

[artifact-sha256.json](artifact-sha256.json) covers every package file except itself.
All scientific files under qualification/ and the corrected verdict retain their original bytes.

The resource files in [receipts/](receipts/) are explicitly labelled public projections.
They retain selected exact resource fields and original receipt hashes.
They omit commands, private paths, process environments, and approval contents.
Original receipts and the original unredacted stderr remain in private custody.

Qualification used 19.670610 charged CPU seconds and 17.001455 wall seconds.
The original verification used 0.362411 CPU seconds and 0.332587 wall seconds.
The corrected verification used 0.603483 CPU seconds and 0.579068 wall seconds.
All three receipts report no legacy accounting drift.

No development cases, confirmatory evaluation, retraining, GPU work, or FPGA work followed this failed gate.
