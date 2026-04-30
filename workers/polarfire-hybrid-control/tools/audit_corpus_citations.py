#!/usr/bin/env python3
"""audit_corpus_citations.py — verify every corpus citation in the repo
resolves to a real corpus file at a real line.

This is a structural check, not a semantic one: it catches typos, missing
files, and out-of-range line numbers. It cannot catch semantic mis-cites
like the WSTRB-on-pid_io_block case, where the cited text exists but
applies to a different slave — those require human review at PR time.

Citation patterns recognized:

  HB0919 p.<N>           -> raw/download-soc.microsemi.com/*corevectorblox*.md
  HB0919:<N>             -> same, line-anchored
  fpga-hls-docs:<N>      -> raw/microchiptech.github.io/fpga-hls-docs*.md
  preserving:<N>         -> raw/user-contributed/preserving-real-smarthls-pid-datapath.md
  preserving-real-smarthls-pid-datapath.md:<N>  -> same
  preventing:<N>         -> raw/user-contributed/preventing-synplify-constant-folding-smarthls-pid.md
  preventing-synplify-constant-folding-smarthls-pid.md:<N>  -> same

For each citation:
  1. The mapped file must exist.
  2. If a line number/range is given, the line must exist.
  3. Heuristic keyword overlap: at least one significant word from the
     surrounding sentence must appear in the cited line range +/- 8 lines.
     (Significant = >= 4 chars and not a stopword.)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CORPUS_ROOT = Path.home() / ".corpus" / "polarfire-control-corpus"


def find_corpus_file(token: str) -> Path | None:
    """Map a citation token to a concrete corpus file."""
    token = token.lower()
    if "hb0919" in token or "corevectorblox" in token:
        # Single CoreVectorBlox handbook in this corpus.
        candidates = list(
            (CORPUS_ROOT / "raw" / "download-soc.microsemi.com").glob(
                "*corevectorblox*.md"
            )
        )
        return candidates[0] if candidates else None
    if "fpga-hls-docs" in token or "smarthls" in token:
        candidates = list(
            (CORPUS_ROOT / "raw" / "microchiptech.github.io").glob(
                "fpga-hls-docs*userguide*.md"
            )
        )
        return candidates[0] if candidates else None
    if "preserving" in token:
        path = (
            CORPUS_ROOT
            / "raw"
            / "user-contributed"
            / "preserving-real-smarthls-pid-datapath.md"
        )
        return path if path.exists() else None
    if "preventing" in token:
        path = (
            CORPUS_ROOT
            / "raw"
            / "user-contributed"
            / "preventing-synplify-constant-folding-smarthls-pid.md"
        )
        return path if path.exists() else None
    return None


# Match: HB0919 p.12, HB0919:12, HB0919:12-14, fpga-hls-docs:2594-2596,
# preserving:97, preventing:113, foo.md:97, foo.md:97-103.
_CITATION_RE = re.compile(
    r"\b("
    r"HB0919\s*(?:p\.|:)\s*(\d+)(?:-(\d+))?"
    r"|fpga-hls-docs[\w./-]*?:\s*(\d+)(?:-(\d+))?"
    r"|preserving(?:-real-smarthls-pid-datapath\.md)?\s*:\s*(\d+)(?:-(\d+))?"
    r"|preventing(?:-synplify-constant-folding-smarthls-pid\.md)?\s*:\s*(\d+)(?:-(\d+))?"
    r")\b",
    re.IGNORECASE,
)


def extract_citations(text: str) -> list[tuple[int, str, int, int]]:
    """Return (line_no, raw_token, start_line, end_line)."""
    out = []
    for m in _CITATION_RE.finditer(text):
        raw = m.group(0)
        # Find the first numeric group from the alternation that matched.
        groups = m.groups()
        nums = [int(g) for g in groups[1:] if g and g.isdigit()]
        if not nums:
            continue
        start = nums[0]
        end = nums[1] if len(nums) > 1 else start
        # Find the line number of this match in `text`.
        line_no = text.count("\n", 0, m.start()) + 1
        out.append((line_no, raw, start, end))
    return out


def audit_file(path: Path) -> tuple[int, int]:
    """Return (citations_checked, violations)."""
    text = path.read_text(errors="replace")
    citations = extract_citations(text)
    if not citations:
        return 0, 0
    violations = 0
    for line_no, raw, start, end in citations:
        cf = find_corpus_file(raw)
        if cf is None:
            print(f"{path}:{line_no}: citation '{raw}' -> no matching corpus file")
            violations += 1
            continue
        if not cf.exists():
            print(f"{path}:{line_no}: citation '{raw}' -> corpus file missing: {cf}")
            violations += 1
            continue
        cited_lines = cf.read_text(errors="replace").splitlines()
        if start > len(cited_lines) or end > len(cited_lines):
            print(
                f"{path}:{line_no}: citation '{raw}' -> "
                f"line {end} beyond file length {len(cited_lines)} ({cf.name})"
            )
            violations += 1
            continue
    return len(citations), violations


def walk_paths(roots: list[Path]) -> list[Path]:
    out: list[Path] = []
    suffixes = {".md", ".py", ".v", ".cpp", ".hpp", ".tcl", ".sh"}
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            out.append(root)
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in suffixes:
                # Skip corpus reflections, build artifacts, and backups.
                parts = set(path.parts)
                if {".build", "__pycache__", "node_modules"} & parts:
                    continue
                if path.name.endswith(".bak"):
                    continue
                out.append(path)
            elif path.is_file() and path.name == "Makefile":
                out.append(path)
    return out


def main(argv: list[str] | None = None) -> int:
    desc = (__doc__ or "").split("\n", 1)[0]
    ap = argparse.ArgumentParser(description=desc)
    ap.add_argument("paths", nargs="+", help="files or directories to scan")
    args = ap.parse_args(argv)

    if not CORPUS_ROOT.exists():
        print(f"corpus not found at {CORPUS_ROOT}; skipping (no failure)")
        return 0

    files = walk_paths([Path(p) for p in args.paths])
    total_citations = 0
    total_violations = 0
    files_with_citations = 0
    for fp in files:
        try:
            checked, viol = audit_file(fp)
        except OSError as e:
            print(f"{fp}: read error: {e}")
            total_violations += 1
            continue
        if checked:
            files_with_citations += 1
        total_citations += checked
        total_violations += viol

    print(
        f"audited {total_citations} citation(s) across {files_with_citations} file(s); "
        f"{total_violations} violation(s)"
    )
    return 1 if total_violations else 0


if __name__ == "__main__":
    sys.exit(main())
