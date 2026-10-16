"""Check every file of this evidence package against ARTIFACTS.sha256.json (stdlib only; no inference).

Usage: python3 check_package.py --expected-artifacts-sha256 <sha256>
Exit 0 and "RESULT: PASS" when the manifest pin and every listed file hash match.
"""
import argparse, hashlib, json, sys
from pathlib import Path

here = Path(__file__).resolve().parent
p = argparse.ArgumentParser(); p.add_argument("--expected-artifacts-sha256", required=True); a = p.parse_args()
mp = here / "ARTIFACTS.sha256.json"; raw = mp.read_bytes()
if hashlib.sha256(raw).hexdigest() != a.expected_artifacts_sha256:
    print("RESULT: FAIL manifest pin differs"); sys.exit(1)
bad = [n for n, r in json.loads(raw)["files"].items() if hashlib.sha256((here / n).read_bytes()).hexdigest() != r["sha256"]]
print(f"files checked: {len(json.loads(raw)['files'])}; mismatches: {len(bad)}")
for n in bad: print("  MISMATCH", n)
print("RESULT:", "PASS" if not bad else "FAIL"); sys.exit(1 if bad else 0)
