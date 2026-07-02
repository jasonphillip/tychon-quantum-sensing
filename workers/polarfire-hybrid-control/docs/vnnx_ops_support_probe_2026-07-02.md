# V250 op-support probe (LOGISTIC / TANH / SOFTMAX / MUL) — Tier 0, 2026-07-02

**Question.** `odmr-vector-tracking`'s `ops_guard` bans `sigmoid`/`tanh`/`softmax`/`mul`/`matmul`
on the V250 — the technical reason its learned tracker partitions the GRU recurrence and the
8×60 association head onto the MSS host instead of the NPU. The VectorBlox SDK's own op list
contradicts that ban. Tier 0 (per `tvw/audits/research-ml-optimization-levers-2026-07-02.md`)
settles it by measurement: export the disputed ops to INT8 TFLite, `vnnx_compile -c V250`,
run the VNNX simulator vs float.

**Status: PARTIALLY BLOCKED — the doc side is settled, the measured side waits on bee.**
The two probe models are built and verified; the compile + sim step is **blocked because the
Beelink (the only host with the VectorBlox SDK) is offline** (Tailscale: `bee … offline, last
seen 7h ago`; 100 % packet loss; `ssh` connection timed out — checked 2026-07-02 ~11:5x UTC).
The Icicle Kit / the running soak were never touched.

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

## Measured side — PROBES BUILT, compile+sim PENDING bee

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

### To finish on bee-up (one command each)

`tools/vnnx_ops_probe/run_vnnx_probe_bee.sh` (copy the tflite + npz + manifest to bee, activate the
SDK, `vnnx_compile -c V250` each model capturing full stdout, simulate on the fixed inputs, then
`compare_vnnx_vs_float.py` for max abs error). Per-op verdict = ACCEPTED (`.vnnx` produced, no
`VECTORBLOX ERROR`) vs REJECT; accuracy = max abs error vs the float reference. See the runbook
header for the SDK specifics that must be confirmed against the live install (WSL-vs-MSYS
activation; whether `tflite_preprocess` is needed; the exact example/python simulator script) —
these could not be verified while bee was offline.

## Decision / provenance (until the measured result lands)

- **`ops_guard` is left UNCHANGED.** Rewriting it "from measured truth" or giving the ban a
  *measured* provenance line both require the compile+sim result, which is blocked on bee. Doing
  either now would substitute doc-archaeology for the measurement this task exists to make.
- **Provisional read** (doc-only, not yet measured): the SDK OPS.md lists all four disputed ops as
  INT8-supported, so **Outcome A (gates/softmax compile) is the more likely result** — which would
  make the gated cell and the 8×60 head NPU-eligible and dissolve the ReLU-vs-gated partition. But
  that is a hypothesis until `run_vnnx_probe_bee.sh` produces `.vnnx` + a small max-abs error.
- **Next action:** when bee is back, run the runbook, paste the per-op ACCEPT/REJECT + max abs error
  into this doc, then update `odmr-vector-tracking/.../ops_guard.py` accordingly (rewrite the
  whitelist, or annotate the ban with the measured `VECTORBLOX ERROR` line).

Evidence: `tools/vnnx_ops_probe/` (harness) + `libero/reports/2026-07-02-vnnx-ops-probe/`
(tflite + fixed IO + manifest).
