#!/usr/bin/env bash
# generate_repo_snapshot.sh — Produces repo2-status-snapshot.md for cross-machine sharing
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST_DIR="~/Desktop/Shared/tychon-nv-sim-repos"
DATE_STAMP=$(date +%Y-%m-%d)
DEST_FILE="${DEST_DIR}/repo2-status-snapshot-${DATE_STAMP}.md"
PREV_SHA=""

cd "$REPO_ROOT"

# If a previous snapshot exists, extract the recorded git SHA for changelog diff
for prev in "${DEST_DIR}"/repo2-status-snapshot-*.md; do
    [[ -f "$prev" ]] || continue
    PREV_SHA=$(grep -oP '(?<=Git SHA: )`\K[a-f0-9]+' "$prev" 2>/dev/null || true)
done

CURRENT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "no-commits")
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

# ---------------------------------------------------------------------------
# Start building the markdown
# ---------------------------------------------------------------------------
{

cat <<EOF
# Repo 2 Status Snapshot — tychon-odmr-ml

**Generated:** ${TIMESTAMP}
**Git SHA:** \`${CURRENT_SHA}\`
**Branch:** $(git branch --show-current 2>/dev/null || echo "n/a")
**Machine:** $(hostname)

---

## 1. File Tree

\`\`\`
EOF

find . -type f \
    | grep -v __pycache__ \
    | grep -v '.git/' \
    | grep -v '.venv' \
    | grep -v '.egg-info' \
    | grep -v '.ruff_cache' \
    | grep -v '.pytest_cache' \
    | sort

cat <<'EOF'
```

---

## 2. Dependency Status

| Package | Installed | Version |
|---------|-----------|---------|
EOF

for pkg in torch numpy h5py yaml scipy; do
    import_name="$pkg"
    display_name="$pkg"
    if [[ "$pkg" == "yaml" ]]; then
        display_name="pyyaml"
    fi
    result=$(python3 -c "
try:
    import ${import_name}; v = getattr(${import_name}, '__version__', 'yes')
    print(f'| ${display_name} | ✓ | {v} |')
except ImportError:
    print(f'| ${display_name} | ✗ | — |')
" 2>/dev/null || echo "| ${display_name} | error | — |")
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

### Config
```python
EOF

python3 -W ignore -c "
import dataclasses
from tychon_odmr_ml.config import Config
print('@dataclass')
print('class Config:')
for f in dataclasses.fields(Config):
    if f.default is not dataclasses.MISSING:
        print(f'    {f.name}: {f.type} = {f.default!r}')
    elif f.default_factory is not dataclasses.MISSING:
        print(f'    {f.name}: {f.type} = field(default_factory=...)')
    else:
        print(f'    {f.name}: {f.type}')
" 2>/dev/null || echo "# Could not extract Config"

cat <<'EOF'
```

### DatasetLoader
```python
EOF

python3 -W ignore -c "
import inspect
from tychon_odmr_ml.data.loaders import DatasetLoader
for name, method in inspect.getmembers(DatasetLoader, predicate=inspect.isfunction):
    if not name.startswith('_') or name == '__init__':
        sig = inspect.signature(method)
        print(f'def {name}{sig}')
" 2>/dev/null || echo "# Could not extract DatasetLoader"

cat <<'EOF'
```

### contracts.py
```python
EOF

python3 -W ignore -c "
import inspect
from tychon_odmr_ml.data import contracts
for name, fn in inspect.getmembers(contracts, predicate=inspect.isfunction):
    if not name.startswith('_'):
        sig = inspect.signature(fn)
        print(f'def {name}{sig}')
" 2>/dev/null || echo "# Could not extract contracts"

cat <<'EOF'
```

### OdmrMLP (Architecture A)
```python
EOF

python3 -W ignore -c "
import inspect
from tychon_odmr_ml.models.mlp import OdmrMLP
sig = inspect.signature(OdmrMLP.__init__)
print(f'class OdmrMLP(nn.Module):')
print(f'    def __init__{sig}')
print(f'    def forward(self, x: Tensor) -> Tensor:')
print(f'        \"\"\"x: (batch, input_dim) → (batch, output_dim)\"\"\"')
m = OdmrMLP()
n = sum(p.numel() for p in m.parameters())
print(f'    # Default params: {n:,}')
" 2>/dev/null || echo "# Could not extract OdmrMLP"

cat <<'EOF'
```

### OdmrCNN1D (Architecture B)
```python
EOF

python3 -W ignore -c "
import inspect
from tychon_odmr_ml.models.cnn1d import OdmrCNN1D
sig = inspect.signature(OdmrCNN1D.__init__)
print(f'class OdmrCNN1D(nn.Module):')
print(f'    def __init__{sig}')
print(f'    def forward(self, x: Tensor) -> Tensor:')
print(f'        \"\"\"x: (batch, input_dim) → (batch, output_dim)\"\"\"')
m = OdmrCNN1D()
n = sum(p.numel() for p in m.parameters())
print(f'    # Default params: {n:,}')
" 2>/dev/null || echo "# Could not extract OdmrCNN1D"

cat <<'EOF'
```

### OpsGuard
```python
EOF

python3 -W ignore -c "
import inspect
from tychon_odmr_ml.validation.ops_guard import check_model_ops, OpsReport
sig = inspect.signature(check_model_ops)
print(f'def check_model_ops{sig} -> OpsReport')
print()
print('@dataclass')
print('class OpsReport:')
print('    allowed: list[str]')
print('    disallowed: list[str]')
print('    unknown: list[str]')
print('    is_compatible: bool  # property')
" 2>/dev/null || echo "# Could not extract OpsGuard"

cat <<'EOF'
```

### PidProxy (baseline)
```python
EOF

python3 -W ignore -c "
import inspect
from tychon_odmr_ml.baselines.pid_proxy import PidProxy
for name, method in inspect.getmembers(PidProxy, predicate=inspect.isfunction):
    if not name.startswith('_') or name == '__init__':
        sig = inspect.signature(method)
        print(f'def {name}{sig}')
" 2>/dev/null || echo "# Could not extract PidProxy"

cat <<'EOF'
```

---

## 6. Working Capabilities

EOF

echo "| Capability | Status |"
echo "|------------|--------|"

# Can load golden data?
result=$(python3 -W ignore -c "
from tychon_odmr_ml.data.loaders import DatasetLoader
loader = DatasetLoader('$HOME/projects/tychon-shared-data/golden')
ds = loader.load_split('train')
assert ds.spectra.shape == (100, 100)
assert ds.labels.shape == (100, 3)
print('PASS')
" 2>&1) && echo "| Load golden dataset | ✓ ${result} |" || echo "| Load golden dataset | ✗ ${result} |"

# Can validate manifest?
result=$(python3 -W ignore -c "
from tychon_odmr_ml.data.contracts import validate_manifest_file
m = validate_manifest_file('$HOME/projects/tychon-shared-data/golden/manifest.json')
assert len(m) == 23
print('PASS')
" 2>&1) && echo "| Validate Repo 1 manifest | ✓ ${result} |" || echo "| Validate Repo 1 manifest | ✗ ${result} |"

# Can run MLP forward pass?
result=$(python3 -W ignore -c "
import torch
from tychon_odmr_ml.data.loaders import DatasetLoader
from tychon_odmr_ml.models.mlp import OdmrMLP
loader = DatasetLoader('$HOME/projects/tychon-shared-data/golden')
ds = loader.to_torch('test')
spectra, labels = ds[:]
model = OdmrMLP()
model.eval()
with torch.no_grad():
    out = model(spectra)
assert out.shape == (20, 3)
assert torch.isfinite(out).all()
print('PASS')
" 2>&1) && echo "| MLP forward pass (golden test) | ✓ ${result} |" || echo "| MLP forward pass (golden test) | ✗ ${result} |"

# Can run CNN forward pass?
result=$(python3 -W ignore -c "
import torch
from tychon_odmr_ml.data.loaders import DatasetLoader
from tychon_odmr_ml.models.cnn1d import OdmrCNN1D
loader = DatasetLoader('$HOME/projects/tychon-shared-data/golden')
ds = loader.to_torch('test')
spectra, labels = ds[:]
model = OdmrCNN1D()
model.eval()
with torch.no_grad():
    out = model(spectra)
assert out.shape == (20, 3)
assert torch.isfinite(out).all()
print('PASS')
" 2>&1) && echo "| CNN forward pass (golden test) | ✓ ${result} |" || echo "| CNN forward pass (golden test) | ✗ ${result} |"

# Can run PID baseline?
result=$(python3 -W ignore -c "
from tychon_odmr_ml.data.loaders import DatasetLoader
from tychon_odmr_ml.baselines.pid_proxy import PidProxy
loader = DatasetLoader('$HOME/projects/tychon-shared-data/golden')
ds = loader.load_split('test')
m = loader.manifest
pid = PidProxy(n_freq_points=m['n_freq_points'], freq_range_hz=tuple(m['freq_range_Hz']))
estimates = pid.estimate_batch(ds.spectra)
assert estimates.shape == (20, 3)
print('PASS')
" 2>&1) && echo "| PID baseline (golden test) | ✓ ${result} |" || echo "| PID baseline (golden test) | ✗ ${result} |"

# VectorBlox ops guard?
result=$(python3 -W ignore -c "
from tychon_odmr_ml.models.mlp import OdmrMLP
from tychon_odmr_ml.models.cnn1d import OdmrCNN1D
from tychon_odmr_ml.validation.ops_guard import check_model_ops
r1 = check_model_ops(OdmrMLP())
r2 = check_model_ops(OdmrCNN1D())
assert r1.is_compatible and r2.is_compatible
print(f'PASS (MLP: {len(r1.allowed)} ops, CNN: {len(r2.allowed)} ops)')
" 2>&1) && echo "| VectorBlox ops guard (both models) | ✓ ${result} |" || echo "| VectorBlox ops guard (both models) | ✗ ${result} |"

cat <<'EOF'

---

## 7. Known Issues / TODOs

```
EOF

grep -rn 'TODO\|FIXME\|HACK\|XXX' src/ 2>/dev/null || echo "None found."

cat <<'EOF'
```

---

## 8. Git Status

### Recent Commits
```
EOF

git log --oneline -20 2>/dev/null || echo "(no commits yet)"

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

## 9. Changes Since Last Snapshot

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
