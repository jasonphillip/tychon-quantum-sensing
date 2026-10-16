# Matched line comparator — source preparation only

This package fits eight Lorentzian centers, one width, one amplitude, baseline, and slope.
It then estimates all three field coordinates and unknown D through the original spin-1 Hamiltonian.
The second stage is numerical inversion, not an analytic inverse.

The source imports the frozen `vector_direct_screen` package from commit `18395df0080fb6f712eebe37a51d6ae55a09dd7f`.
Its Poisson deviance, input-only initializer, physical spectrum guard, and three-width fallback remain unchanged.
The new generic Fisher-scoring loops follow that package's solver, with dimensions changed to twelve and four.
The center inverse uses the full Schur-complement precision after profiling the four fitted line nuisances.
No independent per-center weights replace those correlations.

E=0 and gamma remain the generating model's known constants.
D remains unknown within 2869.6–2870.4 MHz; fixing D would remove a registered nuisance.
Known bias fixes the allowed field branch. The global sign partner lies outside that prior.
Line slots follow nominal bias predictions, never true centers or true fields.
A conservative Weyl bound covers the entire registered field/D box.
Qualification must establish disjoint line envelopes before any fit can execute.
Overlapping envelopes stop this comparator; they do not trigger truth-based relabeling.
This rule does not claim general crossing resolution.

One input-only affine start initializes the line fit.
Each line fit and inverse has the original forty-iteration cap and damping schedule.
The same physical likelihood/bounds guard decides operational acceptance.
Rejected rows get the original bounded three-width physical fallback.
Keep every row and all intermediate validity/convergence flags.
An invalid precision matrix never yields a favorable accepted fit.
No noisy population, old evaluation outputs, new seeds, or measured values were accessed during preparation.

`protocol.json` is a prospective source contract. These scientific values are implemented in code, not arbitrary runtime configuration.
The source guard pins this whole package and each imported frozen runtime dependency.
Only manufactured CPU fixtures have a CLI. Population/profile integration remains root-owned.

After root approval and accounting registration, the prospective exact command is:

```sh
"$PYTHON" "$SOURCE/experiments/vector_line_comparator/run.py" --gate "$GATE" --approval-sha256 "$GATE_SHA256" --out "$OUT"
```

Set all paths explicitly and absolutely. Run this command only through the existing accounting supervisor.
The gate execution must equal `{"phase":"fixtures","backend":"torch","device":"cpu","dtype":"float64"}`.
The eight CPU fixtures passed once at commit ec337749519eaef6907c55b3b46a5266b334325e.
The GPU parity command remains prepared and unexecuted.
Eight authored fixtures cover mathematical model parity, analytic derivatives, unknown-D recovery, noiseless fitting, and sign-branch exclusion.
Future CPU/GPU parity, mixed-failure handling, prior-corner association, and matched noisy profiling remain required.
Use fresh root-authorized evidence only; do not reuse consumed evaluation populations.

Timing must include transfer, initialization, line fitting, precision calculation, field recovery, fallback, and output transfer.
Report fixed calibration separately, with matched amortization for all methods.
A useful neural speedup claim requires this matched classical route to qualify first.
This PyTorch route does not establish equal speed to native Gpufit.

## Optional native path — blocked

`native/` preserves the MIT upstream stock model and license, plus an uncompiled tied-model extension.
The pinned QSL commit is `960a4df49bcbed115778f07407350a18ade14c9b`.
Its default master is not a substitute; it lacks the required Lorentzian models.
The shared-amplitude model has twelve parameters; the stock model has twenty-six independent parameters.
The stock model is an optional flexibility comparison, not the sole strong comparator.

The current supervisor forbids compilation subprocess trees and non-PyTorch GPU allocation.
No new orchestrator or policy bypass is proposed.
`native/build-spec.prepared.json` records the blocked recipe and prospective maximum resources.
The source archive exceeded a voluntary ten-MiB retrieval cap; extraction did not occur.
Native dispatcher registration, full source retrieval, architecture verification, and compile validation remain unfinished.
No driver, compiler, package, service, or system setting changed.

The comparator accepts an explicit `chunk_size=1024`; this is the sole prospective profile choice.
It never mutates the inherited configuration. Additional fixtures cover prior corners, invalid precision, failed fits, and row retention.

`parity.py` proposes one CPU/GPU float64 pass over five fixed noiseless cases, including prior corners.
It compares line values/Jacobians, full parameters, all pipeline flags, and inherited noiseless accuracy.
The complete-parameter comparison uses the unchanged relative-step tolerance in the fixed parameter scales.
No timing or native-performance claim follows. A separate root-approved parity gate is required.
