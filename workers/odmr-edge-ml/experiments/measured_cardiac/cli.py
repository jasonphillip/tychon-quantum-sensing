"""Metadata-only CLI. Scientific replay is deliberately not exposed before Freeze A."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .loader import inventory
from .metadata import eligibility, load_manifest

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inv = commands.add_parser("inventory")
    inv.add_argument("--archive", type=Path, required=True)
    check = commands.add_parser("eligibility")
    check.add_argument("--manifest", type=Path, required=True)
    check.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "inventory":
        print(json.dumps({"signal_values_read": False, "members": inventory(args.archive)}, indent=2))
        return 0
    verdict = eligibility(load_manifest(args.manifest))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(verdict, stream, indent=2)
        stream.write("\n")
    print(json.dumps(verdict, indent=2))
    return 0 if verdict["eligible"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
