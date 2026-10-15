# Known-axis scalar bias comparison

Preparation only. Registration does not authorize running tests or development without the coordinator's execution gate.
This is a new simulated known-axis task. It does not replace the old arbitrary-direction scalar result.
Read PROTOCOL.md and STAGE1_GATE.json. The latter preserves the global independent-review failure and its restricted known-axis approval.

The generator writes separate inputs.npz and truth.npz. Prediction opens only inputs.
The six-start weighted least-squares fit receives no labels, nuisance states, noise, or exact means.
Its nominal microwave mixture approximates the unknown generated MW and gradient.
All failed fits use45. Boundary flags use SciPy active_mask. One worker runs with one numerical thread.

## Execution paths

Set STUDY_REPO to the absolute checkout and STUDY_WORK to the private absolute study directory.
Use absolute paths for PYTHON_BIN, STAGE1_LEDGER, OLD_ESTIMATOR_LEDGER, OLD_CUSTODY_LEDGER, and NUMERICAL_LOCK.
Every numerical command below goes inside this wrapper; do not call inference or generation directly:

    "$PYTHON_BIN" "$STUDY_REPO/experiments/scalar_bias_design/budget.py" \
      --registration "$STUDY_REPO/experiments/scalar_bias_design/registration.json" \
      --protocol "$STUDY_REPO/experiments/scalar_bias_design/PROTOCOL.md" \
      --stage2-ledger "$STUDY_REPO/.scratch/bias_compute_ledger.jsonl" \
      --stage1-ledger "$STAGE1_LEDGER" --prior-ledger "$OLD_ESTIMATOR_LEDGER" \
      --prior-ledger "$OLD_CUSTODY_LEDGER" --lock "$NUMERICAL_LOCK" \
      --accounting-module "$STUDY_REPO/experiments/scalar_repair_cycle/job_receipt.py" \
      --phase development --seconds "$RESERVED_SECONDS" -- "$PYTHON_BIN" <script-and-arguments>

Use phase tests for the focused suite; evaluation for sealed predictions; metrics for scoring; publication for saved-output checks.
The wrapper preserves120CPU and120wall seconds for publication. It also preserves the earlier wrapper's final reserve.
Every phase still requires the approved registration and exact protocol hash.

## Metadata audit and development

The audit is metadata-only. Supply every certificate-listed JSON plus the extra old custody/repository manifests explicitly.
Do not pass spectrum archives. The private path map must stay outside public artifacts.

    "$STUDY_REPO/experiments/scalar_bias_design/generator.py" audit --certificate "$CERTIFICATE" --expected-certificate-sha256 6acd082f907d33f3e84e09156ed05951f720ef3495554ff5098ef5a678c6a081 \
      --metadata "$OLD_MANIFEST_1" --metadata "$OLD_MANIFEST_2" <all-other-approved-metadata> \
      --out "$SEED_AUDIT" --sanitized-certificate "$SANITIZED_CERTIFICATE" --private-map "$PRIVATE_PATH_MAP"

For evaluation auditing, add --new-seed-record with development's seed-record.json. The reserved bootstrap seed is always excluded.
The evaluation seed audit must live inside the checkout and appear in the frozen relative-path code manifest.

After the coordinator permits focused tests, use phase tests with this command:
    -m unittest discover -s "$STUDY_REPO/tests" -p 'test_scalar_bias_*.py'
This runs the design and custody suites once.

Development command, inside the wrapper:
    "$STUDY_REPO/experiments/scalar_bias_design/generator.py" --partition development \
      --registration "$REGISTRATION" --protocol "$PROTOCOL" --seed-audit "$SEED_AUDIT" --out "$DEV_DATA"

Prediction command, inside the wrapper:
    "$STUDY_REPO/experiments/scalar_bias_design/run_predictions.py" --data "$DEV_DATA" --out "$DEV_PREDICTIONS" \
      --registration "$REGISTRATION" --protocol "$PROTOCOL"

Keep prediction outputs in the private study directory. Copy their commitment into the checkout before scoring:

    mkdir -p "$STUDY_REPO/experiments/scalar_bias_design/commitments"
    cp "$DEV_PREDICTIONS/commitment.json" "$STUDY_REPO/experiments/scalar_bias_design/commitments/development.json"
    git -C "$STUDY_REPO" add experiments/scalar_bias_design/commitments/development.json
    git -C "$STUDY_REPO" commit -m "Record development predictions before truth scoring"

Set PREDICTION_COMMIT to that commit hash. Scoring verifies the exact committed bytes and committed prediction/receipt hashes first:
    "$STUDY_REPO/experiments/scalar_bias_design/metrics.py" --data "$DEV_DATA" --predictions "$DEV_PREDICTIONS" \
      --out "$DEV_BUNDLE" --registration "$REGISTRATION" --protocol "$PROTOCOL" --code-root "$STUDY_REPO" \
      --commitment "$STUDY_REPO/experiments/scalar_bias_design/commitments/development.json" --commitment-revision "$PREDICTION_COMMIT"

## Sealed evaluation

The custodian creates one secret, commits its commitment, freezes source and audit hashes, and owns sealed generation.
Evaluation generation adds these arguments to generator.py:
    --partition evaluation --custody-root "$PRIVATE_CUSTODY" --code-root "$STUDY_REPO" \
    --code-manifest "$FROZEN_CODE_MANIFEST" --freeze "$FREEZE" --out "$EVAL_DATA"
It also needs the same registration, protocol and frozen evaluation seed-audit arguments.
Generation claims one use before returning entropy. It writes a new read-only directory and never prints entropy.
Only afterward does the custodian issue evaluation access.

Evaluation prediction and scoring add --freeze "$FREEZE" --access "$ACCESS" --code-root "$STUDY_REPO".
Their canonical exclusive markers sit beside access.json. Binding failures stop the operation.
Copy evaluation commitment.json into experiments/scalar_bias_design/commitments/evaluation.json and commit that tracked copy.
Pass its absolute checkout path and commit hash to scoring. Keep predictions private until bundle review.
Scoring still requires this Git commitment before opening truth. Reveal/retirement belongs to custody.py.

## Public saved-output check

Metrics writes one portable bundle with predictions, labels, spectra/means, flags, bootstrap indices, receipts and metric results.
Supply its expected manifest hash independently:
    "$STUDY_REPO/experiments/scalar_bias_design/check_saved.py" --bundle "$PUBLIC_BUNDLE" \
      --expected-manifest-sha256 "$EXPECTED_BUNDLE_SHA256"

Use the accounting wrapper during this study. A later public checkout needs only NumPy and Python's standard library for this check.
The checker hashes every listed artifact and recomputes metrics and acceptance. It never runs inference or generates spectra.
Source uses NumPy and SciPy for fitting. Latency describes this shared machine, not a portable hardware guarantee.
