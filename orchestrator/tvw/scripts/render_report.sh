#!/usr/bin/env bash
set -euo pipefail
# Default SRC = the authoritative report .md (v3.4 as of 2026-05-03; v3.1
# and earlier are archived under final_report/archive/).
SRC="${1:-$HOME/Desktop/Shared/tychon/nv-sim-repos/01_deliverables/final_report/Tychon_Phase_I_Final_Report_v3.4_2026-05-03.md}"
OUT_DIR="${2:-$HOME/Desktop/Shared/tychon/nv-sim-repos/01_deliverables/final_report}"
# Style reference: the current v3.4 .docx (the original 2026-04-30 template
# now lives only under final_report/archive/).
REFERENCE="${3:-$OUT_DIR/Tychon_Phase_I_Final_Report_v3.4_2026-05-03.docx}"
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
