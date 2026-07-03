#!/usr/bin/env bash
# Relaunch incomplete increment-3 training runs after an unexpected shutdown (power outage).
#
# Intended to run from cron @reboot on each Spark, but safe to invoke manually — it exits
# untouched if a training chain is already alive. Reads the host's intent file
# ``artifacts/increment3/intent_$(hostname -s).txt`` (lines: "<run-name> <seed>", in chain
# order), skips runs that already have a summary.json, archives + wipes partial run dirs, and
# relaunches the remainder as one serial chain via train_run_3.sh.
#
# Restart is FROM SCRATCH by design: runs are deterministic from (config, seed) — the per-epoch
# shot-noise realizations draw from the seeded RNG stream, so a mid-run resume would produce a
# different (non-reproducible) run and break the paired-seed comparison. A clean relaunch
# reproduces the exact same run_key (verified in the 2026-07-03 outage recovery).
set -uo pipefail
cd "$(dirname "$0")/.."
host="$(hostname -s)"
intent="artifacts/increment3/intent_${host}.txt"
rlog="artifacts/increment3/recovery_${host}.log"
stamp() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(stamp)] $*" >> "$rlog"; }

[ -f "$intent" ] || { log "no intent file ($intent) — nothing to recover"; exit 0; }

# Guard: never interfere with a live chain (also makes manual invocation safe).
for pf in artifacts/increment3/chain_*.pid; do
  [ -f "$pf" ] || continue
  pid="$(cat "$pf")"
  if kill -0 "$pid" 2>/dev/null && ps -p "$pid" -o args= 2>/dev/null | grep -qE "increment2a_train|train_run|bash"; then
    log "chain $(basename "$pf") pid $pid alive — no recovery needed"; exit 0
  fi
done

# Collect incomplete runs in intent order.
relaunch=()
while read -r name seed; do
  [ -n "${name:-}" ] || continue
  if [ -f "artifacts/increment3/${name}/summary.json" ]; then
    log "$name: complete (summary.json) — skip"
  else
    if [ -f "artifacts/increment3/${name}.log" ]; then
      mv "artifacts/increment3/${name}.log" \
         "artifacts/increment3/${name}.outage-$(date +%Y%m%d-%H%M%S).log"
    fi
    rm -rf "artifacts/increment3/${name:?}"
    relaunch+=("$name" "$seed")
    log "$name (seed $seed): incomplete — queued for relaunch"
  fi
done < "$intent"

[ ${#relaunch[@]} -gt 0 ] || { log "all intent runs complete — nothing to do"; exit 0; }

# Wait for the GPU driver to come up after boot (train preflight hard-requires CUDA).
for _ in $(seq 1 30); do
  nvidia-smi > /dev/null 2>&1 && break
  sleep 10
done
nvidia-smi > /dev/null 2>&1 || { log "GPU never came up — aborting recovery"; exit 1; }

tag="recover-$(date +%Y%m%d-%H%M%S)"
log "relaunching ${#relaunch[@]} run-args as chain $tag: ${relaunch[*]}"
bash scripts/train_run_3.sh "$tag" "${relaunch[@]}" >> "$rlog" 2>&1
log "chain $tag launched (pid $(cat "artifacts/increment3/chain_${tag}.pid" 2>/dev/null))"
