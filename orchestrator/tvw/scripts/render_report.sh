#!/usr/bin/env bash
set -euo pipefail
SRC="${1:-$HOME/.corpus/tychon-docs/raw/report/Tychon_Phase_I_Final_Report_v3.1_2026-05-01.md}"
OUT_DIR="${2:-$HOME/Desktop/Shared/tychon-nv-sim-repos/01_deliverables/final_report}"
REFERENCE="${3:-$OUT_DIR/Tychon_Phase_I_Final_Report_2026-04-30.docx}"
BASE=$(basename "$SRC" .md)

REF_ARG=()
if [ -n "$REFERENCE" ] && [ -f "$REFERENCE" ]; then
  REF_ARG=(--reference-doc="$REFERENCE")
fi

pandoc "$SRC" -o "$OUT_DIR/${BASE}.docx" \
  "${REF_ARG[@]}" \
  --from=markdown+yaml_metadata_block+pipe_tables+grid_tables+citations+raw_html \
  --to=docx --toc --toc-depth=3 --number-sections \
  --metadata title="Tychon AI — SBIR Phase I Final Technical Report" \
  --metadata author="Jason Phillip" \
  --metadata date="$(date -u +%Y-%m-%d)"

echo "rendered: $OUT_DIR/${BASE}.docx"
