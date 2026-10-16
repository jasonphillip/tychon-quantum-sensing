# Training-only raw-feature compatibility

This additive package qualifies one raw extractor against eight version-A training rows.
It does not reopen the failed localisation trial or score any position model.
It cannot read the separate August 4 acquisition.

The code is portable across the Sparks and Mac.
Numerical execution remains restricted to a root-approved Linux reservation.
Use explicit paths for the archive, bundle, partition, sample and output.
NumPy, SciPy and pytest are required; no installation is part of this package.

## Source and limitations

Source data and processing conventions: Hao-Cheng Weng and contributors,
Zenodo 19855773, CC BY 4.0, https://doi.org/10.5281/zenodo.19855773.
The raw fit follows source cells in Fig.S4/Fig.S2c.ipynb.
The exact notebook SHA256 is in protocol.json.
Source formulas, initialization, bounds and channel reordering are preserved.
The separate-day notebook has matching nominal sweep settings and fit form.
Its full raw-to-version-A provenance is unproved.

The original loop selects APD channels in ascending order:
1, 3, 4, 6, 7, 11, 13, 15.
Its explicit reorder gives model channels:
15, 6, 11, 4, 13, 7, 3, 1.
Native fitted frequencies and standard errors are GHz.
Output features multiply by 1000 to give MHz.
The 24 features contain splitting, first-center standard error, and second-center standard error per channel.

Fit errors, invalid covariance and nonpositive features fail qualification.
Failures remain in saved arrays and flags.
No sample is replaced, imputed or silently dropped.
No alternate fit, retry, seed search or tolerance adjustment is allowed.

## Prospective gate

The sample comes only from the frozen small training subset.
A coordinate needs exactly one fitted row and one raw member.
Session labels come from archive paths.
They identify a candidate pair, not proof of the missing version-A fit lineage.
Round-robin session selection uses a fixed hash order within each session.
The eight exact rows and raw members are frozen in a separate sample JSON before signal access.

Every one of 64 fits and 192 feature comparisons must pass.
Splitting tolerance is 0.001 MHz plus 0.0001 times the reference magnitude.
Standard-error tolerance is 0.0001 MHz plus 0.01 times the reference magnitude.
These are prospective numerical compatibility limits, not physical uncertainty bounds.
A pass supports only this bounded sample.
It does not prove full lineage or authorize acquisition-transfer scoring.
A mismatch stops unchanged-model transfer.
A common raw pipeline with fair new training requires a new protocol and approval.

## Commands prepared for root release

Metadata/header preparation:

    python /ABS/SOURCE/experiments/localisation_raw_compatibility/prepare_sample.py --archive /ABS/ARCHIVE.zip --partition /ABS/partition.json --custody /ABS/custody.json --output /ABS/sample.json

Manufactured fixtures, through the registered supervisor:

    python /ABS/SOURCE/experiments/localisation_raw_compatibility/tests_entrypoint.py --approval /ABS/manufactured-approval.json

Qualification, through the registered supervisor:

    python /ABS/SOURCE/experiments/localisation_raw_compatibility/qualify.py --approval /ABS/qualification-approval.json --archive /ABS/ARCHIVE.zip --bundle /ABS/bundle.json --partition /ABS/partition.json --sample /ABS/sample.json --custody /ABS/custody.json --output /ABS/NEW_OUTPUT

The parent must freeze protocol.json and bind every source/input hash.
The phase requires at most 600 CPU seconds, 600 wall seconds, 4 GiB and one numerical thread.
Exit 2 is a preserved compatibility failure.
It is not permission to retry or read new data.
The test entrypoint uses pytest.main in-process; it spawns no descendant.

No numerical tests or qualification have run during preparation.
