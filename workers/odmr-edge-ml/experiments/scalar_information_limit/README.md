# Scalar information diagnostic

Read [the report](../../docs/scalar_information_limit_2026-10.md). This directory records a deterministic information calculation registered on 2026-10-15. Stage 2 remains closed pending independent review.

- [Public registration](stage1-public-registration.json) fixes constants, the grid, nuisance assumptions, and caps.
- [Registration mapping](evidence/registration-mapping.json) binds it to the original private registration.
- [Preflight classification](evidence/preflight-classification.json) preserves both failed preflights.
- [Symmetry correction](evidence/symmetry-correction.json) records the narrowly authorized grid retry.
- [Remaining checks](evidence/remaining-checks.json) record mathematical tests not reached by the preflights.
- [Corrected-grid results](results/stage1-symmetry-retry/summary.json) contain all 432 points and 12,960 rows.
- [Saved-output verification](evidence/saved-output-checks.json) recomputes both grids.
- [First-grid results](results/stage1/summary.json) preserve the original stopped grid.
- [Compute receipt](evidence/compute-receipt.json) gives resource use and shared-budget context.

Run the saved-output check from a checkout root with NumPy installed:

    python3 experiments/scalar_information_limit/check_saved.py \
      --directory experiments/scalar_information_limit/results/stage1-symmetry-retry

This command recomputes reported bounds from published means and scaled Jacobians. It performs no forward inference. During this bounded study, use the shared accounting wrapper.

The NPZ contains spherical_mean, spherical_jacobian, cartesian_mean, and cartesian_jacobian. Explicit point_keys are JSON strings. The points JSON retains derivative errors and branch events. The information JSON and CSV contain matching metrics.

The original private registration includes machine-specific accounting paths. Do not copy it into a public overlay. The sanitized derivative removes those paths and adds the approved amplitude reference. The hash mapping preserves original evidence.

The historical preflight script requires the original pinned simulator source. It is not a public-checkout parity test. Neither failed preflight may be rerun. The one symmetry-only grid retry needs its recorded authorization and checks.

The renderer requires NumPy. The prior quadrature additionally requires SciPy. Numerical commands must use the accounting wrapper during this study.
