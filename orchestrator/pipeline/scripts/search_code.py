#!/usr/bin/env python3
"""Search the tychon-code corpus.

Two modes:
  --symbol NAME   exact-match against the symbols table; expands to callers
                  via the xrefs table; pulls the surrounding code chunk.
  --query  TEXT   hybrid BM25 + sqlite-vec retrieval over code chunks.

Output is JSON to stdout so the critic loop and other consumers can parse it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.config import corpus_path
from lib.corpus_db import connect, search_hybrid
from lib.embedder import embed_query
from lib.symbol_index import find_callers, find_symbol

_TOPIC = "tychon-code"


def _read_chunk_around(source_path: str, line: int,
                       context_lines: int = 25) -> str:
    """Read +/- context_lines around a line from the on-disk source.

    source_path is the corpus-relative path (e.g. "polarfire-hybrid-control/src/pid.cpp")
    so the prefix is the repo name and the rest is repo-relative.
    Returns "" if the file can't be read (e.g. moved on disk since indexing).
    """
    parts = Path(source_path).parts
    if len(parts) < 2:
        return ""
    repo_root = Path(os.environ.get("TYCHON_REPOS_ROOT", Path.home() / "projects")) / parts[0]
    on_disk = repo_root / Path(*parts[1:])
    try:
        all_lines = on_disk.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    start = max(0, line - context_lines - 1)
    end = min(len(all_lines), line + context_lines)
    numbered = [f"{i+1:>5}: {ln}" for i, ln in enumerate(all_lines[start:end], start=start)]
    return "\n".join(numbered)


def cmd_symbol(args) -> int:
    conn = connect(_TOPIC)
    try:
        defs = find_symbol(conn, args.symbol, repo=args.repo)
        callers = find_callers(conn, args.symbol, repo=args.repo)
    finally:
        conn.close()

    if not defs and not callers:
        print(json.dumps({"symbol": args.symbol, "definitions": [],
                          "callers": [], "context": []}, indent=2))
        return 1

    out = {
        "symbol": args.symbol,
        "definitions": defs,
        "callers": callers,
        "context": [],
    }
    if not args.no_context:
        for d in defs:
            out["context"].append({
                "source_path": d["source_path"],
                "line": d["line"],
                "snippet": _read_chunk_around(d["source_path"], d["line"]),
            })
    print(json.dumps(out, indent=2, default=str))
    return 0


def _scope_query_to_repo(conn: sqlite3.Connection, repo: str) -> None:
    """Shadow retrieval tables with a temporary repo subset before ranking.

    Reuse the shared hybrid search unchanged. The main index is untouched;
    SQLite drops these temporary tables when the command closes its connection.
    """
    prefix = f"{repo}/"
    conn.execute(
        "CREATE TEMP TABLE chunks AS SELECT * FROM main.chunks "
        "WHERE substr(source_path, 1, ?) = ?", (len(prefix), prefix),
    )
    # Preserve the index's tokenizer and vector dimensions.
    for table in ("chunks_fts", "chunks_vec"):
        schema = conn.execute(
            "SELECT sql FROM main.sqlite_master WHERE name = ?", (table,),
        ).fetchone()[0]
        module = re.split(r"\bUSING\b", schema, maxsplit=1, flags=re.IGNORECASE)[1]
        conn.execute(f"CREATE VIRTUAL TABLE temp.{table} USING {module}")
    conn.execute(
        "INSERT INTO temp.chunks_fts SELECT f.* FROM main.chunks_fts f "
        "JOIN temp.chunks c ON c.id = f.chunk_id"
    )
    conn.execute(
        "INSERT INTO temp.chunks_vec (id, embedding) "
        "SELECT v.id, v.embedding FROM main.chunks_vec v "
        "JOIN temp.chunks c ON c.id = v.id"
    )


def cmd_query(args) -> int:
    db_path = corpus_path(_TOPIC) / "processed" / "chunks.db"
    if not db_path.exists():
        print(f"ERROR: corpus DB not found at {db_path}. "
              f"Run build_code_corpus.py first.", file=sys.stderr)
        return 2

    conn = connect(_TOPIC)
    try:
        if args.repo:
            _scope_query_to_repo(conn, args.repo)
        emb = embed_query(args.query)
        results = search_hybrid(conn, args.query, emb, top_k=args.top_k)
    finally:
        conn.close()

    print(json.dumps({"query": args.query, "results": results},
                     indent=2, default=str))
    return 0 if results else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--symbol", help="Exact-match symbol lookup")
    grp.add_argument("--query", help="Natural-language hybrid retrieval")
    p.add_argument("--repo", help="Limit to one repo")
    p.add_argument("--top-k", type=int, default=10, help="Top-K for query mode")
    p.add_argument("--no-context", action="store_true",
                   help="Skip on-disk source snippets in symbol mode")
    args = p.parse_args()

    if args.symbol:
        return cmd_symbol(args)
    return cmd_query(args)


if __name__ == "__main__":
    sys.exit(main())
