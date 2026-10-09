# Claim verification pipeline

These scripts run from `orchestrator/pipeline/scripts/`. They use the bundled `lib/` modules.

- `build_code_corpus.py` reads tracked files from four source repositories, chunks and embeds first-party code, and writes `${CORPUS_ROOT:-~/.corpus}/tychon-code/processed/chunks.db`. The data-only repository contributes a manifest.
- `search_code.py --query TEXT` searches the code index and prints JSON. `--symbol NAME` reads definitions, callers, and optional source context.
- `extract_claims_from_doc.py report.md` reads Markdown and prints claim JSONL to stdout. Redirect it to a file for the next step.
- `critic_loop.py claims.jsonl verdicts.csv` retrieves prose and code evidence, calls each configured critic, and writes verdicts and agreement to CSV.

`orchestrator/STAGES.md` records the code index in Stage 2. Stage 3 ran claim extraction and the critic ensemble. Stage 4 and later re-audits reused the claim and verdict outputs. Stage 1 prepared the prose index separately.

Critics run only on local endpoints. The existing `orchestrator/tvw/configs/endpoints.yaml` selects Ollama models on localhost. The loader rejects non-local hosts. Local llama.cpp or NIM endpoints can use that same config format.

Set `CORPUS_ROOT` for corpus storage and `TYCHON_REPOS_ROOT` for the parent directory of source repositories. The defaults are `~/.corpus` and `~/projects`. `search_code.py` uses the same repository root for source snippets. Set `EMBED_URL_PRIMARY` to an OpenAI-compatible embedding endpoint; its default is `http://localhost:8000/v1/embeddings`. Optional `EMBED_URL_2` and `LITELLM_EMBED_URL` select additional local embedding services. Set `LITELLM_API_KEY` in the environment only when a local proxy requires it; no key value ships here. `CORPUS_STATUS_FILE` defaults inside `CORPUS_ROOT`.

The critic config path defaults to `../tvw/configs/endpoints.yaml` after installation in the monorepo. When running scripts directly from the overlay, pass `--config` with the monorepo config path. Python dependencies include `httpx`, `PyYAML`, and `sqlite-vec`; `tree-sitter-language-pack` and universal-ctags are optional.
