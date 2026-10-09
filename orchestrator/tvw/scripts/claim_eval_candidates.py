"""Build a seeded, blind claim-labeling set from extracted claims."""

import argparse
import csv
import json
import random
import re
from pathlib import Path


UNMEASURED_TEMPLATES = (
    "The hardware achieves a measured 99.9% field reliability rate.",
    "The system consumes exactly 1.2 joules per inference in deployment.",
    "The device has a measured ten-year service life in orbit.",
    "The controller reaches 99.99% uptime in flight operations.",
    "The sensor maintains a measured 0.01 degree pointing error in orbit.",
    "The deployed system has a measured zero percent failure rate.",
    "The production unit costs exactly 500 dollars to manufacture.",
    "The flight unit weighs exactly 250 grams after integration.",
    "The system sustains a measured 10 gigabit per second data rate.",
    "The device survives exactly 100 kilorad total ionizing dose.",
    "The deployed sensor needs exactly one hour between calibrations.",
    "The integrated payload has a measured 50 watt peak draw.",
)
ORIGIN_LABEL = dict(unit_error="contradicted", revision_mismatch="contradicted",
                    unmeasured="unsupported", stale="stale", causal="causal")
NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?!\w)")
VERSION = re.compile(r"\bv\d+(?:\.\d+)+\b", re.I)
CAUSAL = re.compile(r"is associated with|correlates with|was designed to|is designed to|enables|provides|allows|supports|improves|reduces|achieves", re.I)
DATE = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
UNIT = re.compile(r"\b(?:ns|µs|us|ms|s|Hz|kHz|MHz|GHz|W|mW|V|mV|µT|uT|nT|mT|T|GB|MB)\b")
UNIT_SWAP = {"ns": "µs", "µs": "ns", "us": "ns", "ms": "s", "s": "ms",
             "Hz": "kHz", "kHz": "Hz", "MHz": "GHz", "GHz": "MHz",
             "W": "mW", "mW": "W", "V": "mV", "mV": "V",
             "µT": "nT", "uT": "nT", "nT": "µT", "mT": "T", "T": "mT",
             "GB": "MB", "MB": "GB"}


def perturb(parent, origin, originals, rng):
    text = parent["text"]
    if origin == "unmeasured":
        return rng.choice(UNMEASURED_TEMPLATES) if parent["kind"] == "numerical" else None
    if origin == "causal":
        match = CAUSAL.search(text)
        if match:
            return text[:match.start()] + rng.choice(("causes", "guarantees")) + text[match.end():]
        return text.rstrip(" .") + ", and this is the direct cause of the measured system performance."
    if origin == "stale":
        # Stale = an older version or date token replaces the current one; no token, no stale edit.
        match = VERSION.search(text)
        if match:
            parts = match.group()[1:].split(".")
            older = [str(max(int(parts[0]) - 1, 0))] + ["0"] * (len(parts) - 1)
            if older != parts:
                return text[:match.start()] + "v" + ".".join(older) + text[match.end():]
        match = DATE.search(text)
        if match:
            return text[:match.start()] + f"{int(match.group(1)) - 1}-{match.group(2)}-{match.group(3)}" + text[match.end():]
        return None
    if origin == "unit_error":
        units = list(UNIT.finditer(text))
        if units:
            match = rng.choice(units)
            return text[:match.start()] + UNIT_SWAP[match.group()] + text[match.end():]
        nums = list(NUMBER.finditer(text))
        if not nums:
            return None
        match = rng.choice(nums)
        number = float(match.group().replace(",", ""))
        changed = number * rng.choice((1000, 0.001))
        return text[:match.start()] + f"{changed:g}" + text[match.end():]
    if origin == "revision_mismatch":
        nums = list(NUMBER.finditer(text))
        peers = [p for p in originals if p["id"] != parent["id"] and p["kind"] == parent["kind"] and NUMBER.search(p["text"])]
        if not nums or not peers:
            return None
        match = rng.choice(nums)
        alternatives = [m.group() for p in peers for m in NUMBER.finditer(p["text"]) if m.group() != match.group()]
        if not alternatives:
            return None
        return text[:match.start()] + rng.choice(alternatives) + text[match.end():]
    raise ValueError(origin)


def generate(claims_path, out_dir, n_original, n_perturbed, seed):
    rng = random.Random(seed)
    with Path(claims_path).open() as handle:
        claims = [json.loads(line) for line in handle if line.strip()]
    if len({c["id"] for c in claims}) != len(claims):
        raise ValueError("duplicate source claim id")
    if not 0 <= n_original <= len(claims) or n_perturbed < 0:
        raise ValueError("invalid requested counts")
    originals = rng.sample(claims, n_original)
    # Assign the same opaque ID format to both classes before making blind input.
    used_ids = set()

    def new_id():
        while True:
            value = f"e{rng.getrandbits(64):016x}"
            if value not in used_ids:
                used_ids.add(value)
                return value

    rows = [dict(c, id=new_id(), source_id=c["id"], origin="original", parent_id=None)
            for c in originals]
    parent_ids = {r["source_id"]: r["id"] for r in rows}
    possibilities = []
    for origin in ORIGIN_LABEL:
        for parent in originals:
            # A separate RNG preserves the main sampling stream during feasibility checks.
            if perturb(parent, origin, originals, random.Random(0)) not in (None, parent["text"]):
                possibilities.append((origin, parent))
    if n_perturbed and not possibilities:
        raise ValueError("sampled originals have no eligible perturbations")
    rng.shuffle(possibilities)
    seen = {r["text"] for r in rows}
    origins = list(ORIGIN_LABEL)
    by_origin = {o: [p for p in possibilities if p[0] == o] for o in origins}
    # Balance: n_perturbed split evenly over origins (remainder to the first ones); an origin with
    # no eligible parent gives its quota to the others in turn.
    quota = {o: n_perturbed // len(origins) + (i < n_perturbed % len(origins)) for i, o in enumerate(origins)}
    plan = []
    for o in origins:
        plan += [o] * quota[o]
    def draw(pool, index):
        for attempt in range(max(20, len(pool) * 4)):
            origin, parent = pool[(index + attempt) % len(pool)]
            changed = perturb(parent, origin, originals, rng)
            if changed and changed not in seen and changed != parent["text"]:
                return origin, parent, changed
        return None

    for index, want in enumerate(plan):
        got = (draw(by_origin[want], index) if by_origin[want] else None) or draw(possibilities, index)
        if got is None:
            raise ValueError("cannot generate enough distinct perturbations")
        origin, parent, changed = got
        seen.add(changed)
        rows.append(dict(parent, id=new_id(), source_id=parent["id"], text=changed,
                         kind="definitive" if origin == "unmeasured" else parent["kind"],
                         origin=origin, parent_id=parent_ids[parent["id"]]))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "candidates.jsonl").open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (out / "labels_constructed.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("id", "label", "origin"))
        writer.writeheader()
        writer.writerows(dict(id=r["id"], label=ORIGIN_LABEL[r["origin"]], origin=r["origin"])
                         for r in rows if r["origin"] != "original")
    rng.shuffle(rows)
    with (out / "label_input.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("id", "text"))
        writer.writeheader()
        writer.writerows(dict(id=r["id"], text=r["text"]) for r in rows)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--n-original", required=True, type=int)
    parser.add_argument("--n-perturbed", required=True, type=int)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    generate(args.claims, args.out, args.n_original, args.n_perturbed, args.seed)


if __name__ == "__main__":
    main()
