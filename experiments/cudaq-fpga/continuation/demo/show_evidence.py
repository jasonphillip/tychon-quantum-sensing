#!/usr/bin/env python3
"""Display saved evidence only after validating every hash and evidence reference."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any


class EvidenceError(ValueError):
    """The supplied manifest or saved evidence failed validation."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f'Duplicate JSON key: {key!r}')
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise EvidenceError(f'Non-finite JSON number: {value}')


def _relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise EvidenceError('Evidence paths must be nonempty relative strings')
    if (not value.isprintable() or '\\' in value or ':' in value
            or PurePosixPath(value).is_absolute()
            or any(part in ('', '.', '..') for part in value.split('/'))):
        raise EvidenceError(f'Invalid relative evidence path: {value!r}')
    return value


def _within_root(root: Path, relative: str) -> Path:
    relative = _relative_path(relative)
    try:
        path = (root / relative).resolve(strict=True)
        path.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise EvidenceError(f'Missing or escaping evidence path: {relative!r}') from exc
    if not path.is_file():
        raise EvidenceError(f'Evidence path is not a regular file: {relative!r}')
    return path


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or not value.isprintable():
        raise EvidenceError(f'Fact {field} must be nonempty printable text')
    return value


def validate_manifest(root: Path, manifest: str) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Validate saved bytes and link structure; do not adjudicate the stated facts."""
    try:
        root = root.resolve(strict=True)
        if not root.is_dir():
            raise EvidenceError('Workspace root must be an existing directory')
        manifest_path = _within_root(root, manifest)
        data = json.loads(manifest_path.read_text(encoding='utf-8'),
                          object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError) as exc:
        raise EvidenceError(f'Cannot read evidence manifest: {exc}') from exc
    if not isinstance(data, dict):
        raise EvidenceError('Manifest must be a JSON object')
    files, facts = data.get('files'), data.get('facts')
    if not isinstance(files, dict) or not files:
        raise EvidenceError('Manifest files must be a nonempty object')
    if not isinstance(facts, list) or not facts:
        raise EvidenceError('Manifest facts must be a nonempty list')
    paths: dict[str, Path] = {}
    for name, expected in files.items():
        if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', expected):
            raise EvidenceError(f'Invalid SHA-256 for {name!r}')
        paths[name] = _within_root(root, name)
    for fact in facts:
        if not isinstance(fact, dict) or 'value' not in fact:
            raise EvidenceError('Each fact must be an object with a value')
        _text(fact.get('label'), 'label')
        _text(fact.get('scope'), 'scope')
        evidence = fact.get('evidence')
        if not isinstance(evidence, list) or not evidence:
            raise EvidenceError('Each fact must reference at least one listed evidence file')
        for name in evidence:
            _relative_path(name)
            if name not in files:
                raise EvidenceError(f'Fact references unlisted evidence: {name!r}')
    # Read in bounded chunks. No facts are printed unless every file passes.
    for name, path in paths.items():
        digest = hashlib.sha256()
        try:
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
        except OSError as exc:
            raise EvidenceError(f'Cannot read evidence file: {name!r}') from exc
        if digest.hexdigest() != files[name].lower():
            raise EvidenceError(f'SHA-256 mismatch: {name!r}')
    return files, facts


def render(files: dict[str, str], facts: list[dict[str, Any]]) -> str:
    lines = [f'Verified saved evidence: {len(files)} files; {len(facts)} facts.',
             'Saved-file integrity and references only. No live hardware or performance checks.']
    for fact in facts:
        value = json.dumps(fact['value'], ensure_ascii=True, sort_keys=True, allow_nan=False)
        if isinstance(fact['value'], str):
            value = value[1:-1]
        lines.extend(['', f'{fact["label"]}: {value}', f'  Scope: {fact["scope"]}',
                      '  Evidence: ' + ', '.join(fact['evidence'])])
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Existing workspace directory')
    parser.add_argument('--manifest', default='demo/evidence_manifest.json',
                        help='Manifest path relative to the workspace root')
    args = parser.parse_args(argv)
    try:
        files, facts = validate_manifest(args.root, args.manifest)
        output = render(files, facts)
    except (EvidenceError, OSError, ValueError) as exc:
        print(f'Evidence verification failed: {exc}', file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
