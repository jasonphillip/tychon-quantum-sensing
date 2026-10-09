#!/usr/bin/env bash
# Board runbook. Only wd_fallback_test writes the 0x60040000 slot-3 page.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
control="$repo/firmware/linux/wd_fallback_test"
observer="$repo/firmware/linux/wd_observer"
analyzer="$repo/tools/wd_fallback_analyze.py"
period_us=${PERIOD_US:-300}
control_core=${CONTROL_CORE:-1}
observer_core=${OBSERVER_CORE:-2}
out_min=${OUT_MIN:--1.0}
out_max=${OUT_MAX:-1.0}
model=${MODEL_PATH:-}
image_id=${IMAGE_ID:-}
room_temp=${ROOM_TEMPERATURE:-}
load=${OUTPUT_LOAD:-}
output_root=${OUTPUT_ROOT:-$repo/watchdog-runs}

if [[ -z $image_id || -z $model || -z $room_temp || -z $load || $control_core == "$observer_core" ]]; then
    printf '%s\n' 'Set IMAGE_ID, MODEL_PATH, ROOM_TEMPERATURE, OUTPUT_LOAD, and distinct CONTROL_CORE/OBSERVER_CORE before running.' >&2
    exit 2
fi
if [[ ! -x $control || ! -x $observer || ! -f $model ]]; then
    printf '%s\n' 'Both board binaries and MODEL_PATH must exist.' >&2
    exit 2
fi

# Fail closed before making any register write. wd_observer only maps the page read-only.
csr=$($observer --read-csr-version)
if [[ $csr != 0x00010000 ]]; then
    printf 'Refusing to run: csr_version=%s, expected 0x00010000\n' "$csr" >&2
    exit 1
fi
wd_start=$($observer --read-watchdog)
run_dir="$output_root/$(date -u +%Y%m%dT%H%M%SZ)-watchdog"
mkdir -p -- "$run_dir"
sha256sum -- "$control" "$observer" > "$run_dir/binary-sha256.txt"
{
    printf 'csr_version=%s\nwatchdog_at_start=%s\n' "$csr" "$wd_start"
    printf 'kernel='; uname -a
    printf 'repository_commit='; git -C "$repo" rev-parse HEAD
    printf 'image_id=%s\nroom_temperature=%s\noutput_load=%s\n' "$image_id" "$room_temp" "$load"
    printf 'period_us=%s\nout_min=%s\nout_max=%s\n' "$period_us" "$out_min" "$out_max"
    grep -nE 'WATCHDOG_TIMEOUT_CYCLES|WATCHDOG_COOLDOWN_CYCLES|MAX_SLEW_PER_CYCLE' "$repo/hls/include/rta_config.hpp"
} > "$run_dir/metadata.txt"

