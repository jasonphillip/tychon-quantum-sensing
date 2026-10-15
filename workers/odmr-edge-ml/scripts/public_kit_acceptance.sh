#!/usr/bin/env bash
# Fresh public checkout acceptance: five arguments, with all output outside Git trees.
set -euo pipefail

if [[ $# -ne 5 ]]; then
  echo 'usage: public_kit_acceptance.sh PUBLIC_URL PUBLIC_SHA KIT_URL KIT_SHA WORK_DIR' >&2
  exit 2
fi
public_url=$1
public_sha=$2
kit_url=$3
kit_sha=$4
work_dir=$5
if [[ ! $public_sha =~ ^[0-9a-f]{40}$ || ! $kit_sha =~ ^[0-9a-f]{40}$ ]]; then
  echo 'both revisions must be full 40-character Git SHAs' >&2
  exit 2
fi
mkdir -p "$work_dir"
work_dir=$(cd "$work_dir" && pwd -P)
if git -C "$work_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo 'work directory must be outside every checkout' >&2
  exit 2
fi
if [[ -n $(find "$work_dir" -mindepth 1 -maxdepth 1 -print -quit) ]]; then
  echo 'work directory must be empty' >&2
  exit 2
fi
public_dir="$work_dir/public"
kit_dir="$work_dir/kit"
receipt="$work_dir/receipt.txt"
output="$work_dir/recomputed-kit-metrics.json"
command_text='not reached'
public_head='not reached'
kit_head='not reached'
numpy_version='not reached'
python_version='not reached'
output_sha256='not reached'
checker_status='not reached'
public_status='not reached'
kit_status='not reached'

write_receipt() {
  status=$?
  {
    printf 'checker command: %s\n' "$command_text"
    printf 'exit status: %s\n' "$status"
    printf 'checker exit status: %s\n' "$checker_status"
    printf 'public commit: %s\n' "$public_head"
    printf 'kit commit: %s\n' "$kit_head"
    printf 'Python: %s\n' "$python_version"
    printf 'NumPy: %s\n' "$numpy_version"
    printf 'output SHA256: %s\n' "$output_sha256"
    printf 'public git status --porcelain: %s\n' "$public_status"
    printf 'kit git status --porcelain: %s\n' "$kit_status"
  } > "$receipt"
}
trap write_receipt EXIT

git clone --quiet "$public_url" "$public_dir"
git -C "$public_dir" checkout --quiet --detach "$public_sha"
public_head=$(git -C "$public_dir" rev-parse HEAD)
[[ $public_head == "$public_sha" ]]
git clone --quiet "$kit_url" "$kit_dir"
git -C "$kit_dir" checkout --quiet --detach "$kit_sha"
kit_head=$(git -C "$kit_dir" rev-parse HEAD)
[[ $kit_head == "$kit_sha" ]]
worker="$public_dir/workers/odmr-edge-ml"
recorded_kit_sha=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["external_kit_evidence"]["revision"])' \
  "$worker/docs/kit-run-2026-10-14/ARRAYS.manifest.json")
[[ $recorded_kit_sha =~ ^[0-9a-f]{40}$ && $kit_head == "$recorded_kit_sha" ]] || {
  echo 'kit checkout revision differs from recorded evidence revision' >&2
  exit 1
}

python3 -m venv "$work_dir/.venv"
"$work_dir/.venv/bin/python" -m pip --disable-pip-version-check install --no-input 'numpy==2.1.3'
python_version=$("$work_dir/.venv/bin/python" -c 'import sys; print(sys.version.split()[0])')
numpy_version=$("$work_dir/.venv/bin/python" -c 'import numpy; print(numpy.__version__)')

kit_evidence="$kit_dir/evidence/2026-10-14-deployed-fcnn"
cmd=("$work_dir/.venv/bin/python" "$worker/scripts/recompute_published_kit_metrics.py"
  --run-dir "$worker/docs/kit-run-2026-10-14"
  --hardware-evidence-dir "$kit_evidence"
  --expected-results "$worker/docs/kit-run-2026-10-14/results.json"
  --expected-constants "$worker/docs/kit_constant_baselines_2026-10.json"
  --verify-sha256 --no-network --atol-uT 0.000001 --out "$output")
printf -v command_text '%q ' "${cmd[@]}"
if "${cmd[@]}"; then
  checker_status=0
else
  checker_status=$?
  exit "$checker_status"
fi
output_sha256=$(sha256sum "$output")
output_sha256=${output_sha256%% *}
public_status=$(git -C "$public_dir" status --porcelain)
kit_status=$(git -C "$kit_dir" status --porcelain)
[[ -z $public_status && -z $kit_status ]] || { echo 'checkout changed during acceptance' >&2; exit 1; }
echo "PASS: $receipt"
