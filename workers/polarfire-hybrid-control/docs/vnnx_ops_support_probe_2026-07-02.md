# V250 op-support probe (LOGISTIC / TANH / SOFTMAX / MUL) — Tier 0, 2026-07-02

**Question.** `odmr-vector-tracking`'s `ops_guard` bans `sigmoid`/`tanh`/`softmax`/`mul`/`matmul`
on the V250 — the technical reason its learned tracker partitions the GRU recurrence and the
8×60 association head onto the MSS host instead of the NPU. The VectorBlox SDK's own op list
contradicts that ban. Tier 0 (per `tvw/audits/research-ml-optimization-levers-2026-07-02.md`)
settles it by measurement: export the disputed ops to INT8 TFLite, `vnnx_compile -c V250`,
run the VNNX simulator vs float.

**Status: MEASURED (bee back online same day after a forced reset; compile + sim executed
2026-07-02 ~17:30–17:45Z). The Icicle Kit / the running soak were never touched.**

**Measured bottom line:** the op-level ban on `sigmoid`/`tanh`/`softmax` is **FALSIFIED** —
they compile and simulate correctly in single-input feedforward graphs. But the GRU-style
cell is still **not deployable**, for a *different, now-measured* reason: `vnnx_compile`
crashes on the cell composition (both rank-2 and rank-4 variants), and two-graph-input
topologies produce garbage in the VNNX simulator even when they compile. The real constraint
is **topology (single graph input), not the op list**.

## Doc-archaeology side — SETTLED (contradiction confirmed)

The SDK op list `polarfire-control-corpus/raw/github.com/Microchip-Vectorblox/VectorBlox-SDK/docs/OPS.md`
(title *"Supported Operations (INT8 TFLite)"*, 74 operators "Ready for INT8/UINT8 inference",
Apr-2026 / SDK commit `4186f9a` vintage) explicitly lists as supported:

| ops_guard ban (aten) | OPS.md TFLite op | OPS.md constraint |
|---|---|---|
| `sigmoid` | **LOGISTIC** | none |
| `tanh` | **TANH** | none |
| `softmax` | **SOFTMAX** | Dim ∈ {-3,-2,-1} |
| `mul` | **MUL** | fused-activation ∈ {NONE,RELU,RELU6} |
| (—) | **SUB** | fused-activation ∈ {NONE,RELU} |
| (—) | **EXP** | none |

So the ban rests on older launch-collateral, not this SDK's op table. (Per the audit note, the
ban *may* originally trace to real `odmr-edge-ml` compile failures — the measured test settles
whether it still holds on this SDK/target.)

## Measured results (bee, WSL Ubuntu `vbx-env`, Python 3.10.20, SDK at `~/VectorBlox-SDK`)

Per-model verdicts — `vnnx_compile -c V250` accept/reject + simulator accuracy. Raw compile
logs: `libero/reports/2026-07-02-vnnx-ops-probe/bee_logs/`. Drivers: `tools/vnnx_ops_probe/`.

| model (ops under test) | vnnx_compile | sim accuracy (max abs err) |
|---|---|---|
| `softmax_head_8x60` (**SOFTMAX**, FC, reshape — single input) | **ACCEPTED** (92,968 B) | **0.0293 vs float** (mean 0.0045; ≈7.5/1.2 LSB @ 1/256) over all 64 fixed inputs |
| `fc_sigmoid` (**LOGISTIC** — single input) | **ACCEPTED** | 0.0352 vs TFLite-INT8 (≈9 LSB; LUT-grade) |
| `fc_tanh` (**TANH** — single input) | **ACCEPTED** | 0.0859 vs TFLite-INT8 (≈11 LSB; LUT-grade) |
| `sub_const` (**SUB** vs const) | **ACCEPTED** | **exact (0.000)** |
| `mul2in` (**MUL**, two graph inputs) | ACCEPTED | **GARBAGE on distinct inputs** (max 2.42 ≈ full range); bit-exact only on the embedded duplicated test vector |
| `concat_fc` (**CONCATENATION**+FC, two graph inputs) | ACCEPTED | **GARBAGE on distinct inputs** (max 3.94) |
| `gru_cell_onestep` (full cell, rank-2, two inputs) | **CRASH** rc=1 — `ValueError: cannot select an axis to squeeze…` in `channels_first_array_reshape` (`vnnx_tflite.py:664`) | n/a |
| `gru_cell_4d` (same cell, rank-4 NHWC, two inputs) | **CRASH** rc=1 — `IndexError: tuple index out of range` | n/a |

Notes on the two-input failure (three discriminators run, all logged in `tools/vnnx_ops_probe/`):
- **Not input order**: both orders give identical garbage (`order_test.py`); the `.vnnx` does
  reverse input order vs TFLite `input_details` (match by quant params), but that isn't the cause.
