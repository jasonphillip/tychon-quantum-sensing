#!/usr/bin/env bash
# parallel_launch.sh — orchestrate a master-synth + N parallel P&R sweep on
# Beelink. Run from inside the parallel/ scripts directory on Beelink, e.g.
#
#   ssh bee 'cd ~/dev/projects/polarfire-hybrid-control/libero/scripts/parallel \
#            && bash parallel_launch.sh seed_7 seed_13 seed_23'
#
# Assumes the source project lives at the canonical Microchip ref-design path
# below; override SRC_PROJECT to use a different baseline. Clones go under
# ~/libero_seedsweep/{master,$seed1,...}/ and logs at the same level.
#
# Designed for 64 GB RAM Beelink (2026-05-03 audit-006 baseline). Each Libero
# instance peaks ~8 GB during P&R; 4 concurrent uses ~32 GB. Adjust if running
# on different hardware.
set -u

SRC_PROJECT="${SRC_PROJECT:-/c/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox}"
WORK_BASE="${WORK_BASE:-$HOME/libero_seedsweep}"
LIBERO="${LIBERO:-/c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/libero.exe}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ $# -lt 1 ]; then
  echo "usage: $0 SEED1 [SEED2 SEED3 ...]" >&2
  echo "  SEEDs are integers used as LAYOUT_RANDOM_SEED for each P&R clone." >&2
  exit 1
fi
SEEDS=("$@")

mkdir -p "$WORK_BASE"

# 1. Clone source N+1 times (one master + N seed clones)
echo "==> [$(date -u +%H:%M:%SZ)] cloning project to $WORK_BASE/{master,$(IFS=,; echo "${SEEDS[*]}")}"
for sub in master "${SEEDS[@]}"; do
  rm -rf "$WORK_BASE/$sub"
  cp -r "$SRC_PROJECT" "$WORK_BASE/$sub"
done
echo "==> clones created: $(du -sh $WORK_BASE/* 2>/dev/null | wc -l)"

# 2. Rewrite prjx self-path in each clone
SRC_BASENAME=$(basename "$SRC_PROJECT")
SRC_BS="$(echo "$SRC_PROJECT" | sed 's|^/c/|C:\\|; s|/|\\|g')"
for sub in master "${SEEDS[@]}"; do
  NEW_BS="~\\libero_seedsweep\\${sub}\\${SRC_BASENAME}"
  perl "$SCRIPT_DIR/rewrite_prjx_path.pl" "$SRC_BS" "$NEW_BS" \
    "$WORK_BASE/$sub/${SRC_BASENAME}.prjx"
done

# 3. Generate master_synth.tcl with the master CLONE_DIR substituted
sed -e "s|__MASTER_CLONE_DIR__|~/libero_seedsweep/master|g" \
    "$SCRIPT_DIR/master_synth.tcl" > "$HOME/parallel_master_synth.tcl"

# 4. Run master synth (single Libero) — blocking, ~25 min
echo "==> [$(date -u +%H:%M:%SZ)] launching master synth (single Libero, ~25 min)"
"$LIBERO" "SCRIPT:~/parallel_master_synth.tcl" \
  >"$WORK_BASE/master_synth.log" 2>&1
RC=$?
if [ $RC -ne 0 ] || ! grep -q "MASTER_SYNTH_DONE" "$WORK_BASE/master_synth.log"; then
  echo "==> [$(date -u +%H:%M:%SZ)] MASTER_SYNTH_FAILED rc=$RC" >&2
  echo "    see $WORK_BASE/master_synth.log" >&2
  exit 2
fi
echo "==> [$(date -u +%H:%M:%SZ)] master synth DONE; sha256(.vm)=$(sha256sum "$WORK_BASE/master/synthesis/MPFS_ICICLE_KIT_BASE_DESIGN.vm" | awk '{print $1}')"

# 5. Propagate master's synthesis/ + component/ state to each seed clone
echo "==> [$(date -u +%H:%M:%SZ)] propagating master synth state to ${#SEEDS[@]} seed clones"
for s in "${SEEDS[@]}"; do
  rsync -a --delete "$WORK_BASE/master/synthesis/" "$WORK_BASE/$s/synthesis/"
  rsync -a --delete "$WORK_BASE/master/component/" "$WORK_BASE/$s/component/"
  rsync -a --delete "$WORK_BASE/master/designer/"  "$WORK_BASE/$s/designer/"
done

# 6. Generate per-seed P&R Tcl scripts
for s in "${SEEDS[@]}"; do
  # SEED is parsed from the dir name: prefix-stripped digits (e.g. "seed_7" -> 7)
  SEED_NUM=$(echo "$s" | grep -oE '[0-9]+' | head -1)
  sed -e "s|__SEED__|$SEED_NUM|g" \
      -e "s|__CLONE_DIR__|~/libero_seedsweep/$s|g" \
      "$SCRIPT_DIR/parallel_sweep_pnr.tcl.tmpl" > "$HOME/parallel_${s}.tcl"
done

# 7. Launch N parallel Libero P&R processes, disowned
echo "==> [$(date -u +%H:%M:%SZ)] launching ${#SEEDS[@]} parallel P&R Liberos"
for s in "${SEEDS[@]}"; do
  log="$WORK_BASE/${s}_run.log"
  done_marker="$WORK_BASE/${s}.DONE"
  fail_marker="$WORK_BASE/${s}.FAILED"
  rm -f "$done_marker" "$fail_marker"
  (
    cd "$HOME"
    "$LIBERO" "SCRIPT:~/parallel_${s}.tcl" >"$log" 2>&1
    rc=$?
    if [ $rc -eq 0 ] && grep -q "PARALLEL_SWEEP_SEED.*_DONE" "$log"; then
      date -u +%Y-%m-%dT%H:%M:%SZ > "$done_marker"
    else
      printf 'rc=%s\n' "$rc" > "$fail_marker"
      date -u +%Y-%m-%dT%H:%M:%SZ >> "$fail_marker"
    fi
  ) </dev/null >/dev/null 2>&1 &
  disown $!
  echo "    launched $s pid=$!"
done

echo "==> [$(date -u +%H:%M:%SZ)] all parallel P&Rs launched. Monitor: ls $WORK_BASE/*.DONE $WORK_BASE/*.FAILED"
echo "==> after completion, run parse_seed_slacks.sh to tabulate worst-slack per seed"