control_pid= observer_pid= cleaned=0
cleanup() {
    local rc=$?
    if (( cleaned )); then return; fi
    cleaned=1
    trap - EXIT INT TERM
    if [[ -n $control_pid ]]; then
        kill -CONT "$control_pid" 2>/dev/null || true
        kill -TERM "$control_pid" 2>/dev/null || true
        wait "$control_pid" 2>/dev/null || true
    fi
    if [[ -n $observer_pid ]]; then
        kill -TERM "$observer_pid" 2>/dev/null || true
        wait "$observer_pid" 2>/dev/null || true
    fi
    printf '%q ' "$control" --zero-and-exit >> "$run_dir/commands.txt"
    printf '\n' >> "$run_dir/commands.txt"
    "$control" --zero-and-exit > "$run_dir/zeroing.txt" 2>&1 || rc=1
    if ! grep -q '^post_clamp_q16=0 ' "$run_dir/zeroing.txt"; then rc=1; fi
    if (( rc )); then printf 'Abort or check failure; inspect %s and zeroing.txt. Power-cycle if readback is nonzero.\n' "$run_dir" >&2; fi
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

launch() {
    local scenario=$1 rep=$2; shift 2
    local stem="$run_dir/$scenario-$(printf '%02d' "$rep")"
    local obs_cmd=(taskset -c "$observer_core" "$observer")
    local ctl_cmd=(taskset -c "$control_core" "$control" "$@" --model "$model" --period-us "$period_us" --out-min "$out_min" --out-max "$out_max")
    printf '%q ' "${obs_cmd[@]}" >> "$run_dir/commands.txt"; printf '> %q\n' "$stem-observer.csv" >> "$run_dir/commands.txt"
    printf '%q ' "${ctl_cmd[@]}" >> "$run_dir/commands.txt"; printf '> %q 2> %q\n' "$stem-control.csv" "$stem-control.stderr" >> "$run_dir/commands.txt"
    "${obs_cmd[@]}" > "$stem-observer.csv" 2> "$stem-observer.stderr" & observer_pid=$!
    sleep 0.1
    if ! kill -0 "$observer_pid" 2>/dev/null; then
        printf 'Observer failed to start; see %s-observer.stderr\n' "$stem" >&2
        return 1
    fi
    "${ctl_cmd[@]}" > "$stem-control.csv" 2> "$stem-control.stderr" & control_pid=$!
}
finish() {
    local scenario=$1 rep=$2
    local stem="$run_dir/$scenario-$(printf '%02d' "$rep")"
    wait "$control_pid"
    control_pid=
    kill -TERM "$observer_pid" 2>/dev/null || true
    wait "$observer_pid" 2>/dev/null || true
    observer_pid=
    if [[ $scenario == dry ]]; then
        # Every control row must have timeout bit 0 after its inference.
        awk -F, 'NR > 2 && $9 != 0 {bad=1} END {exit bad}' "$stem-control.csv"
        return
    fi
    local analysis_cmd=(python3 "$analyzer" "$stem-observer.csv" "$stem-control.csv" --scenario "$scenario" --period-us "$period_us" --out-dir "$stem-analysis")
    printf '%q ' "${analysis_cmd[@]}" >> "$run_dir/commands.txt"; printf '\n' >> "$run_dir/commands.txt"
    "${analysis_cmd[@]}" > "$stem-analysis.stdout"
}

# Precondition: 60 s normal mode, with no timeout reported in control rows.
launch dry 1 normal --updates "$((60000000 / period_us))"
finish dry 1

# Ten SIGSTOP/SIGCONT pauses, five seconds of normal operation between pauses.
launch a 1 normal --updates "$((180000000 / period_us))"
sleep 5
for rep in {1..10}; do
    printf 'kill -STOP %q; sleep 1; kill -CONT %q; sleep 5\n' "$control_pid" "$control_pid" >> "$run_dir/commands.txt"
    kill -STOP "$control_pid"
    sleep 1
    kill -CONT "$control_pid"
    sleep 5
done
kill -TERM "$control_pid"
finish a 1

for rep in {1..20}; do
    launch b1 "$rep" skip-inference-after "$((1000000 / period_us))" --updates "$((1000000 / period_us + 2000))"
    finish b1 "$rep"
    sleep 2
done
for rep in {1..20}; do
    if (( rep <= 3 )); then
        launch b2 "$rep" resume-after "$((1000000 / period_us))" 200 --repeat-trips 3 --updates "$((1000000 / period_us + 3400))"
    else
        launch b2 "$rep" resume-after "$((1000000 / period_us))" 200 --updates "$((1000000 / period_us + 1100))"
    fi
    finish b2 "$rep"
    sleep 2
done
for rep in {1..20}; do
    launch c1 "$rep" gap-then-inference 2500 --gap-after "$((1000000 / period_us))" --updates "$((1000000 / period_us + 1100))"
    finish c1 "$rep"
    sleep 2
done
for rep in {1..20}; do
    launch c0 "$rep" gap-then-inference 2500 2200 --gap-after "$((1000000 / period_us))" --updates "$((1000000 / period_us + 1100))"
    finish c0 "$rep"
    sleep 2
done
printf 'Logs: %s\n' "$run_dir"
