#!/usr/bin/env python3
"""Critic-loop: per-claim, retrieve from both corpora and ask N local LLMs.

Reads a JSONL file of claims (from extract_claims_from_doc.py), retrieves
relevant chunks from `tychon-docs` and `tychon-code` via the corpus pipeline,
sends each claim + evidence to every configured critic endpoint, and writes
a CSV verdict log.

All endpoints must be local + OpenAI-compatible. The loader refuses any URL
whose host is not localhost or 127.0.0.1. To add a model add an entry to endpoints.yaml.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import yaml

from lib.corpus_db import connect, search_hybrid
from lib.embedder import embed_query

_DEFAULT_CONFIG = (Path(__file__).resolve().parents[2] / "tvw" / "configs" / "endpoints.yaml")

# Hosts allowed for critic endpoints. Anything else is a hard reject.
_ALLOWED_HOST_RE = re.compile(
    r"^(localhost|127\.0\.0\.1)(:\d+)?$"
)


_VERDICT_PROMPT = """You are auditing a technical claim from a technical report against retrieved evidence from the project's own documents and source code.

Claim:
  "{claim}"

Retrieved evidence (top {n_doc} prose chunks + top {n_code} code chunks):

{evidence}

Decide whether the evidence supports the claim. Reply with EXACTLY one line of strict JSON, no prose before or after:
  {{"verdict": "SUPPORTED" | "WEAK" | "UNSUPPORTED" | "CONTRADICTED",
    "evidence_chunks": [<integer indices of the chunks you actually relied on, may be empty>],
    "rationale": "<one sentence, max 25 words>"}}

Verdict definitions:
  SUPPORTED: at least one chunk explicitly supports the claim's specific assertion.
  WEAK: chunks are topically related but do not directly support the specific assertion.
  UNSUPPORTED: no relevant evidence retrieved; claim may be hallucinated or cite a missing source.
  CONTRADICTED: evidence directly contradicts the claim.

