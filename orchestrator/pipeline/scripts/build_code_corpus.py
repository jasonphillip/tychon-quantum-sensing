#!/usr/bin/env python3
"""Build the tychon-code corpus from the four Tychon repos.

For each repo:
1. Enumerate first-party tracked files via `git ls-files`.
2. Apply path/extension exclude list (vendor/, build/, *.o, *.npy, ...).
3. Chunk source files via lib.code_chunker (tree-sitter, falls back recursive).
4. Embed via lib.embedder (local Qwen3 → Ollama fallback honors dim guard).
5. Insert via lib.corpus_db.insert_chunk into ~/.corpus/tychon-code/.
6. Run ctags over each repo's source files; ingest into symbols + xrefs tables.

The shared-data repo gets manifest-only indexing (path/size/sha256) — no chunking.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

# Make lib/ importable when invoked as a script from the skill's scripts/ dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from lib.code_chunker import chunk_code_file
from lib.config import (
    EMBED_URL_PRIMARY, corpus_path, detect_primary_embedding, get_embedding_config,
)
from lib.corpus_db import (
    connect, delete_by_source, get_source_hash, get_stats, init_schema,
    insert_chunk, upsert_source,
)
from lib.embedder import embed_texts, get_dims, get_label
from lib.symbol_index import (
    get_code_stats, have_ctags, ingest_tags, init_code_tables, run_ctags,
)

# The four Tychon repos. Override via TYCHON_REPOS_ROOT for testing.
_REPOS_ROOT = Path(os.environ.get("TYCHON_REPOS_ROOT", Path.home() / "projects"))
_REPO_NAMES = ["polarfire-hybrid-control", "odmr-edge-ml", "nv-sensor-sim",
               "tychon-shared-data"]
# tychon-shared-data is data — manifest-only, no chunking.
_DATA_ONLY = {"tychon-shared-data"}

# Source extensions we chunk. Anything else gets skipped.
_SOURCE_EXTS = {
    ".py", ".pyi",
    ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx",
    ".c", ".h",
    ".v", ".sv", ".svh",
}

# Exclude these path components anywhere in the relative path.
_EXCLUDE_DIRS = {
    "vendor", "third_party", "extern", "build", "_deps",
    "Release", "Debug", ".venv", "venv", "node_modules", "__pycache__",
    "dist", "site-packages", ".tox", ".pytest_cache",
}

# Exclude files matching these extensions (binary or generated).
_EXCLUDE_EXTS = {
    ".o", ".so", ".a", ".dylib", ".dll",
    ".bin", ".npy", ".npz", ".h5", ".pt", ".pth", ".ckpt", ".safetensors",
    ".pyc", ".pyo",
    ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".tar", ".gz",
}

# Topic name and per-source path encoding.
_TOPIC = "tychon-code"

# Embed batch size (Qwen3-4B handles 32-64 OK at 6000 char chunks).
_BATCH = 32


def _git_ls_files(repo: Path) -> list[Path]:
    """Tracked files from the repo's git index. Empty list on failure."""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z"],
            capture_output=True, check=True, timeout=60,
        )
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"  WARN: git ls-files failed for {repo}: {e}", file=sys.stderr)
        return []
    rels = out.stdout.decode("utf-8", errors="replace").split("\0")
    return [repo / r for r in rels if r]


def _is_first_party(rel: Path) -> bool:
    """Apply path-component and extension excludes."""
    parts_lower = {p.lower() for p in rel.parts}
    if parts_lower & _EXCLUDE_DIRS:
        return False
    if rel.suffix.lower() in _EXCLUDE_EXTS:
        return False
    return True


def _filter_sources(repo: Path, files: list[Path]) -> list[Path]:
    """Keep first-party source files we know how to chunk."""
    kept: list[Path] = []
    for f in files:
        if not f.is_file():
            continue
        rel = f.relative_to(repo)
        if not _is_first_party(rel):
            continue
        if f.suffix.lower() in _SOURCE_EXTS:
            kept.append(f)
    return kept


