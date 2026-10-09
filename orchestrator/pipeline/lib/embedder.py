"""Embedding generation via Ollama or primary host llama.cpp (4B or 8B)."""

import os
import struct
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import httpx

from .config import (
    OLLAMA_EMBED_URL, EMBED_URL_PRIMARY,
    MODEL_EMBED_DEFAULT, MODEL_EMBED_ENHANCED,
    EMBED_DIMS_DEFAULT, EMBED_DIMS_ENHANCED,
    get_embedding_config,
)

# Qwen3-Embedding family expects an instruction prefix on QUERIES ONLY.
# Documents (passages) get raw text. Without this split, retrieval drops 5-10
# MTEB points — the model treats query and doc embeddings as if they're in
# the same space when they shouldn't be. Apply universally to any Qwen3 model
# (4B and 8B both benefit) since the prefix is purely client-side text.
_QWEN3_QUERY_PREFIX = (
    "Instruct: Given a web search query, retrieve relevant passages "
    "that answer the query.\nQuery: "
)

# Cache the detected config for the session
_config: Optional[dict] = None
_actual_dims: Optional[int] = None


def index_embedding_kwargs() -> dict[str, int]:
    """Return batch and worker settings for index-style embedding."""
    # CORPUS_EMBED_WORKERS / CORPUS_EMBED_BATCH: optional overrides (2026-09-10).
    # Unset = 4 workers x 8 texts. The nightly history-ingest units set
    # workers=1 batch=16 so the 21:26 run stops pushing primary host to its thermal limit.
    # Batch 8, not the library's 64 (2026-10-02): llama-server spreads one request's inputs over
    # all 4 slots and serves tasks first-in first-out, so a `corpus search` query waits behind
    # every queued text. Measured on primary host with a search running during the load:
    # 4x64 -> search fails (30 s timeout); 4x16 -> 45 s; 4x8 -> 25 s; idle 4 s. Index rate is
    # the same at all three (4.5-4.8 texts/s). Fewer workers do not help: 3x64 filled all 4 slots.
    kwargs = {"batch_size": 8}
    for name, key in (("CORPUS_EMBED_WORKERS", "workers"), ("CORPUS_EMBED_BATCH", "batch_size")):
        value = os.environ.get(name, "")
        if value.isdigit() and int(value) > 0:
            kwargs[key] = int(value)
    return kwargs


def _get_config() -> dict:
    global _config
    if _config is None:
        _config = get_embedding_config()
    return _config


def _probe_dims() -> int:
    """Probe the actual embedding dimensions by embedding a test string."""
    global _actual_dims
    if _actual_dims is not None:
        return _actual_dims
    cfg = _get_config()
    vec = _embed_raw("dimension probe", cfg)
    _actual_dims = len(vec)
    # Update config to match reality
    cfg["dims"] = _actual_dims
    return _actual_dims


def embed_text(text: str) -> bytes:
    """Embed a single text string, return as packed float32 bytes for sqlite-vec."""
    cfg = _get_config()
    vec = _embed_raw(text, cfg)
    return _pack_vector(vec)


def embed_texts(texts: list[str], batch_size: int = 64) -> list[bytes]:
    """Embed multiple texts, return as list of packed float32 bytes."""
    cfg = _get_config()
    results = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        vecs = _embed_batch_raw(batch, cfg)
        results.extend(_pack_vector(v) for v in vecs)
    return results


