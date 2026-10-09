"""Corpus pipeline configuration — paths, models, constants."""

import os
from pathlib import Path


class EmbeddingUnavailable(RuntimeError):
    """No compatible embedding endpoint is available."""


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean env gate; empty/unset means the default."""
    v = os.environ.get(name, "").strip()
    if v == "":
        return default
    return v not in ("0", "false", "False", "no")

# Core paths
CORPUS_ROOT = Path(os.environ.get("CORPUS_ROOT", Path.home() / ".corpus"))
PIPELINE_ROOT = Path(os.environ.get("PIPELINE_ROOT", Path(__file__).resolve().parents[1]))
STATUS_FILE = Path(os.environ.get("CORPUS_STATUS_FILE", CORPUS_ROOT / "corpus-index.md"))

# Ollama config
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_GENERATE_URL = f"{OLLAMA_HOST}/api/generate"
OLLAMA_EMBED_URL = f"{OLLAMA_HOST}/api/embed"

# Embedding services (Qwen3-Embedding-4B via llama.cpp).
# The primary embedding host defaults to local llama-server on :8000.
# A second host can be added for round-robin bulk-indexing throughput by
# setting EMBED_URL_2 in the environment (e.g. the RMA replacement node when
# it arrives). Left empty it means primary host-only, which is the correct default.
EMBED_URL_PRIMARY = os.environ.get("EMBED_URL_PRIMARY", "http://localhost:8000/v1/embeddings")
EMBED_URL_2 = os.environ.get("EMBED_URL_2", "").strip()

# Optional LiteLLM proxy. Only probe it when an explicit URL is configured.
# LITELLM_DISABLE=1 overrides that opt-in and uses the direct primary host endpoint.
LITELLM_EMBED_URL = os.environ.get("LITELLM_EMBED_URL", "").strip()
LITELLM_API_KEY = os.environ.get("LITELLM_API_KEY", "")
LITELLM_DISABLE = _env_bool("LITELLM_DISABLE", False)

# OpenAI-compatible chat backend (optional). When LLM_CHAT_URL is set, ALL
# lib.ollama_llm text generation (scoring, query expansion, LLM-rerank
# fallback, triage, summaries) goes to this /v1/chat/completions endpoint
# instead of Ollama — the Composer world points it at DSV4-Flash on
# 127.0.0.1:8002. LLM_CHAT_MODEL replaces the per-call Ollama model name
# (those names don't exist on an OpenAI-compatible server). Unset (the
# primary host default) = Ollama, unchanged.
LLM_CHAT_URL = os.environ.get("LLM_CHAT_URL", "").strip()
LLM_CHAT_MODEL = os.environ.get("LLM_CHAT_MODEL", "").strip()

# Model assignments
MODEL_SCORING = "qwen3:14b"       # Source quality scoring, summarization
MODEL_TRIAGE = "nemotron-mini"     # Fast chunk metadata triage
MODEL_EMBED_DEFAULT = "nomic-embed-text-v2-moe"  # Default Ollama embedding
MODEL_EMBED_ENHANCED = "Qwen3-Embedding-4B"       # primary host llama.cpp 4B embedding

# Embedding dimensions (defaults — auto-detected at runtime by embedder.py)
EMBED_DIMS_DEFAULT = 768     # nomic-embed-text-v2-moe
EMBED_DIMS_ENHANCED = 2560   # Qwen3-Embedding-4B (actual output dims)

# Chunking defaults
CHUNK_SIZE = 1500           # characters (Chonkie semantic chunker)
CHUNK_OVERLAP = 200         # characters overlap (13% of CHUNK_SIZE)
CHUNK_SIZE_ENHANCED = 6000  # larger chunks when using 8192-token embedding model
CHUNK_OVERLAP_ENHANCED = 600  # 10% of CHUNK_SIZE_ENHANCED

# Search defaults
SEARCH_VECTOR_WEIGHT = 0.7
SEARCH_BM25_WEIGHT = 0.3
SEARCH_TOP_K = 30
SEARCH_PER_SOURCE_LIMIT = 3
SEARCH_RECENCY_WEIGHT = 0.15
# 2026-10-02 llm-history A/B: with/without rerank MRR 0.543/0.526 whole-chunk, 0.362/0.360 late-content, at 2-3 s/query (dgx-spark scripts/rerank-ab-2026-10-02/REPORT.md).
SEARCH_RERANK = _env_bool("SEARCH_RERANK", False)
SEARCH_RERANK_MODEL = MODEL_SCORING  # qwen3:14b (fallback path)
# Local cross-encoder reranker (Qwen3-Reranker-0.6B via llama.cpp --rerank).
# rerank_chunks() tries this first and falls back to the LLM prompt path; if
# BOTH fail it raises RerankUnavailable so callers report hybrid order honestly.
RERANK_URL = os.environ.get("RERANK_URL", "http://127.0.0.1:8003/v1/rerank")
# Window and server batch (2026-10-02). reranker.service runs with -b/-ub 4096. A query+document
# pair over the batch aborts llama-server, so the client cuts by bytes: a tokenizer never emits
# more tokens than UTF-8 bytes. The server's fixed prompt measured 72 tokens; the allowance below
# leaves room for it. Window A/B: dgx-spark scripts/rerank-ab-2026-10-02/REPORT.md.
RERANK_TEMPLATE_TOKENS = 128
RERANK_QUERY_MAX_BYTES = 1024


def rerank_limits() -> tuple[int, int]:
    """Return (document window in characters, server batch in tokens).

    Read at call time, so CORPUS_RERANK_DOC_CHARS and CORPUS_RERANK_BATCH_TOKENS can match a
    server that runs a different batch."""
    def positive(name: str, default: int) -> int:
        value = os.environ.get(name, "")
        return int(value) if value.isdigit() and int(value) > 0 else default
    return positive("CORPUS_RERANK_DOC_CHARS", 4000), positive("CORPUS_RERANK_BATCH_TOKENS", 4096)


SEARCH_QUERY_EXPANSION = _env_bool("SEARCH_QUERY_EXPANSION", True)
SEARCH_SMART_MIN_CHUNKS = 500  # auto-disable rerank + expansion below this

# Figure-caption sidecar chunks (vault-world PDF ingest emits them with this
# prefix). caption_mode in corpus_db filters on it; SEARCH_EXCLUDE_CAPTIONS=1
# makes text-first searches drop them by default (CLI flags still override).
SEARCH_CAPTION_PREFIX = os.environ.get("SEARCH_CAPTION_PREFIX", "[Figure caption")
SEARCH_EXCLUDE_CAPTIONS = _env_bool("SEARCH_EXCLUDE_CAPTIONS", False)

# Context mode budget
CONTEXT_TOKEN_BUDGET = 100_000  # ~100K tokens for CONTEXT.md

def corpus_path(topic: str) -> Path:
    """Get the corpus directory for a topic."""
    return CORPUS_ROOT / _sanitize_topic(topic)


def _sanitize_topic(topic: str) -> str:
    """Sanitize topic name for use as directory name."""
    return topic.lower().strip().replace(" ", "-").replace("/", "-")


def detect_primary_embedding() -> bool:
    """Check if primary host's Qwen3-Embedding-4B service is available."""
    return _detect_spark_embedding(EMBED_URL_PRIMARY)


