> Agent instruction file as used by this repo's coding-agent session (snapshot 2026-10-09; the live file was kept outside version control).

# Session rituals — start, stop-gate, end-of-day

> Moved from CLAUDE.md §What to do when invoked, §Pre-flight, §End-of-day close on 2026-09-04
> (harness-sota restructure). The five-line "Every session" list in CLAUDE.md is the binding
> short form; this file carries the original wording and rationale.

## What to do when invoked
1. Read STAGES.md to find the current stop-gate status.
2. If the work concerns the fix list, also re-read `tvw/source/sbir/tychon-nv-sim-repos/May_1_2026_Document_Fix_List.md` — it is revised between sessions.
3. The user will paste a stage-specific prompt that tells you exactly what to build.
4. Stop at the stop-gate; don't bleed into the next stage. The orchestrator (the user's other Claude session in `~/projects/skills/`) decides when to advance.

## Pre-flight before any Stage that touches corpora
```
curl -sf http://ws2:8000/health
```
Failure means abort — silent fallback to 768-d Ollama corrupts the sqlite-vec index.
Embedder: the Qwen3-Embedding-4B service on ws2 :8000 (Hard rule 2; NIM embedding containers
fail on ARM64 Blackwell).

## End-of-day close
When the user signals end-of-day wrap-up intent ("wrapping up", "done for the day", "closing out",
"EOD", etc.), proactively ask whether to run `tvw/scripts/eod_close.sh`. The script sweeps all 5
Tychon repos (TVW + 4 implementation), auto-pushes internal mirrors (NAS, ws2; ws1 removed
from `eod_close.sh` INTERNAL_REMOTES_REGEX 2026-07-10 — decommissioned 2026-07-05), runs a secrets
sweep, and gates the GitHub push behind a single yes/N approval. Don't run without explicit yes;
don't re-ask in the same session if declined. Full behavioral rule: memory entry
`feedback_eod_close_trigger.md`.
