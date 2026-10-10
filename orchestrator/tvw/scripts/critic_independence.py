"""Measure verdict agreement and effective independent votes in a critic panel.

Kish votes: n_eff = n / (1 + (n - 1) * rho), where rho is mean pairwise
phi on SUPPORTED indicators, or error indicators when --truth is supplied.
Reference: arXiv 2605.29800, "Nine Judges, Two Effective Votes", section 3.3.
Usage: python3 tvw/scripts/critic_independence.py tvw/audits/stage-4.7-verdicts.csv
"""

import argparse
from collections import Counter
import csv
from itertools import combinations
import json
import math


def normalized(value):
    return (value or "").strip().upper()


def read_verdicts(path):
    """Return critic names and claim rows; use None for a missing critic."""
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        if {"claim", "critic", "verdict"} <= set(fields):
            critics = []
            claims = {}
            for row in reader:
                claim, critic = row["claim"], row["critic"]
                if not claim or not critic:
                    raise ValueError("long format requires claim and critic")
                if critic not in critics:
                    critics.append(critic)
                claim_row = claims.setdefault(claim, {})
                if critic in claim_row:
                    raise ValueError(f"duplicate critic {critic!r} for claim {claim!r}")
                claim_row[critic] = normalized(row["verdict"])
            return critics, claims

        claim_field = "claim_id" if "claim_id" in fields else "claim"
        critics = [field[:-8] for field in fields if field.endswith("_verdict")]
        if claim_field not in fields or not critics:
            raise ValueError("expected long claim/critic/verdict or wide claim and *_verdict columns")
        claims = {}
        for row in reader:
            claim = row[claim_field]
            if not claim or claim in claims:
                raise ValueError("wide format requires unique, nonempty claim IDs")
            claims[claim] = {critic: normalized(row[f"{critic}_verdict"])
                             for critic in critics}
        return critics, claims


