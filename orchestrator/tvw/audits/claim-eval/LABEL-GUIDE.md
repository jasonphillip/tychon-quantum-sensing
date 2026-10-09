# Claim labels (one per row of label_input.csv)

supported    The report's own evidence (figures, tables, code, logs) establishes the claim as written, with the stated numbers and units.
contradicted The evidence shows the opposite or a different number/unit than the claim states.
unsupported  Plausible, but nothing in the evidence measures or demonstrates it. Includes "plausible-but-unmeasured".
stale        True for an earlier revision or dataset version, no longer true for the one the report describes (mismatched revision).
causal       Asserts cause from correlation or from a design intent, where the evidence shows only association or a plan.

Rules: label the claim text as written, not what the author meant. A unit error is contradicted. If two labels fit, pick the first in this order: contradicted, stale, causal, unsupported, supported. Evidence is code, logs, data, figures and tables; the report's own sentence is not evidence for itself. Write one row per claim: id,label,evidence,rationale, with evidence as path:line or "none found" and a one-line rationale.