Output only the JSON line.""".strip()


def _validate_endpoint(name: str, base_url: str) -> None:
    host = httpx.URL(base_url).host
    if not _ALLOWED_HOST_RE.match(host):
        raise ValueError(
            f"endpoint '{name}' base_url={base_url} is not local; "
            f"refusing to break air-gap discipline. Add an explicit host "
            f"override to _ALLOWED_HOST_RE only after explicit local review."
        )


def load_critics(config_path: Path) -> list[dict]:
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Critic config not found at {config_path}. "
            f"See orchestrator/tvw/configs/endpoints.yaml."
        )
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    critics = cfg.get("critics") or []
    if not critics:
        raise ValueError(f"{config_path} has no 'critics' entries")
    for c in critics:
        for k in ("name", "base_url", "model"):
            if k not in c:
                raise ValueError(f"critic entry missing '{k}': {c}")
        _validate_endpoint(c["name"], c["base_url"])
        c.setdefault("max_tokens", 1024)
        c.setdefault("timeout_s", 60.0)
        if isinstance(c["max_tokens"], bool) or not isinstance(c["max_tokens"], int):
            raise ValueError(f"critic '{c['name']}' max_tokens must be an int")
        if isinstance(c["timeout_s"], bool) or not isinstance(c["timeout_s"], (int, float)):
            raise ValueError(f"critic '{c['name']}' timeout_s must be a float")
        c["timeout_s"] = float(c["timeout_s"])
    return critics


def filter_excluded(chunks: list[dict],
                    exclude_substrings: list[str]) -> tuple[list[dict], int]:
    """Drop chunks whose source path contains any excluded substring."""
    kept = [chunk for chunk in chunks
            if not any(substring in chunk.get("source_path", "")
                       for substring in exclude_substrings)]
    return kept, len(chunks) - len(kept)


def retrieve_evidence(query: str, top_k_doc: int = 5,
                      top_k_code: int = 5,
                      exclude_substrings: list[str] | None = None,
                      ) -> tuple[list[dict], int]:
    """Pull, filter, and select top chunks from both corpora."""
    emb = embed_query(query)
    out: list[dict] = []
    excluded_n = 0
    exclude_substrings = exclude_substrings or []

    for topic, top_k in (("tychon-docs", top_k_doc), ("tychon-code", top_k_code)):
        try:
            conn = connect(topic)
        except Exception:
            continue
        try:
            results = search_hybrid(conn, query, emb,
                                    top_k=top_k * 3 if exclude_substrings else top_k)
        except Exception as e:
            print(f"  WARN: search failed on {topic}: {e}", file=sys.stderr)
            results = []
        finally:
            conn.close()
        results, n = filter_excluded(results, exclude_substrings)
        excluded_n += n
        for r in results[:top_k]:
            out.append({
                "topic": topic,
                "score": r.get("score", 0.0),
                "source_path": r.get("source_path", ""),
                "content": r.get("content", "")[:1500],
            })
    return out, excluded_n


def _format_evidence(chunks: list[dict]) -> str:
    lines = []
    for i, c in enumerate(chunks):
        lines.append(f"[{i}] ({c['topic']}) {c['source_path']}")
        lines.append(c["content"])
        lines.append("")
    return "\n".join(lines)


def call_critic(critic: dict, prompt: str, timeout: float = 60.0) -> dict:
    """POST to an OpenAI-compatible /chat/completions endpoint, parse JSON."""
    url = critic["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": critic["model"],
        "messages": [
            {"role": "system",
             "content": "You are a careful technical auditor. Reply only with the requested JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_tokens": critic.get("max_tokens", 1024),
    }
    try:
        r = httpx.post(url, json=payload, timeout=critic.get("timeout_s", timeout))
        r.raise_for_status()
        data = r.json()
        choice = data["choices"][0]
        content = choice["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError) as e:
        return {"verdict": "ERROR", "evidence_chunks": [],
                "rationale": f"endpoint error: {e}"}
    if content is None:
        # Reasoning models served by vLLM return no content when the reasoning
        # uses the whole max_tokens budget (finish_reason "length").
        return {"verdict": "ERROR", "evidence_chunks": [],
                "rationale": f"empty content (finish_reason={choice.get('finish_reason')})"}
    content = content.strip()

    parsed = _extract_json(content)
    if not parsed:
        return {"verdict": "ERROR", "evidence_chunks": [],
                "rationale": f"unparseable response: {content[:200]}"}
    return parsed


def _extract_json(content: str) -> dict | None:
    """Pull the first parseable JSON object out of an LLM response.

    Tries (in order):
      1. Plain json.loads on the whole content (best case)
      2. ```json ... ``` fenced code-block extraction
      3. Character-walk to find the first balanced {...} block that parses

    The walk approach is necessary because LLMs sometimes precede the JSON
    with prose ("Here is my analysis: { ... }") or include nested braces in
    rationale strings; greedy regex picks up too much or too little.

    Reasoning-tuned models (openreasoning-nemotron, deepseek-r1) wrap their
    chain-of-thought in <think>...</think> tags before producing the actual
    output. Strip those first so the JSON parser sees only the answer.
    """
    s = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    # 1. Direct parse.
    try:
        result = json.loads(s)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 2. Fenced code block ```json {...} ```.
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.DOTALL)
    if fence_match:
        try:
            result = json.loads(fence_match.group(1))
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # 3. Character-walk: find each '{' and try to parse the balanced block.
    pos = 0
    while pos < len(s):
        start = s.find("{", pos)
        if start == -1:
            break
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(s)):
            c = s[i]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        result = json.loads(s[start:i + 1])
                        if isinstance(result, dict):
                            return result
                    except json.JSONDecodeError:
                        pass
                    break
        pos = start + 1

    return None


def _normalize_indices(value: Any) -> list[int]:
    if isinstance(value, list):
        out = []
        for v in value:
            try:
                out.append(int(v))
            except (TypeError, ValueError):
                continue
        return out
    return []


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("claims", type=Path, help="JSONL of claims (from extract_claims_from_doc.py)")
    p.add_argument("out_csv", type=Path, help="Path to write verdict CSV")
    p.add_argument("--config", type=Path, default=_DEFAULT_CONFIG)
    p.add_argument("--top-k-doc", type=int, default=5)
    p.add_argument("--top-k-code", type=int, default=5)
    p.add_argument("--exclude-source", action="append", default=[], metavar="SUBSTR",
                   help="Exclude retrieved chunks with SUBSTR in source_path; repeatable")
    p.add_argument("--limit", type=int, default=0,
                   help="Process only the first N claims (0 = all)")
    args = p.parse_args()

    if not args.claims.is_file():
        print(f"ERROR: claims file not found: {args.claims}", file=sys.stderr)
        return 2

    critics = load_critics(args.config)
    print(f"Loaded {len(critics)} critic(s): {[c['name'] for c in critics]}")

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["claim_id", "claim_text", "section", "kind"]
    for c in critics:
        fieldnames += [f"{c['name']}_verdict", f"{c['name']}_rationale",
                       f"{c['name']}_evidence_chunks"]
    fieldnames += ["agreement", "doc_top_sources", "code_top_sources",
                   "evidence_excluded_n"]

    with args.out_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()

        n = 0
        with args.claims.open(encoding="utf-8") as cf:
            for line in cf:
                line = line.strip()
                if not line:
                    continue
                try:
                    claim = json.loads(line)
                except json.JSONDecodeError:
                    continue

                evidence, excluded_n = retrieve_evidence(
                    claim["text"], args.top_k_doc, args.top_k_code,
                    args.exclude_source)
                evidence_text = _format_evidence(evidence)
                prompt = _VERDICT_PROMPT.format(
                    claim=claim["text"],
                    n_doc=args.top_k_doc, n_code=args.top_k_code,
                    evidence=evidence_text,
                )

                row = {
                    "claim_id": claim.get("id", ""),
                    "claim_text": claim.get("text", ""),
                    "section": claim.get("section", ""),
                    "kind": claim.get("kind", ""),
                }
                verdicts = []
                for c in critics:
                    res = call_critic(c, prompt)
                    verdicts.append(res.get("verdict", "ERROR"))
                    row[f"{c['name']}_verdict"] = res.get("verdict", "ERROR")
                    row[f"{c['name']}_rationale"] = res.get("rationale", "")[:240]
                    row[f"{c['name']}_evidence_chunks"] = json.dumps(
                        _normalize_indices(res.get("evidence_chunks"))
                    )

                row["agreement"] = "yes" if len(set(verdicts)) == 1 else "no"
                row["evidence_excluded_n"] = excluded_n
                row["doc_top_sources"] = json.dumps(
                    [c["source_path"] for c in evidence if c["topic"] == "tychon-docs"][:3]
                )
                row["code_top_sources"] = json.dumps(
                    [c["source_path"] for c in evidence if c["topic"] == "tychon-code"][:3]
                )
                writer.writerow(row)
                fh.flush()

                n += 1
                if args.limit and n >= args.limit:
                    break
                if n % 5 == 0:
                    print(f"  processed {n} claims")

    print(f"\nWrote {args.out_csv} with {n} rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
