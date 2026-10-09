#!/usr/bin/env bash
# Production-loop check for the trip-start fix: rate before/after, and forced starts on real pauses.
set -u
M=/root/bringup/fcnn_v2_residual_dataset_a.vnnx; ROWS=/root/bringup/odmr_v250_rows.csv
OLD=/root/bringup/v250_pid_loop.pre-fix; NEW=/root/pfhc/firmware/linux/v250_pid_loop
O=/root/prodcheck-$(date -u +%Y%m%dT%H%M%SZ); mkdir -p $O; cd $O
sha256sum $OLD $NEW > sha256.txt
rate() { awk -F, 'NR>2 && $2+0>0 {n++; last=$2} END {printf "rows=%d elapsed_s=%.3f rate_hz=%.1f\n", n, last/1e9, n/(last/1e9)}' "$1"; }
taskset -c 2 $OLD $M 10000 2 $ROWS > old.csv 2> old.err; echo "old rc=$? $(rate old.csv)"
taskset -c 2 $NEW $M 10000 2 $ROWS > new.csv 2> new.err; echo "new rc=$? $(rate new.csv) forced=$(grep -c forced_start new.err)"
taskset -c 2 $NEW $M 10000 2 $ROWS --no-trip-start > new_off.csv 2> new_off.err; echo "new --no-trip-start rc=$? $(rate new_off.csv) forced=$(grep -c forced_start new_off.err)"
taskset -c 2 $NEW $M 10000 2 $ROWS --daemon > pause.csv 2> pause.err & P=$!
sleep 3; for k in 1 2 3 4 5; do kill -STOP $P; sleep 0.05; kill -CONT $P; sleep 2; done; sleep 1; kill -TERM $P; wait $P; echo "pause run rc=$? $(rate pause.csv) forced=$(grep -c forced_start pause.err)"
grep forced_start pause.err | head -8
cmp -s <(head -2 old.csv | tail -1) <(head -2 new.csv | tail -1) && echo "CSV header unchanged" || echo "CSV header CHANGED"
/root/pfhc/firmware/linux/wd_fallback_test --zero-and-exit 2>&1 | tail -1
echo "dir=$O"
