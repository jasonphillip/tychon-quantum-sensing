#!/usr/bin/env python3
"""Extract enumerable factual claims from a parsed technical document.

Input: a markdown file (the .docx report converted via pandoc, or the signed
PDF parsed by nemoretriever-parse / Marker).

Output: JSONL on stdout, one claim per line, with fields:
    {"id": str, "text": str, "section": str, "source_line": int, "kind": str}

Heuristics rather than LLM extraction — deliberately. We want a
deterministic, auditable list of candidates the critic loop then evaluates.
The critic loop is where the LLMs live; this stage stays simple and fast.

Claim kinds we extract:
  - numerical: any sentence with a number + unit (Hz, MHz, ms, V, mA, dB, %, etc.)
  - citation:  any sentence with [N], (Author, Year), or ref-style markers
  - reference: any sentence mentioning Figure N, Table N, Section N
  - definitive: any sentence with strong-claim verbs (achieves, demonstrates,
                proves, eliminates, ensures) NOT hedged ("up to", "may", "could")
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterator

# Sentence splitter — quick-and-good-enough; trips on abbreviations like "e.g."
# but we'd rather over-split than under-split here.
_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")

# Claim-detection regexes (order matters; kind is taken from the first match).
_PATTERNS = [
    # Numerical: digit + optional decimal + optional comma-thousands + unit/percent.
    ("numerical",
     re.compile(r"\b\d[\d,]*(\.\d+)?\s?"
                r"(Hz|kHz|MHz|GHz|s|ms|us|µs|ns|"
                r"V|mV|kV|A|mA|µA|W|mW|"
                r"Ω|ohm|"
                r"%|°C|°F|K|"
                r"bit|bits|byte|bytes|MB|GB|TB|"
                r"LUT|LUTs|FF|FFs|"
                r"MHz|"
                r"x|times)\b",
                re.IGNORECASE)),
    # Citation markers: [12], (Author 2024), [Author2024], etc.
    ("citation",
     re.compile(r"(\[\d+(\s*[-,]\s*\d+)*\])"
                r"|(\([A-Z][a-zA-Z]+(?:\s+(?:et\s+al\.?|and\s+[A-Z][a-zA-Z]+))?,?\s+\d{4}\))"
                r"|(\[[A-Z][a-zA-Z]+\d{4}\])")),
    # Cross-references inside the document.
    ("reference",
     re.compile(r"\b(Figure|Fig\.|Table|Tbl\.|Section|Sec\.|Appendix|App\.)\s+"
                r"\d+(\.\d+)*\b")),
    # Strong, definitive claims — extracted last so a numerical or citation match wins.
    ("definitive",
     re.compile(r"\b(achieves|achieved|demonstrates|demonstrated|"
                r"proves|proved|eliminates|eliminated|ensures|ensured|"
                r"satisfies|satisfied|outperforms|outperformed|"
                r"is\s+(?:the\s+first|capable|able)|"
                r"meets\s+the\s+requirement|exceeds\s+the\s+requirement)\b",
                re.IGNORECASE)),
]

# Hedging words that disqualify a sentence from "definitive" (still pass
# numerical/citation/reference if those matched first).
_HEDGES = re.compile(r"\b(may|might|could|possibly|"
                     r"approximately|roughly|"
                     r"up\s+to|at\s+least|on\s+the\s+order\s+of|"
                     r"we\s+expect|we\s+believe)\b",
                     re.IGNORECASE)


def _iter_paragraphs(text: str) -> Iterator[tuple[str, int, str]]:
    """Yield (paragraph_text, first_line_no, current_section).

    Markdown wraps sentences across lines. Iterating line-by-line and then
    sentence-splitting (the original approach) cut sentences at line wraps,
    producing fragment "claims" like "The system demonstrates that the primary
    failure mode of classical" that crashed the audit pass.

    A paragraph is a run of non-blank, non-header, non-code lines. Within a
    paragraph, single newlines become spaces. Headers reset the section;
    blank lines and code-fence transitions flush the current paragraph.
    """
    current_section = ""
    current_para: list[str] = []
    para_start_line = 0
    in_code_fence = False
    line_no = 0

    def flush() -> Iterator[tuple[str, int, str]]:
        if current_para:
            yield (" ".join(current_para).strip(), para_start_line, current_section)

    for raw_line in text.splitlines():
        line_no += 1
        stripped = raw_line.strip()

        # Code-fence toggles flush the paragraph and skip until close.
        if stripped.startswith("```"):
            yield from flush()
            current_para = []
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue

        # ATX headers reset section context.
        if raw_line.startswith("#"):
            yield from flush()
            current_para = []
            current_section = stripped.lstrip("# ").strip()
            continue

        # 4-space-indented blocks = code; HTML tags get skipped coarsely.
        if raw_line.startswith("    ") or stripped.startswith("<"):
            yield from flush()
            current_para = []
            continue

        # Blank line = paragraph boundary.
        if not stripped:
            yield from flush()
            current_para = []
            continue

        # Regular text line: extend the current paragraph.
        if not current_para:
            para_start_line = line_no
        current_para.append(stripped)

    yield from flush()


def iter_claims(md_path: Path) -> Iterator[dict]:
    """Yield claim dicts from a markdown file (paragraph-aware)."""
    text = md_path.read_text(encoding="utf-8", errors="replace")
    cid = 0
    for paragraph, line_no, section in _iter_paragraphs(text):
        # Sentence-split the paragraph.
        for sentence in _SENT_RE.split(paragraph):
            s = sentence.strip()
            if len(s) < 30 or len(s) > 500:
                continue
            kind = _classify(s)
            if not kind:
                continue
            cid += 1
            yield {
                "id": f"c{cid:04d}",
                "text": s,
                "section": section,
                "source_line": line_no,
                "kind": kind,
            }


def _classify(sentence: str) -> str | None:
    """Return the claim kind that fires first, honoring _HEDGES for definitive."""
    for kind, pat in _PATTERNS:
        if pat.search(sentence):
            if kind == "definitive" and _HEDGES.search(sentence):
                continue
            return kind
    return None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("doc", type=Path, help="Markdown file to extract from")
    p.add_argument("--limit", type=int, default=0,
                   help="Cap the number of claims emitted (0 = no cap)")
    args = p.parse_args()

    if not args.doc.is_file():
        print(f"ERROR: not a file: {args.doc}", file=sys.stderr)
        return 2

    n = 0
    for claim in iter_claims(args.doc):
        sys.stdout.write(json.dumps(claim, ensure_ascii=False) + "\n")
        n += 1
        if args.limit and n >= args.limit:
            break
    print(f"  extracted {n} claims from {args.doc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