def read_truth(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not {"claim", "verdict"} <= set(reader.fieldnames or []):
            raise ValueError("truth CSV needs claim and verdict columns")
        truth = {}
        for row in reader:
            claim, verdict = row["claim"], normalized(row["verdict"])
            if not claim or not verdict or claim in truth:
                raise ValueError("truth CSV needs unique claims and nonempty verdicts")
            truth[claim] = verdict
        return truth


def cohen_kappa(left, right):
    count = len(left)
    observed = sum(a == b for a, b in zip(left, right)) / count
    first, second = Counter(left), Counter(right)
    chance = sum(first[label] * second[label] for label in first.keys() | second.keys()) / count**2
    return None if math.isclose(chance, 1.0) else (observed - chance) / (1 - chance)


def phi(left, right):
    n11 = sum(a and b for a, b in zip(left, right))
    n10 = sum(a and not b for a, b in zip(left, right))
    n01 = sum(not a and b for a, b in zip(left, right))
    n00 = len(left) - n11 - n10 - n01
    denominator = math.sqrt((n11 + n10) * (n01 + n00) *
                            (n11 + n01) * (n10 + n00))
    return None if denominator == 0 else (n11 * n00 - n10 * n01) / denominator


def measure(critics, claims, truth=None, positive="SUPPORTED"):
    if len(critics) < 2:
        raise ValueError("at least two critics are required")
    kept = {claim: row for claim, row in claims.items()
            if all(row.get(critic) not in (None, "", "ERROR") for critic in critics)}
    dropped = len(claims) - len(kept)
    verdict_rows = list(kept.values())
    n = len(critics)
    result = {
        "n_critics": n,
        "n_claims": len(kept),
        "n_dropped": dropped,
        "basis": "errors against --truth" if truth is not None else f"verdicts: {positive} vs other",
        "raw_agreement": None,
        "mean_pairwise_agreement": None,
        "fleiss_kappa": None,
        "mean_pairwise_cohen_kappa": None,
        "mean_pairwise_phi": None,
        "n_eff": None,
        "n_eff_note": "undefined: no kept claims",
        "positive_rate": {},
        "prevalence_warning": None,
        "n_truth_matched": None,
    }
    if not verdict_rows:
        return result

    count = len(verdict_rows)
    rates = {c: sum(row[c] == positive for row in verdict_rows) / count for c in critics}
    result["positive_rate"] = rates
    result["raw_agreement"] = sum(len({row[c] for c in critics}) == 1
                                  for row in verdict_rows) / count
    if result["raw_agreement"] >= 0.8 and any(rate >= 0.9 or rate <= 0.1 for rate in rates.values()):
        result["prevalence_warning"] = (
            f"near-constant {positive} rate: high raw agreement here comes mostly from prevalence; "
            "read the chance-corrected agreement, and pass --truth if reference verdicts exist")
    category_counts = [Counter(row[c] for c in critics) for row in verdict_rows]
    pooled = Counter(value for row in verdict_rows for value in (row[c] for c in critics))
    p_bar = sum(sum(v * (v - 1) for v in counts.values()) / (n * (n - 1))
                for counts in category_counts) / count
    p_chance = sum((frequency / (count * n)) ** 2 for frequency in pooled.values())
    if not math.isclose(p_chance, 1.0):
        result["fleiss_kappa"] = (p_bar - p_chance) / (1 - p_chance)

    pairs = list(combinations(critics, 2))
    agreements = []
    kappas = []
    for first, second in pairs:
        left = [row[first] for row in verdict_rows]
        right = [row[second] for row in verdict_rows]
        agreements.append(sum(a == b for a, b in zip(left, right)) / count)
        kappas.append(cohen_kappa(left, right))
    result["mean_pairwise_agreement"] = sum(agreements) / len(pairs)
    if all(value is not None for value in kappas):
        result["mean_pairwise_cohen_kappa"] = sum(kappas) / len(pairs)

    vectors = {critic: [int(row[critic] != truth[claim]) if truth is not None
                        else int(row[critic] == positive)
                        for claim, row in kept.items() if truth is None or claim in truth]
               for critic in critics}
    correlations = [phi(vectors[first], vectors[second]) for first, second in pairs]
    if truth is not None:
        result["n_truth_matched"] = len(vectors[critics[0]])
    if not vectors[critics[0]]:
        result["n_eff_note"] = "undefined: no kept claims present in --truth"
    elif any(value is None for value in correlations):
        result["n_eff_note"] = "undefined: a critic's vector has no variance"
    else:
        rho = sum(correlations) / len(correlations)
        result["mean_pairwise_phi"] = rho
        denominator = 1 + (n - 1) * rho
        effective = n / denominator if denominator > 0 else math.inf
        clipped = min(n, max(1.0, effective))
        result["n_eff"] = clipped
        result["n_eff_note"] = "clipped to [1, n]" if clipped != effective else "Kish effective votes"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", help="wide or long verdict CSV")
    parser.add_argument("--truth", help="reference CSV with claim,verdict columns")
    parser.add_argument("--json", action="store_true", help="print one JSON object")
    parser.add_argument("--positive", default="SUPPORTED", help="verdict counted as acceptance (default SUPPORTED)")
    args = parser.parse_args()
    try:
        critics, claims = read_verdicts(args.csv)
        truth = read_truth(args.truth) if args.truth else None
        result = measure(critics, claims, truth, normalized(args.positive))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if args.json:
        print(json.dumps(result, allow_nan=False))
    else:
        for key, value in result.items():
            if key == "n_truth_matched" and value is None:
                continue
            label = "effective votes" if key == "n_eff" else key.replace("_", " ")
            if isinstance(value, float):
                value = f"{value:.3f}"
            elif isinstance(value, dict):
                value = ", ".join(f"{name} {rate:.3f}" for name, rate in value.items())
            print(f"{label}: {value}")
        print("Without --truth, effective votes measure how redundant the verdicts are, not whether they are right.")
        print("Perfect agreement with no variance is not evidence of independent checking.")


if __name__ == "__main__":
    main()
