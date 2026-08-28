# VectorBlox SDK 3.1 and Libero 2026.1 upgrade decision

**Decision: upgrade at the next INT8 milestone.** Do not disturb the working two-slot image now. Start the upgrade before the first new `vnnx_compile` integration. Treat SDK, CoreVectorBlox, driver, model binary, and Libero as one validated bundle. Execution remains Jason-gated. **p_success: 0.80** for a staged upgrade with the current toolchain retained `[inferred from Findings 1–5]`.

**Rollback plan.** Keep SDK 2.0.3 and its root-local `vbx_env`. Install SDK 3.1 in another directory. Each `setup_vars.sh` derives `VBX_SDK` and `vbx_env` from its own directory. This makes SDK coexistence feasible by inspection, not by an explicit vendor guarantee `[diff-read; 4186f9a1ac81:setup_vars.sh; f5a428c3c0ee:setup_vars.sh]`. Keep Libero 2025.2 and the known-good `idfix2` job until 2026.1 passes synthesis and silicon checks `[inferred; 165dea3e23b1:README.md]`. The supplied local sources state no Libero coexistence policy. If its installer cannot coexist, stop before installation until Jason approves a tested restore path `[inferred; explicit unknown 5]`.

## Findings

1. **The V250 defect is not identifiable from exposed source.** `[release-note-text]` The 3.1 release note says it resolves a V250 configuration bug `[f5a428c3c0ee; tvw/audits/agent-reports-2026-08-28/r3-microchip.md, row 1]`. `[diff-read]` The requested V250 filename diff is empty. The V250 preset values remain 2 vector lanes, 8 filter copies, 8 output maps, and 32 KiB scratchpad `[bff635b45769..f5a428c3c0ee:python/vbx/vbx/generate/vnnx_types.py]`. The clone contains no CoreVectorBlox HDL or component parameter source `[bff635b45769; f5a428c3c0ee trees]`. It only shows higher 3.1 V250 LUT and DFF totals `[f5a428c3c0ee:docs/resource_utilization.md]`. `[inferred]` An IP-level fix could affect this custom design because it instantiates V250 directly. The evidence does not prove that it does `[165dea3e23b1:README.md; 165dea3e23b1:CLAUDE.md]`.

2. **Use 3.1 before new VNNX integration.** `[diff-read]` The requested 2.0.3→3.1 TFLite files add 9,558 lines and remove 4,568 lines. They add `verify_tflite.py` and the Neuronix compiler/parser `[4186f9a1ac81..f5a428c3c0ee:python/vbx/vbx/generate/*tflite*.py; snp_compiler/compiler/tflite_*.py]`. Release 3.0 also adds a numeric simulator `[bff635b45769:snp_compiler/numeric_simulator/tflite_simulator.py]`. The CLI changes from `-c V250` to `-s V250 -c <ncomp|comp|ucomp>` `[4186f9a1ac81..f5a428c3c0ee:python/vbx/vbx/generate/lite_flow.py]`. The VNNX graph version also changes from `0xf1267b05` to `0x2330b149` `[4186f9a1ac81..f5a428c3c0ee:drivers/vectorblox/graph_version.h]`. `[inferred]` INT8 training and quantized TFLite export remain reusable. Compiler-specific scripts, VNNX files, and baselines do not. The flow is reworked, but the clone does not declare 2.0.3 deprecated `[4186f9a1ac81:README.md; f5a428c3c0ee:README.md]`.

3. **The master transpose fix is conditional for a small 1-D CNN.** `[diff-read]` Commit `6c5c98ecb9da` adds one shape assignment in the `TRANSPOSE_CONV` rewrite. It sets output channels from `weights.shape[0]` `[6c5c98ecb9da:python/vbx/vbx/generate/transform_tflite.py]`. The commit does not change `GROUP_CONV` `[6c5c98ecb9da:python/vbx/vbx/generate/transform_tflite.py]`. `[inferred]` Model size and one-dimensional input do not trigger this path. The fix matters only if the exported graph contains `TRANSPOSE_CONV`, especially with different input and output channel counts. Release 3.1 lacks this fix `[f5a428c3c0ee..6c5c98ecb9da]`.

4. **V250 supports structured sparsity, not Neuronix unstructured mode.** `[diff-read]` The 3.1 core tables include V250 `COMP` with structured sparsity `[f5a428c3c0ee:docs/CoreVectorBlox_IP_Handbook.pdf; docs/resource_utilization.md]`. The SDK guide restricts `UCOMP` to V1000 `[f5a428c3c0ee:docs/VectorBloxPG.md]`. The Neuronix compiler runs only inside the `ucomp` branch `[f5a428c3c0ee:python/vbx/vbx/generate/lite_flow.py]`. V250 can use structured `COMP`. It cannot use the documented Neuronix `UCOMP` configuration.

5. **Paired validation is justified, but Libero 2026.1 is not a proven SDK requirement.** `[release-note-text]` CoreVectorBlox v3.0.001 fails synthesis under Libero 2025.1. The issue is marked fixed in SDK 3.1 `[175b7b4c3a8f; f5a428c3c0ee:docs/known_issues.md]`. This does not establish failure under the current 2025.2 baseline. `[diff-read]` The 3.1 handbook still says CoreVectorBlox v3.0, while resource data says “3.1 Core” `[f5a428c3c0ee:docs/CoreVectorBlox_IP_Handbook.pdf; docs/resource_utilization.md]`. No clone file pins SDK 3.1 to Libero 2026.1 `[f5a428c3c0ee tree]`. `[inferred]` Upgrade and validate them together. Do not call 2026.1 a mandatory dependency.

## Explicit unknowns

1. The defective V250 parameter or RTL behavior.
2. The fix's timing and functional effect on the custom two-slot design.
3. The exact CoreVectorBlox build that should pair with SDK 3.1.
4. An official SDK 3.1 and Libero compatibility matrix.
5. Libero 2025.2 and 2026.1 coexistence and rollback policy.
6. The future INT8 model's operator graph and transpose-fix exposure.

---

## Evidence appendix

**Repository refs**

- `release-v2.0.3` = `4186f9a1ac818f1bb4568eb0f6c3e040f4f28aba`
- `release-v3.0` = `bff635b4576958c10ad6c14e87b469de7aed1a5a`
- `release-v3.1` = `f5a428c3c0ee7e06ad06657c5fcdcc1eda8cf046`
- `master` = `6c5c98ecb9dafe7acb05b0ddb7ce4ee37de2634d`
- Consumer context = `165dea3e23b1f20b6507fbd1e6fad9c80857f0ad`

**Key reads**

- `git diff release-v3.0..release-v3.1 -- '*V250*' '*v250*'` returned no changed path.
- `git grep V250` found unchanged presets and new 3.1 resource tables.
- `git diff --numstat release-v2.0.3..release-v3.1 -- 'python/vbx/vbx/generate/*tflite*.py' 'snp_compiler/compiler/tflite*'` produced Finding 2's totals.
- `git log release-v3.1..master` contains only the transpose-fix commit.
- `docs/known_issues.md` provides the only local Libero/CoreVectorBlox incompatibility statement.

**Decision gates for later execution**

1. Export the candidate INT8 TFLite model and record its operator list.
2. Compile it with the selected 3.1 SDK ref and V250 `ncomp` or `comp`.
3. Import the matching core into a copied Libero project.
4. Rebuild the two-slot design. Compare timing, resources, register version, and PCIe behavior.
5. Program hardware only after Jason approves the recorded rollback artifact and command.
