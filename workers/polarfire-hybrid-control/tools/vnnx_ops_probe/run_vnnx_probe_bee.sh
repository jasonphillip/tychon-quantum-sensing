#!/usr/bin/env bash
# Tier-0 op-support probe — BEE-SIDE compile + VNNX-sim runbook.
#
# Prereq: the VectorBlox SDK is Beelink-only. Run this ON bee once bee is back online
# (as of 2026-07-02T11:5x it was OFFLINE — Tailscale "last seen 7h ago" — so the measured
# half of Tier 0 is BLOCKED until then). This never touches the Icicle Kit / the soak.
#
# Inputs (produced by export_ops_probe.py, committed under the report dir):
#   gru_cell_onestep_int8.tflite      softmax_head_8x60_int8.tflite
#   gru_cell_onestep_fixed_io.npz     softmax_head_8x60_fixed_io.npz   (fixed inputs + float ref)
#   ops_probe_manifest.json           (tflite ops + int8 quant params)
#
# Goal: for each model, vnnx_compile -c V250; run the VNNX simulator on the fixed input set;
# report per-op ACCEPT/REJECT (compiler stdout) + max abs error (sim vs float ref).
#
# --- UNVERIFIED against the live SDK (bee was offline when this was written) — CONFIRM on bee-up:
#   * activation path: global notes say  source /c/Microchip/VectorBlox-SDK/setup_vars.sh  (MSYS,
#     Python-3.10 vbx_env); the repo CLAUDE.md "Remote Synthesis" shows a WSL path
#     (wsl -d Ubuntu -u jason -- 'source ~/vbx-env/bin/activate'). vnnx_compile needs x86-64
#     Linux, so the WSL path is the likely one. Try WSL first.
#   * exact vnnx_compile flags: CLAUDE.md documents `vnnx_compile -c V250 -t model.tflite -o out.vnnx`.
#     SDK tutorials also mention a `tflite_preprocess` step (adds a preprocessing/normalization
#     layer) — for these raw-feature probes it is very likely NOT needed; skip unless the
#     compiler asks for it.
#   * the simulator entrypoint: SDK tutorials say "simulate ... using a Python inference script
#     from example/python". vnnx_compile itself typically also prints a VNNX-sim-vs-TFLite error
#     during compile — capture full stdout; that alone may answer the accept/reject + error.
set -u
SDK_ACTIVATE_WSL='source ~/vbx-env/bin/activate'
SDK_ACTIVATE_MSYS='source /c/Microchip/VectorBlox-SDK/setup_vars.sh'
WORK="$HOME/vnnx_ops_probe"      # stage the artifacts here on bee
mkdir -p "$WORK"; cd "$WORK" || exit 1

for m in gru_cell_onestep softmax_head_8x60; do
  echo "==================== $m ===================="
  # 1) COMPILE — capture ALL stdout/stderr (accepted-op list + any 'VECTORBLOX ERROR' + sim error)
  vnnx_compile -c V250 -t "${m}_int8.tflite" -o "${m}.vnnx" 2>&1 | tee "${m}_compile.log"
  rc=${PIPESTATUS[0]}
  echo "vnnx_compile rc=$rc"
  if grep -q "VECTORBLOX ERROR" "${m}_compile.log"; then
    echo "RESULT[$m] = REJECT (VECTORBLOX ERROR in compile log — the op(s) are NOT V250-supported)"
    continue
  fi
  if [ "$rc" -ne 0 ] || [ ! -f "${m}.vnnx" ]; then
    echo "RESULT[$m] = REJECT/INCOMPLETE (rc=$rc, no .vnnx) — inspect ${m}_compile.log"
    continue
  fi
  echo "RESULT[$m] = ACCEPTED by vnnx_compile (.vnnx produced)"
  # 2) SIMULATE on the fixed input set + compare to the float reference.
  #    Adapt the sim call to the SDK's example/python inference script; write its outputs to
  #    ${m}_sim_out.npy (shape must match the float ref in ${m}_fixed_io.npz['ref']).
  #    Then:
  #      python3 compare_vnnx_vs_float.py --fixed ${m}_fixed_io.npz --sim ${m}_sim_out.npy \
  #              --manifest ops_probe_manifest.json --model $m
  echo "  (run the SDK simulator on ${m}_fixed_io.npz inputs -> ${m}_sim_out.npy, then compare_vnnx_vs_float.py)"
done
echo "Done. Per-op verdict = ACCEPTED/REJECT above; max abs error = compare_vnnx_vs_float.py output."
