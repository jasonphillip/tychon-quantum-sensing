#!/usr/bin/env bash
# Fresh public checkout; all generated files stay outside the checkout.
set -euo pipefail
if [[ $# -ne 3 ]]; then
  echo 'usage: public_scalar_validation_acceptance.sh PUBLIC_URL PUBLIC_SHA EMPTY_WORK_DIR' >&2
  exit 2
fi
public_url=$1
public_sha=$2
work_dir=$3
if [[ ! $public_sha =~ ^[0-9a-f]{40}$ ]]; then
  echo 'PUBLIC_SHA must be a full 40-character Git SHA' >&2
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
checkout="$work_dir/public"
receipt="$work_dir/receipt.txt"
output="$work_dir/recomputed-scalar-validation.json"
command_text='not reached'
public_head='not reached'
python_version='not reached'
numpy_version='not reached'
output_sha256='not reached'
checker_status='not reached'
public_status='not reached'
write_receipt() {
  status=$?
  {
    printf 'checker command: %s\n' "$command_text"
    printf 'exit status: %s\n' "$status"
    printf 'checker exit status: %s\n' "$checker_status"
    printf 'public commit: %s\n' "$public_head"
    printf 'Python: %s\n' "$python_version"
    printf 'NumPy: %s\n' "$numpy_version"
    printf 'output SHA256: %s\n' "$output_sha256"
    printf 'public git status --porcelain: %s\n' "$public_status"
  } > "$receipt"
}
trap write_receipt EXIT
git clone --quiet "$public_url" "$checkout"
git -C "$checkout" checkout --quiet --detach "$public_sha"
public_head=$(git -C "$checkout" rev-parse HEAD)
[[ $public_head == "$public_sha" ]]
python3 -m venv "$work_dir/.venv"
"$work_dir/.venv/bin/python" -m pip --disable-pip-version-check install --no-input 'numpy==2.1.3'
python_version=$("$work_dir/.venv/bin/python" -c 'import sys; print(sys.version.split()[0])')
numpy_version=$("$work_dir/.venv/bin/python" -c 'import numpy; print(numpy.__version__)')
worker="$checkout/workers/odmr-edge-ml"
bundle_manifest_sha=$(sed -n 's/^BUNDLE\.manifest\.json sha256: \([0-9a-f]\{64\}\)$/\1/p' "$worker/docs/scalar_repair_cycle_2026-10.md")
[[ $bundle_manifest_sha =~ ^[0-9a-f]{64}$ ]] || { echo 'recorded bundle manifest SHA256 missing' >&2; exit 1; }
cmd=("$work_dir/.venv/bin/python" "$worker/scripts/recompute_published_scalar_validation.py"
  --bundle "$worker/docs/scalar_repair_cycle_2026-10" --no-network
  --expected-bundle-manifest-sha256 "$bundle_manifest_sha" --cross-check-truth --out "$output")
printf -v command_text '%q ' "${cmd[@]}"
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
if flock -w 3600 "$work_dir/numerical.lock" /usr/bin/time -v "${cmd[@]}"; then
  checker_status=0
else
  checker_status=$?
  exit "$checker_status"
fi
output_sha256=$(sha256sum "$output")
output_sha256=${output_sha256%% *}
public_status=$(git -C "$checkout" status --porcelain)
[[ -z $public_status ]] || { echo 'checkout changed during acceptance' >&2; exit 1; }
echo "PASS: $receipt"
