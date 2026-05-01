# Tychon Verification Workbench (TVW) — Claude Project Context

## Mission
Verify factual claims in the Tychon SBIR Phase I final technical report (Proposal `FX255-PCS02-0044` (not selected 2026-05-12, never a contract), Topic `AFX25S-PCS02`, Distribution Statement A) against the project's own ground truth (closure deliverables, technical references, four implementation repos), then carry the same harness forward as Phase II IP.

## Hard rules
1. **Air-gapped only.** Endpoints must resolve to `localhost`, `127.0.0.1`, `spark1`, `spark2`, or `192.168.*`. Any cloud LLM (Anthropic API, OpenAI, Gemini, Perplexity, Scite, etc.) is forbidden under Phase II CUI risk posture.
2. **NIM-first for inference.** Primary critics: `qwen/qwen3-32b-dgx-spark` and `nvidia/nvidia-nemotron-nano-9b-v2-dgx-spark`. Heavyweight reviewer (Stage 5): `meta/llama-3.3-70b-instruct` quantized Q4_K_M via llama.cpp built with `-DCMAKE_CUDA_ARCHITECTURES="121"`. NIM embedding containers fail on ARM64 Blackwell — keep the existing Qwen3-Embedding-4B service on Spark 2 as the embedder.
3. **Symlinked sources are read-only.** `tvw/source/repos/*` and `tvw/source/sbir/*` are symlinks into the user's actual repos. Never `git add` to them via TVW; never modify their contents.
4. **Never read or commit secrets.** `.env`, credentials, API keys are off-limits. Use `$VAR` references in commands.
5. **The infrastructure lives in `~/projects/skills/`.** TVW invokes scripts from there but does not duplicate them. Specifically:
   - Code corpus build: `python ~/projects/skills/skills/tychon-code-search/scripts/build_code_corpus.py`
   - Code corpus search: `python ~/projects/skills/skills/tychon-code-search/scripts/search_code.py`
   - Claim extraction: `python ~/projects/skills/skills/tychon-verify/scripts/extract_claims_from_doc.py`
   - Critic loop: `python ~/projects/skills/skills/tychon-verify/scripts/critic_loop.py`
   - Doc corpus build: invoke the existing `process-corpus` skill (after pandoc-converting .docx and parsing the signed PDF).

## Layout
```
~/projects/tychon-verification-workbench/
├── CLAUDE.md             this file
├── STAGES.md             stop-gate roadmap
├── README.md             project overview
├── .gitignore
└── tvw/
    ├── configs/          endpoints.yaml, model lineup, MCP wiring
    ├── audits/           audit-NNN.md punch lists, verdict CSVs
    ├── services/         systemd unit drafts for NIMs / llama.cpp
    └── source/
        ├── repos/        symlinks → ~/projects/{4 repos}
        └── sbir/         symlink → ~/Desktop/Shared/tychon-nv-sim-repos
```

## Corpus locations
- `~/.corpus/tychon-docs/` — prose corpus (built in Stage 1)
- `~/.corpus/tychon-code/` — code corpus (built in Stage 2)
- Both use the existing `~/projects/skills/lib/` pipeline (sqlite-vec FTS5 + Qwen3 embeddings).

## Pre-flight before any Stage that touches corpora
```
curl -sf http://spark2:8000/health
```
Failure means abort — silent fallback to 768-d Ollama corrupts the sqlite-vec index.

## What to do when invoked
1. Read STAGES.md to find the current stop-gate status.
2. The user will paste a stage-specific prompt that tells you exactly what to build.
3. Stop at the stop-gate; don't bleed into the next stage. The orchestrator (the user's other Claude session in `~/projects/skills/`) decides when to advance.
