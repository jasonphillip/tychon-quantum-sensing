#!/usr/bin/env bash
# generate_repo_snapshot.sh — Produces repo1-status-snapshot.md for cross-machine sharing
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST_DIR="~/shared/tychon-nv-sim-repos"
DEST_FILE="${DEST_DIR}/repo1-status-snapshot.md"
PREV_SHA=""

cd "$REPO_ROOT"

# If a previous snapshot exists, extract the recorded git SHA for changelog diff
if [[ -f "$DEST_FILE" ]]; then
    PREV_SHA=$(grep -oP '(?<=Git SHA: )`\K[a-f0-9]+' "$DEST_FILE" 2>/dev/null || true)
fi

CURRENT_SHA=$(git rev-parse --short HEAD)
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

# ---------------------------------------------------------------------------
# Start building the markdown
# ---------------------------------------------------------------------------
{

cat <<EOF
# Repo 1 Status Snapshot — tychon-nv-sim

**Generated:** ${TIMESTAMP}
**Git SHA:** \`${CURRENT_SHA}\`
**Branch:** $(git branch --show-current)
**Machine:** $(hostname)

---

## 1. File Tree

\`\`\`
EOF

find . -type f \
    | grep -v __pycache__ \
    | grep -v '.git/' \
    | grep -v node_modules \
    | grep -v '.venv' \
    | grep -v '.egg-info' \
    | grep -v '.ruff_cache' \
    | grep -v '.serena/' \
    | sort

cat <<'EOF'
```

---

## 2. Dependency Status

| Package | Installed | Version |
|---------|-----------|---------|
EOF

for pkg in simos qutip cudaq cuquantum h5py numpy scipy sympy pandas; do
    result=$(python3 -c "
try:
    import ${pkg}; v = getattr(${pkg}, '__version__', 'yes')
    print(f'| ${pkg} | ✓ | {v} |')
except ImportError:
    print(f'| ${pkg} | ✗ | — |')
" 2>/dev/null || echo "| ${pkg} | error | — |")
    echo "$result"
done

cat <<'EOF'

---

## 3. Test Results

```
EOF

python3 -m pytest tests/ -v --tb=short 2>&1 | tail -80 || true

cat <<'EOF'
```

---

## 4. Module Status Table

| File | Lines | Status |
|------|-------|--------|
EOF

find src/ -name '*.py' -type f | sort | while read -r f; do
    lines=$(wc -l < "$f" 2>/dev/null || echo 0)
    if grep -qE 'NotImplementedError|raise NotImplementedError|pass\s*$' "$f" 2>/dev/null; then
        has_stub="yes"
    else
        has_stub="no"
    fi
    # Check if file has real implementation beyond stubs/imports/docstrings
    real_lines=$(grep -cvE '^\s*$|^\s*#|^\s*"""|^\s*import |^\s*from |^\s*pass\s*$|NotImplementedError|^\s*def |^\s*class |^\s*@' "$f" 2>/dev/null || echo "0")
    real_lines=$(echo "$real_lines" | tail -1)
    if [[ "$real_lines" -lt 3 ]]; then
        status="stub-only"
    elif [[ "$has_stub" == "yes" ]]; then
        status="partial (has stubs)"
    else
        status="implemented"
    fi
    echo "| \`${f}\` | ${lines} | ${status} |"
done

cat <<'EOF'

---

## 5. Public API Surface

### SimulationConfig (dataclass)
```python
EOF

python3 -W ignore -c "
import dataclasses
from tychon_nv_sim.config import SimulationConfig
print('@dataclass')
print('class SimulationConfig:')
for f in dataclasses.fields(SimulationConfig):
    print(f'    {f.name}: {f.type} = {f.default!r}' if f.default is not dataclasses.MISSING else f'    {f.name}: {f.type} = field(...)')
" 2>/dev/null || echo "# Could not extract SimulationConfig"

cat <<'EOF'
```

### SimOSAdapter.generate_odmr_spectrum()
```python
EOF

python3 -W ignore -c "
import inspect
from tychon_nv_sim.adapters.simos_adapter import SimOSAdapter
sig = inspect.signature(SimOSAdapter.generate_odmr_spectrum)
print(f'def generate_odmr_spectrum{sig}')
" 2>/dev/null || echo "# Could not extract signature"

cat <<'EOF'
```

### corrupt_spectrum()
```python
EOF

python3 -W ignore -c "
import inspect
from tychon_nv_sim.physics.lineshape import corrupt_spectrum
sig = inspect.signature(corrupt_spectrum)
print(f'def corrupt_spectrum{sig}')
" 2>/dev/null || echo "# Could not extract signature"

cat <<'EOF'
```

### DatasetManifest (dataclass)
```python
EOF

python3 -W ignore -c "
import dataclasses, inspect
from tychon_nv_sim.datasets.schema import DatasetManifest
print('@dataclass')
print('class DatasetManifest:')
for f in dataclasses.fields(DatasetManifest):
    if f.default is not dataclasses.MISSING:
        print(f'    {f.name}: {f.type} = {f.default!r}')
    elif f.default_factory is not dataclasses.MISSING:
        print(f'    {f.name}: {f.type} = field(default_factory=...)')
    else:
        print(f'    {f.name}: {f.type}')
print()
for name, method in inspect.getmembers(DatasetManifest, predicate=inspect.isfunction):
    if not name.startswith('_') or name == '__post_init__':
        sig = inspect.signature(method)
        print(f'    def {name}{sig}')
" 2>/dev/null || echo "# Could not extract DatasetManifest"

cat <<'EOF'
```

### generate_dataset() (batch pipeline)
```python
EOF

python3 -W ignore -c "
import inspect
from tychon_nv_sim.pipelines.batch_generate import generate_dataset
sig = inspect.signature(generate_dataset)
print(f'def generate_dataset{sig}')
" 2>/dev/null || echo "# Could not extract signature"

cat <<'EOF'
```

### DatasetWriter
```python
EOF

python3 -W ignore -c "
import inspect
from tychon_nv_sim.datasets.writer import DatasetWriter
for name, method in inspect.getmembers(DatasetWriter, predicate=inspect.isfunction):
    if not name.startswith('_') or name == '__init__':
        sig = inspect.signature(method)
        print(f'def {name}{sig}')
" 2>/dev/null || echo "# Could not extract DatasetWriter"

cat <<'EOF'
```

### DatasetLoader
```python
EOF

python3 -W ignore -c "
import inspect
from tychon_nv_sim.datasets.loaders import DatasetLoader
for name, method in inspect.getmembers(DatasetLoader, predicate=inspect.isfunction):
    if not name.startswith('_') or name == '__init__':
        sig = inspect.signature(method)
        print(f'def {name}{sig}')
" 2>/dev/null || echo "# Could not extract DatasetLoader"

cat <<'EOF'
```

### Validation (reference_comparison)
```python
EOF

python3 -W ignore -c "
import inspect
import tychon_nv_sim.validation.reference_comparison as rc
for name, fn in inspect.getmembers(rc, predicate=inspect.isfunction):
    if not name.startswith('_'):
        sig = inspect.signature(fn)
        ret = fn.__annotations__.get('return', '')
        ret_str = f' -> {ret}' if ret else ''
        print(f'def {name}{sig}{ret_str}')
" 2>/dev/null || echo "# Could not extract validation signatures"

cat <<'EOF'
```

---

## 6. Working Capabilities

EOF

# Test actual capabilities by running quick smoke checks
echo "| Capability | Status |"
echo "|------------|--------|"

# Can generate a single spectrum?
result=$(python3 -W ignore -c "
from tychon_nv_sim.adapters.simos_adapter import SimOSAdapter
from tychon_nv_sim.config import SimulationConfig
cfg = SimulationConfig()
adapter = SimOSAdapter(cfg)
freqs, signal = adapter.generate_odmr_spectrum()
assert len(freqs) == 100 and len(signal) == 100
print('PASS')
" 2>&1) && echo "| Generate single ODMR spectrum | ✓ ${result} |" || echo "| Generate single ODMR spectrum | ✗ ${result} |"

# Can corrupt a spectrum?
result=$(python3 -W ignore -c "
from tychon_nv_sim.adapters.simos_adapter import SimOSAdapter
from tychon_nv_sim.config import SimulationConfig
from tychon_nv_sim.physics.lineshape import corrupt_spectrum
cfg = SimulationConfig()
adapter = SimOSAdapter(cfg)
freqs, signal, params = corrupt_spectrum(adapter, cfg, b1_gradient_frac=0.1, b_perp_T=10e-6)
assert len(freqs) == 100
print('PASS')
" 2>&1) && echo "| Corrupt spectrum (B1 gradient + B_perp) | ✓ ${result} |" || echo "| Corrupt spectrum (B1 gradient + B_perp) | ✗ ${result} |"

# Can write a manifest?
result=$(python3 -W ignore -c "
import tempfile, os
from tychon_nv_sim.datasets.schema import DatasetManifest
m = DatasetManifest(master_seed=42, train_seeds=[1,2], val_seeds=[3], test_seeds=[4],
                    n_spectra_train=2, n_spectra_val=1, n_spectra_test=1,
                    train_indices=[0,1], val_indices=[2], test_indices=[3])
m.validate()
d = tempfile.mkdtemp()
m.to_json(os.path.join(d, 'manifest.json'))
m2 = DatasetManifest.from_json(os.path.join(d, 'manifest.json'))
assert m2.master_seed == 42
print('PASS')
" 2>&1) && echo "| Write + read manifest JSON | ✓ ${result} |" || echo "| Write + read manifest JSON | ✗ ${result} |"

# Can run batch pipeline?
result=$(python3 -W ignore -c "
import tempfile, io, sys
sys.stdout = io.StringIO()
from tychon_nv_sim.pipelines.batch_generate import generate_dataset
d = tempfile.mkdtemp()
path = generate_dataset(output_dir=d, n_train=2, n_val=1, n_test=1)
sys.stdout = sys.__stdout__
print('PASS')
" 2>&1) && echo "| Batch pipeline (generate_dataset) | ✓ ${result} |" || echo "| Batch pipeline (generate_dataset) | ✗ ${result} |"

# Can load experimental data?
result=$(python3 -W ignore -c "
from tychon_nv_sim.validation.reference_comparison import load_experimental_odmr
import glob
csvs = glob.glob('data/experimental/zenodo_odmr/*.csv')
if not csvs:
    print('NO DATA FILES')
else:
    f, s = load_experimental_odmr(csvs[0])
    assert len(f) > 0
    print(f'PASS ({len(csvs)} files)')
" 2>&1) && echo "| Load experimental ODMR data | ✓ ${result} |" || echo "| Load experimental ODMR data | ✗ ${result} |"

cat <<'EOF'

---

## 7. Data Contract Readiness (Section 3.4)

EOF

python3 -W ignore -c "
required_fields = {
    'generator_git_sha': 'provenance',
    'config_hash': 'provenance',
    'simos_version': 'provenance',
    'qutip_version': 'provenance',
    'backend': 'provenance',
    'generated_at': 'provenance',
    'master_seed': 'seeds',
    'train_seeds': 'seeds',
    'val_seeds': 'seeds',
    'test_seeds': 'seeds',
    'n_spectra_train': 'splits',
    'n_spectra_val': 'splits',
    'n_spectra_test': 'splits',
    'train_indices': 'splits',
    'val_indices': 'splits',
    'test_indices': 'splits',
    'n_freq_points': 'spectral',
    'freq_range_Hz': 'spectral',
    'p1_concentration_range_ppm': 'corruption',
    'temperature_range_K': 'corruption',
    'b1_gradient_range': 'corruption',
    'b_perp_range_T': 'corruption',
    'units': 'units',
}

from tychon_nv_sim.datasets.schema import DatasetManifest
import dataclasses
manifest_fields = {f.name for f in dataclasses.fields(DatasetManifest)}

print('| Contract Field | Category | Implemented |')
print('|----------------|----------|-------------|')
for field, cat in required_fields.items():
    status = '✓' if field in manifest_fields else '✗ MISSING'
    print(f'| \`{field}\` | {cat} | {status} |')

missing = [f for f in required_fields if f not in manifest_fields]
if missing:
    print(f'\n**Missing fields:** {len(missing)}')
else:
    print('\n**All contract fields implemented.**')
" 2>/dev/null || echo "Could not check data contract."

cat <<'EOF'

---

## 8. Known Issues / TODOs

EOF

echo '```'
grep -rn 'TODO\|FIXME\|HACK\|XXX' src/ 2>/dev/null || echo "None found."
echo '```'

cat <<'EOF'

---

## 9. Git Status

### Recent Commits
```
EOF

git log --oneline -20

cat <<'EOF'
```

### Working Tree
```
EOF

git status --short

cat <<'EOF'
```
EOF

# ---------------------------------------------------------------------------
# Changelog vs previous snapshot
# ---------------------------------------------------------------------------
cat <<'EOF'

---

## 10. Changes Since Last Snapshot

EOF

if [[ -n "$PREV_SHA" ]] && git rev-parse "$PREV_SHA" >/dev/null 2>&1; then
    echo "Diff from \`${PREV_SHA}\` → \`${CURRENT_SHA}\`:"
    echo ""
    echo '```'
    git diff --stat "${PREV_SHA}..${CURRENT_SHA}" 2>/dev/null || echo "Could not compute diff."
    echo '```'
    echo ""
    echo "### Commits"
    echo '```'
    git log --oneline "${PREV_SHA}..${CURRENT_SHA}" 2>/dev/null || echo "No new commits."
    echo '```'
else
    echo "*First snapshot — no prior version to diff against.*"
fi

} > "$DEST_FILE"

echo ""
echo "Snapshot written to ${DEST_FILE}"