- **Not operand broadcast**: sim output matches none of a·b / a·a / b·b (`broadcast_test.py`).
- **The compiler's own embedded reference is bit-exact TFLite** (`embedded_test.py`): for every
  model, `test_output` == TFLite on `test_input`; the *simulator* deviates (≤11 LSB single-input,
  unbounded multi-input). The multi-input marshalling defect is somewhere in `vbx.sim`/the vnnx
  packing — root cause not chased further (time-boxed); the deployability verdict doesn't need it.
- The SDK's entire example zoo (`example/python/`) is single-input image models — multi-input
  graphs appear simply untrodden in this 2.0.x flow.

### What this means

1. **SOFTMAX heads (single-input) are NPU-eligible** — e.g. the 8×60 association head compiles
   and matches float to 0.029. The `aten.softmax` ban is measured-false for this shape class.
2. **Sigmoid/tanh are NOT the blocker** for gated cells — they compile and behave (LUT-grade).
3. **The gated cell remains non-deployable on SDK 2.0.x**, with measured provenance: (a) the
   composition crashes `vnnx_compile` outright, and (b) its state-as-graph-input topology
   requires ≥2 graph inputs, which the simulator executes incorrectly even when compilation
   succeeds. Two independent kill mechanisms, both logged.
4. **The honest guard is a topology rule (exactly one graph input) plus a small op-note**, not
   the old sigmoid/tanh/softmax folklore ban. `matmul` stays banned (untested — attention-style
   MATMUL ≠ FULLY_CONNECTED; no measurement yet).

## Probe construction (for reproduction)

Export harness `tools/vnnx_ops_probe/export_ops_probe.py` (TF 2.21, seed 20260702) produced two
INT8 TFLite models under `libero/reports/2026-07-02-vnnx-ops-probe/`, each isolating the disputed
ops (elementary ops, static batch=1 so no `SHAPE`/`STRIDED_SLICE`/`PACK` dynamic-shape ops leak in
— those are a *separate* already-known ban and would confound the test):

- **`gru_cell_onestep_int8.tflite`** — one-step-unrolled GRU cell, hidden state as graph I/O.
  TFLite ops: `ADD, CONCATENATION, FULLY_CONNECTED, LOGISTIC, MUL, QUANTIZE, RESHAPE, SUB, TANH`
  → exercises **LOGISTIC (sigmoid), TANH, MUL, SUB**.
- **`softmax_head_8x60_int8.tflite`** — Dense → 8×60 score matrix → softmax over the 60-candidate
  axis. TFLite ops: `FULLY_CONNECTED, RESHAPE, SOFTMAX` → exercises **SOFTMAX**.

Each ships a `*_fixed_io.npz` (64 fixed inputs + the float reference output) and hashes/quant-params
in `ops_probe_manifest.json`, so the compile+sim is a single scripted run.

### Execution notes (as run 2026-07-02)

The compile+sim ran via WSL (`wsl -d Ubuntu -u jason`, `source ~/vbx-env/bin/activate`) — the
runbook's WSL-first guess was right; `tflite_preprocess` was **not** needed (raw-feature probes);
the simulator API is `vbx.sim.Model(bytes).run([flat_int8_inputs])` dequantized via
`output_scale_factor`/`output_zeropoint` (ground truth: `vbx/sim/model_run.py`). Bisection
models: `tools/vnnx_ops_probe/export_bisect_probes.py`. bee had crashed earlier the same day
(hard hang in Modern Standby ~08:21–08:27Z, idle, no workload — separate forensics) and was
force-reset by the user before this run.

## Decision / provenance — ops_guard rewritten from measured truth

`odmr-vector-tracking/src/odmr_vector_tracking/validation/ops_guard.py` updated 2026-07-02:

- `aten.sigmoid`, `aten.tanh`, `aten.softmax` moved **BANNED → ALLOWED** (measured: compile +
  LUT-grade sim accuracy in single-input graphs; softmax verified against float on the 8×60 head).
- **New topology gate: exactly ONE graph input** — the measured real constraint (multi-input
  graphs sim-broken; state-as-graph-input cells additionally crash the compiler). This is what
  actually keeps the recurrence on the MSS host.
- `aten.mul` stays banned with a measured provenance note (two-input MUL compiles but
  sim-garbage; internal-mul compositions crash the compiler). `aten.matmul` stays banned
  (untested). The old sigmoid/tanh/softmax folklore rationale is deleted from the docstring.

Evidence: `tools/vnnx_ops_probe/` (harness + discriminator scripts) +
`libero/reports/2026-07-02-vnnx-ops-probe/` (tflite + fixed IO + manifest + `bee_logs/`
compile logs + softmax sim output).
