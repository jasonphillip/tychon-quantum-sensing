# Pipeline & corpus reference

> Extracted verbatim from CLAUDE.md (2026-07-17 progressive-disclosure restructure).
> The governing rule remains in CLAUDE.md Hard rule 5: the infrastructure lives in
> `~/projects/skills/` — TVW invokes scripts from there but does not duplicate them.

## Script invocations (Hard rule 5 detail)

- Code corpus build: `python ~/projects/skills/skills/tychon-code-search/scripts/build_code_corpus.py`
- Code corpus search: `python ~/projects/skills/skills/tychon-code-search/scripts/search_code.py`
- Claim extraction: `python ~/projects/skills/skills/tychon-verify/scripts/extract_claims_from_doc.py`
- Critic loop: `python ~/projects/skills/skills/tychon-verify/scripts/critic_loop.py`
- Doc corpus build: invoke the existing `process-corpus` skill (after pandoc-converting .docx and parsing the signed PDF).

## Corpus locations

- `~/.corpus/tychon-docs/` — prose corpus (built in Stage 1)
- `~/.corpus/tychon-code/` — code corpus (built in Stage 2)
- Both use the existing `~/projects/skills/lib/` pipeline (sqlite-vec FTS5 + Qwen3 embeddings).