def _detect_spark_embedding(url: str) -> bool:
    """Check if an OpenAI-compatible embedding endpoint is up.

    Tries /health (llama.cpp's public endpoint) first, then /health/readiness
    (LiteLLM's public endpoint — LiteLLM's /health requires auth and returns
    401 without it). 2-second timeout per attempt.
    """
    import httpx
    base = url.rsplit('/v1', 1)[0]
    for path in ("/health", "/health/readiness"):
        try:
            r = httpx.get(f"{base}{path}", timeout=2.0)
            if r.status_code == 200:
                return True
        except Exception:
            continue
    return False


# Module-global cache of healthy spark embedding URLs.
# Populated lazily on first call to get_spark_embedding_urls() and reused
# for the lifetime of the Python process. Restart the process to refresh.
_HEALTHY_SPARK_URLS: list[str] | None = None


def get_spark_embedding_urls() -> list[str]:
    """Return list of healthy llama.cpp embedding endpoints (primary host first, then optional EMBED_URL_2).

    Result is cached for the lifetime of the process. Used by
    ``embed_texts_parallel`` to round-robin batches across multiple hosts —
    real 2× throughput when both are healthy. If only one is up, that one
    is used for all batches.
    """
    global _HEALTHY_SPARK_URLS
    if _HEALTHY_SPARK_URLS is None:
        candidates = [EMBED_URL_PRIMARY, EMBED_URL_2]
        _HEALTHY_SPARK_URLS = [u for u in candidates if u and _detect_spark_embedding(u)]
    return list(_HEALTHY_SPARK_URLS)


def get_embedding_config() -> dict:
    """Return active embedding configuration.

    Provider precedence:
      1. Optional LiteLLM proxy at an explicitly set LITELLM_EMBED_URL.
         Skipped if LITELLM_DISABLE is truthy in env.
      2. Direct llama.cpp on primary host (the default endpoint).
      3. Local Ollama only with EMBED_ALLOW_OLLAMA_FALLBACK=1 for a new corpus.
    """
    if not LITELLM_DISABLE and LITELLM_EMBED_URL and _detect_spark_embedding(LITELLM_EMBED_URL):
        return {
            "provider": "llama_cpp",       # LiteLLM is OpenAI-compatible (same code path)
            "via_litellm": True,            # signals embed_texts_parallel to skip client-side LB
            "url": LITELLM_EMBED_URL,
            "api_key": LITELLM_API_KEY,
            "model": "qwen3-embedding-4b",  # the model_name in litellm/config.yaml
            "dims": EMBED_DIMS_ENHANCED,
            "chunk_size": CHUNK_SIZE_ENHANCED,
            "chunk_overlap": CHUNK_OVERLAP_ENHANCED,
            "label": "Qwen3-Embedding-4B (via LiteLLM proxy)",
        }
    if detect_primary_embedding():
        return {
            "provider": "llama_cpp",
            "url": EMBED_URL_PRIMARY,
            "model": MODEL_EMBED_ENHANCED,
            "dims": EMBED_DIMS_ENHANCED,
            "chunk_size": CHUNK_SIZE_ENHANCED,
            "chunk_overlap": CHUNK_OVERLAP_ENHANCED,
            "label": "Qwen3-Embedding-4B (primary host)",
        }
    if os.environ.get("EMBED_ALLOW_OLLAMA_FALLBACK") != "1":
        raise EmbeddingUnavailable(
            f"Embedding service unavailable at {EMBED_URL_PRIMARY}. "
            "Existing indexes are 2560-d; the 768-d Ollama fallback cannot query them. "
            "Run: systemctl --user status embedding-service; "
            "systemctl --user restart embedding-service. "
            "To build a NEW corpus with Ollama, set EMBED_ALLOW_OLLAMA_FALLBACK=1 "
            "(optionally set OLLAMA_EMBED_MODEL)."
        )
    model = os.environ.get("OLLAMA_EMBED_MODEL", MODEL_EMBED_DEFAULT)
    return {
        "provider": "ollama",
        "url": OLLAMA_EMBED_URL,
        "model": model,
        "dims": EMBED_DIMS_DEFAULT,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "label": f"{model} (local)",
    }
