#!/usr/bin/env bash
# Copied 2026-10-10 from ~/cjobs.sh (plan C GPU queue runner; also present on ws3 and ws4 at that path).
# Lessons: GNU timeout takes plain durations (270m, not 4h30m); one training job at a time on ws2 (psi-guard);
# run with `taskset -c <perf core>`; never overwrite a running queue script in place (bash reads by offset).
# Plan C GPU job queue (2026-10-09). Usage: cjobs.sh <queue-file>. Lines:
#   RUN <name> <timeout> <worktree> <script> <args...>   train under timeout --signal=INT; log $A/logs/<name>.log
#   WAIT <path> [path...]                                 block until every path exists (24 h max)
#   PUSH <path> <host> [host...]                          rsync -a path to the same path on each host
#   WAITDONE <name> [name...]                             block until $A/logs/<name>.status has an "end" line
# Status: $A/logs/<name>.status gets "start <epoch>" then "end <epoch> rc=<rc>".
set -uo pipefail
Q=$1
A=~/projects/odmr-vector-tracking/artifacts/portfolio-c
mkdir -p "$A/logs"
if [ -x ~/miniconda3/envs/ctrain/bin/python ]; then PY=~/miniconda3/envs/ctrain/bin/python; else PY=~/miniconda3/bin/python3; fi
NVS=~/projects/nv-sensor-sim/src
export PYTHONUNBUFFERED=1
echo "queue $Q on $(hostname) py=$PY start $(date -Is)" >> "$A/logs/queues.log"
while read -r op rest <&3; do
  [ -z "${op:-}" ] && continue; case "$op" in \#*) continue;; esac
  set -- $rest
  case "$op" in
    RUN)
      name=$1; to=$2; wt=$3; script=$4; shift 4
      if grep -q '^end .* rc=0' "$A/logs/$name.status" 2>/dev/null; then echo "skip $name (done)" >> "$A/logs/queues.log"; continue; fi
      echo "start $(date +%s)" > "$A/logs/$name.status"
      ( cd "$wt" && PYTHONPATH="$wt/src:$NVS" timeout --signal=INT "$to" "$PY" "$script" "$@" ) < /dev/null > "$A/logs/$name.log" 2>&1
      rc=$?; echo "end $(date +%s) rc=$rc" >> "$A/logs/$name.status"
      echo "$(date -Is) $name rc=$rc" >> "$A/logs/queues.log" ;;
    WAIT)
      for p in "$@"; do n=0; until [ -e "$p" ]; do sleep 60; n=$((n+1)); [ $n -gt 1440 ] && { echo "WAIT timeout $p" >> "$A/logs/queues.log"; exit 3; }; done; done ;;
    WAITDONE)
      for nm in "$@"; do n=0; until grep -q '^end ' "$A/logs/$nm.status" 2>/dev/null; do sleep 60; n=$((n+1)); [ $n -gt 1440 ] && { echo "WAITDONE timeout $nm" >> "$A/logs/queues.log"; exit 3; }; done; done ;;
    PUSH)
      p=$1; shift
      for h in "$@"; do ssh -n -o BatchMode=yes "$h" "mkdir -p '$(dirname "$p")'" && rsync -a "$p" "$h:$(dirname "$p")/" && echo "$(date -Is) pushed $p -> $h" >> "$A/logs/queues.log"; done ;;
    *) echo "bad op $op" >> "$A/logs/queues.log"; exit 2 ;;
  esac
done 3< "$Q"
echo "queue $Q done $(date -Is)" >> "$A/logs/queues.log"