def embed_texts_parallel(
    texts: list[str],
    batch_size: int = 64,
    workers: int = 4,
) -> list[bytes]:
    """Embed multiple texts using concurrent HTTP requests across embedding-service slots.

    Splits ``texts`` into batches of ``batch_size`` and dispatches up to
    ``workers`` batches concurrently via ThreadPoolExecutor. Each concurrent
    HTTP request lands on a separate llama.cpp slot (the embedding service is
    configured with ``--parallel 4`` since 2026-05-04). Order is preserved
    in the returned list.

    **Multi-host load balancing:** if a second embedding host is configured
    via ``EMBED_URL_2`` and reachable alongside ``EMBED_URL_PRIMARY``, batches
    are round-robin'd across the two hosts (real 2× throughput from two
    independent GB10 GPUs). With only primary host up (the default), all batches
    go to primary host. The optional Ollama fallback path
    keeps single-URL behavior. Health-check is cached for the lifetime of
    the process.

    Why this exists: llama.cpp processes a single HTTP request with a batched
    ``input=[t1,t2,...]`` SERIALLY within ONE slot — so the old
    ``embed_texts(batch_size=64)`` pattern bottlenecks on a single slot, and
    additionally on a single host. ``embed_texts_parallel`` fans across both.

    **Vector parity with `embed_texts`:** defaults to ``batch_size=64`` (same
    as ``embed_texts``) so chunking offsets are identical to the legacy code,
    and each chunk lands at the same position-within-batch — preserving the
    same per-position FP-rounding as before. Cross-host vectors are NOT
    bit-identical (cosine ~0.9998 due to per-GPU CUDA kernel non-determinism)
    but are functionally identical for retrieval.
    """
    if not texts:
        return []

    cfg = _get_config()

    # Determine the URL pool for this call.
    # Explicit via_litellm opt-in → single proxy URL (proxy handles LB+cache).
    # Direct llama.cpp path → both spark hosts when healthy.
    # ollama path → single URL.
    if cfg.get("via_litellm"):
        urls = [cfg["url"]]
    elif cfg["provider"] == "llama_cpp":
        from .config import get_spark_embedding_urls
        urls = get_spark_embedding_urls() or [cfg["url"]]
    else:
        urls = [cfg["url"]]

    # Build (start_index, batch_texts, url) tuples. Each batch is statically
    # assigned a URL by round-robin order; the corresponding worker thread
    # makes the HTTP call. We don't shuffle URLs *across* workers because
    # ThreadPoolExecutor.map dispatches in order and each worker pulls the
    # next item — so if we have 2 URLs and 4 workers, the first 4 batches
    # get URLs [0,1,0,1] respectively, perfect interleaving.
    #
    # IMPORTANT — host-balancing fix (2026-05-19): When `texts` would produce
    # fewer batches than len(urls) at the requested batch_size, we shrink the
    # effective batch size so EVERY healthy URL gets at least one batch. This
    # closes a real bug where small files (e.g. a CLI session with 30 chunks)
    # produced 1 batch → always url[0] → 95% of pipeline work landed on primary host
    # while the second host sat at 0% GPU. A 30-chunk call with 2 URLs splits as
    # [15, 15] across both hosts. Vectors are bit-identical to a single-host
    # call modulo cross-host CUDA nondeterminism (~0.9998 cosine; already
    # documented above as functionally identical for retrieval).
    n = len(texts)
    n_urls = len(urls)
    natural_batches = (n + batch_size - 1) // batch_size
    if n_urls > 1 and natural_batches < n_urls and n >= n_urls:
        effective_batch = max(1, (n + n_urls - 1) // n_urls)
    else:
        effective_batch = batch_size

    batches: list[tuple[int, list[str], str]] = []
    for i, start in enumerate(range(0, n, effective_batch)):
        url = urls[i % n_urls]
        batches.append((start, texts[start:start + effective_batch], url))

    results: list[Optional[bytes]] = [None] * len(texts)

    def _process(item: tuple[int, list[str], str]) -> tuple[int, list[bytes]]:
        start, batch, url = item
        # Override URL in a copy of cfg so _embed_batch_raw hits the right host.
        cfg_for_batch = {**cfg, "url": url}
        vecs = _embed_batch_raw(batch, cfg_for_batch)
        return start, [_pack_vector(v) for v in vecs]

    # ThreadPoolExecutor.map preserves order of yielded results matching the
    # input iterable, but we don't rely on that — we use the returned start
    # index to write into the output list directly. If ANY worker raises,
    # the exception propagates here and the caller's retry/fallback handles
    # it (mirrors the single-batch error semantics of embed_texts).
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for start, packed_vecs in pool.map(_process, batches):
            for offset, packed in enumerate(packed_vecs):
                results[start + offset] = packed

    # By construction every position is filled (no gaps), so this assert
    # is a sanity check, not a runtime contract.
    assert all(r is not None for r in results), "embed_texts_parallel: hole in output"
    return results  # type: ignore[return-value]


def embed_query(text: str) -> bytes:
    """Embed a query string. Applies the Qwen3 instruction prefix for Qwen3 models."""
    cfg = _get_config()
    if "Qwen3" in cfg.get("model", ""):
        return embed_text(f"{_QWEN3_QUERY_PREFIX}{text}")
    return embed_text(text)


def get_dims() -> int:
    """Return the actual embedding dimension (probes model on first call)."""
    return _probe_dims()


def get_label() -> str:
    """Return a human-readable label for the active embedding model."""
    return _get_config()["label"]


def _embed_raw(text: str, cfg: dict) -> list[float]:
    """Get raw embedding vector for a single text (document path — no query prefix)."""
    if cfg["provider"] == "llama_cpp":
        return _embed_llama_cpp(text, cfg)
    return _embed_ollama(text, cfg)


def _embed_batch_raw(texts: list[str], cfg: dict) -> list[list[float]]:
    """Get raw embedding vectors for a batch (document path — no query prefix)."""
    if cfg["provider"] == "llama_cpp":
        return _embed_llama_cpp_batch(texts, cfg)
    return _embed_ollama_batch(texts, cfg)


def _embed_ollama(text: str, cfg: dict) -> list[float]:
    """Embed via Ollama /api/embed endpoint."""
    r = httpx.post(
        cfg["url"],
        json={"model": cfg["model"], "input": text},
        timeout=30.0,
    )
    r.raise_for_status()
    data = r.json()
    return data["embeddings"][0]


def _embed_ollama_batch(texts: list[str], cfg: dict) -> list[list[float]]:
    """Embed batch via Ollama /api/embed (supports list input)."""
    r = httpx.post(
        cfg["url"],
        json={"model": cfg["model"], "input": texts},
        timeout=60.0,
    )
    r.raise_for_status()
    data = r.json()
    return data["embeddings"]


def _llama_cpp_headers(cfg: dict) -> dict:
    """Build HTTP headers; adds Authorization when cfg has a real api_key
    (LiteLLM proxy needs it; direct llama-server doesn't enforce auth)."""
    api_key = cfg.get("api_key")
    if api_key and api_key != "not-needed":
        return {"Authorization": f"Bearer {api_key}"}
    return {}


def _embed_llama_cpp(text: str, cfg: dict) -> list[float]:
    """Embed via llama.cpp OpenAI-compatible /v1/embeddings endpoint."""
    r = httpx.post(
        cfg["url"],
        headers=_llama_cpp_headers(cfg),
        json={"model": cfg["model"], "input": text},
        timeout=30.0,
    )
    r.raise_for_status()
    data = r.json()
    try:
        return data["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(
            f"Unexpected response from {cfg['url']}: {str(data)[:300]}"
        ) from e


def _embed_llama_cpp_batch(texts: list[str], cfg: dict) -> list[list[float]]:
    """Embed batch via llama.cpp OpenAI-compatible /v1/embeddings endpoint."""
    r = httpx.post(
        cfg["url"],
        headers=_llama_cpp_headers(cfg),
        json={"model": cfg["model"], "input": texts},
        timeout=120.0,
    )
    r.raise_for_status()
    data = r.json()
    try:
        # Response data items may not be in order; sort by index
        items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]
    except (KeyError, IndexError, TypeError) as e:
        raise ValueError(
            f"Unexpected batch response from {cfg['url']}: {str(data)[:300]}"
        ) from e


def _pack_vector(vec: list[float]) -> bytes:
    """Pack a float list into bytes for sqlite-vec (little-endian float32)."""
    return struct.pack(f"<{len(vec)}f", *vec)