def _file_hash(path: Path) -> str:
    """SHA-256 of file contents for change detection."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _shared_data_manifest(repo: Path) -> Path:
    """Index a data-only repo by writing one manifest file under raw/.

    The manifest gets ingested as one chunk so 'where is the dataset stored?'
    questions land somewhere in the corpus. No binaries get embedded.
    """
    raw_dir = corpus_path(_TOPIC) / "raw" / repo.name
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_dir / "MANIFEST.md"

    files = _git_ls_files(repo)
    rows = []
    for f in files:
        if not f.is_file():
            continue
        rel = f.relative_to(repo)
        try:
            size = f.stat().st_size
        except OSError:
            size = -1
        rows.append((str(rel), size))

    rows.sort()
    body = [f"# {repo.name} — file manifest", "",
            f"Total tracked files: {len(rows)}", ""]
    body.append("| Path | Size (bytes) |")
    body.append("|------|--------------|")
    for rel, size in rows:
        body.append(f"| {rel} | {size} |")
    manifest_path.write_text("\n".join(body) + "\n")
    return manifest_path


def _embed_with_fallback(texts: list[str]) -> tuple[list[bytes | None], int]:
    """Batch embed with retry; per-chunk fallback on persistent failure."""
    statuses_to_retry = {408, 429, 500, 502, 503, 504}
    for attempt in range(3):
        try:
            return list(embed_texts(texts, batch_size=_BATCH)), 0
        except httpx.HTTPStatusError as e:
            if e.response.status_code in statuses_to_retry and attempt < 2:
                time.sleep([1, 4][attempt])
                continue
            break
        except httpx.RequestError:
            if attempt < 2:
                time.sleep([1, 4][attempt])
                continue
            break

    out: list[bytes | None] = []
    dropped = 0
    for t in texts:
        try:
            out.append(embed_texts([t])[0])
        except (httpx.HTTPStatusError, httpx.RequestError):
            out.append(None)
            dropped += 1
    return out, dropped


def _process_repo(repo: Path, conn, force: bool) -> dict:
    """Chunk + embed + insert + ctags for one source repo. Returns counters."""
    counts = {"files_seen": 0, "files_chunked": 0, "files_skipped": 0,
              "files_failed": 0, "chunks": 0, "dupes": 0, "dropped": 0,
              "defs": 0, "refs": 0}

    all_files = _git_ls_files(repo)
    counts["files_seen"] = len(all_files)
    sources = _filter_sources(repo, all_files)
    print(f"  {repo.name}: {len(all_files)} tracked → {len(sources)} first-party source")

    embed_cfg = get_embedding_config()
    chunk_size = embed_cfg["chunk_size"]
    overlap = embed_cfg.get("chunk_overlap", 0)

    for f in sources:
        rel_path = f"{repo.name}/{f.relative_to(repo)}"
        try:
            src_hash = _file_hash(f)
            if not force and get_source_hash(conn, rel_path) == src_hash:
                counts["files_skipped"] += 1
                continue

            chunks = chunk_code_file(f, chunk_size=chunk_size, overlap=overlap)
            if not chunks:
                continue

            delete_by_source(conn, rel_path)

            texts = [c["content"] for c in chunks]
            embeddings, dropped = _embed_with_fallback(texts)
            counts["dropped"] += dropped

            inserted = 0
            dupes = 0
            for c, emb in zip(chunks, embeddings):
                if emb is None:
                    continue
                meta = c.get("metadata", {})
                meta["repo"] = repo.name
                result = insert_chunk(conn, rel_path, c["index"],
                                      c["content"], emb, meta)
                if result:
                    inserted += 1
                else:
                    dupes += 1

            upsert_source(conn, rel_path, src_hash, inserted)
            conn.commit()
            counts["files_chunked"] += 1
            counts["chunks"] += inserted
            counts["dupes"] += dupes
        except Exception as e:
            conn.rollback()
            counts["files_failed"] += 1
            print(f"    FAIL {rel_path}: {e}", file=sys.stderr)

    # ctags pass — once per repo, over the same first-party file set.
    if have_ctags() and sources:
        try:
            tags = run_ctags(repo, sources)
            defs, refs = ingest_tags(conn, repo.name, tags)
            counts["defs"] = defs
            counts["refs"] = refs
            print(f"    ctags: {defs} definitions, {refs} references")
        except Exception as e:
            print(f"    ctags FAILED: {e}", file=sys.stderr)
    elif not have_ctags():
        print(f"    NOTE: universal-ctags not on PATH — symbol/xref tables empty")

    return counts


def _process_data_repo(repo: Path, conn, force: bool) -> dict:
    """Manifest-only indexing for tychon-shared-data."""
    manifest = _shared_data_manifest(repo)
    rel_path = f"{repo.name}/{manifest.relative_to(corpus_path(_TOPIC) / 'raw' / repo.name)}"

    counts = {"files_seen": 0, "files_chunked": 0, "files_skipped": 0,
              "files_failed": 0, "chunks": 0, "dupes": 0, "dropped": 0,
              "defs": 0, "refs": 0}

    src_hash = _file_hash(manifest)
    if not force and get_source_hash(conn, rel_path) == src_hash:
        counts["files_skipped"] = 1
        return counts

    text = manifest.read_text(encoding="utf-8", errors="replace")
    embeddings = embed_texts([text])
    if embeddings:
        delete_by_source(conn, rel_path)
        ok = insert_chunk(conn, rel_path, 0, text, embeddings[0],
                          {"repo": repo.name, "kind": "manifest", "language": "markdown"})
        if ok:
            counts["chunks"] = 1
        upsert_source(conn, rel_path, src_hash, counts["chunks"])
        conn.commit()
    counts["files_chunked"] = 1
    return counts


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    sys.stderr.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repos-root", type=Path, default=_REPOS_ROOT,
                        help="Parent dir containing the 4 repos (default: ~/projects)")
    parser.add_argument("--repo", action="append", default=None,
                        help="Limit to one repo (can repeat); default: all 4")
    parser.add_argument("--force", action="store_true",
                        help="Re-process every file even if its hash is unchanged")
    args = parser.parse_args()

    if not detect_primary_embedding():
        print(f"FATAL: primary embedder at {EMBED_URL_PRIMARY} is degraded.",
              file=sys.stderr)
        print("Refusing to build a code corpus that would silently fall back to",
              file=sys.stderr)
        print("768-d Ollama and corrupt the sqlite-vec index. Fix the primary embedder first.",
              file=sys.stderr)
        return 2

    repo_names = args.repo or _REPO_NAMES
    repos: list[Path] = []
    for name in repo_names:
        p = args.repos_root / name
        if not p.is_dir():
            print(f"FATAL: missing repo {p}", file=sys.stderr)
            return 2
        repos.append(p)

    print(f"Embedding: {get_label()}")
    print(f"Dimensions: {get_dims()}")
    print(f"Topic: {_TOPIC}")
    print(f"Repos: {', '.join(r.name for r in repos)}\n")

    conn = connect(_TOPIC)
    init_schema(conn, get_dims())
    init_code_tables(conn)

    started = time.time()
    totals = {"files_seen": 0, "files_chunked": 0, "files_skipped": 0,
              "files_failed": 0, "chunks": 0, "dupes": 0, "dropped": 0,
              "defs": 0, "refs": 0}
    for repo in repos:
        print(f"--- {repo.name} ---")
        if repo.name in _DATA_ONLY:
            counts = _process_data_repo(repo, conn, args.force)
        else:
            counts = _process_repo(repo, conn, args.force)
        for k, v in counts.items():
            totals[k] = totals.get(k, 0) + v

    db_path = corpus_path(_TOPIC) / "processed" / "chunks.db"
    stats = get_stats(conn)
    code_stats = get_code_stats(conn)
    conn.close()

    elapsed = time.time() - started
    print(f"\n{'='*60}")
    print(f"tychon-code build complete — {elapsed:.1f}s")
    print(f"  Source files seen:    {totals['files_seen']}")
    print(f"  Source files chunked: {totals['files_chunked']}")
    print(f"  Files skipped (unchanged): {totals['files_skipped']}")
    print(f"  Files failed:        {totals['files_failed']}")
    print(f"  Chunks total in DB:  {stats['total_chunks']}")
    print(f"  Symbols total in DB: {code_stats['total_symbols']}")
    print(f"  Xrefs total in DB:   {code_stats['total_xrefs']}")
    print(f"  Per-repo symbols:    {code_stats['by_repo']}")
    print(f"  DB:                  {db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
