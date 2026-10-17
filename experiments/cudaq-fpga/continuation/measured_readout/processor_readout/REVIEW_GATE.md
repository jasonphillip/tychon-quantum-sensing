# Independent source-test release gate

The coordinator approved `PROPOSED_PROTOCOL.json` and its exact row ranges before implementation.
The proposed-status wording inside that file remains unchanged to preserve its reviewed hash.
The train-only command never requests source-test payloads.

Review `processor_io.py`, `processor_eval.py`, `test_processor.py`, and `train_registration.json`.
Once training finishes, also review `train_frozen/receipt.json`, `selection.json`, and `models.json`.
`train_ranges.json` records immutable range hashes. `source_train_rows.json` records partition and source-row identities.

The reviewer must clear the frozen code, data split, parameter selection, and final command.
A source-test release file must contain:

```json
{
  "schema": "processor_readout_test_release_v1",
  "approved": true,
  "reviewer": "actual independent reviewer identity",
  "training_receipt_sha256": "SHA256 of completed train_frozen/receipt.json"
}
```

The coordinator writes that receipt after review. This lane does not create its own approval.
The runner verifies the receipt hash, registered code, protocol, and fitted artifacts before each test range.
Test labels and signals remain sealed until those checks pass.
The runner marks the test consumed before its first test payload request.
It refuses a second final run or an existing final output directory.

Uncertainty uses separate preparation-class Wilson intervals.
A separately labelled pooled-accuracy interval is not called a balanced-accuracy interval.
The exported boxcar coefficients are candidates for a future FPGA image.
No LDA-on-FPGA, live sensor, drift-transfer, or physical true-state claim follows from this experiment.
