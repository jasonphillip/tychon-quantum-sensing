"""Score claim critics against independent and constructed labels."""

import argparse
import csv
import math
from collections import Counter
from pathlib import Path

LABELS = ("contradicted", "stale", "causal", "unsupported", "supported")
VERDICTS = {"SUPPORTED", "CONTRADICTED", "UNSUPPORTED", "WEAK", "ERROR"}
POLICY = ("Decision per row: accept iff every critic verdict is SUPPORTED; reject iff any CONTRADICTED "
          "or all UNSUPPORTED; else abstain; ERROR counts as parser failure and abstain.")
MAJORITY_POLICY = ("Decision per row (majority): accept iff at least 2 verdicts are SUPPORTED and none is CONTRADICTED; "
                   "reject iff at least 2 are CONTRADICTED or all are UNSUPPORTED; else abstain; ERROR counts as parser failure and abstain.")


def read_csv(path, key, fields):
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        if not set(fields).issubset(reader.fieldnames or []):
            raise ValueError(f"{path}: required columns: {', '.join(fields)}")
        rows = list(reader)
    result = {row[key]: row for row in rows}
    if len(result) != len(rows) or "" in result:
        raise ValueError(f"{path}: duplicate or empty ids")
    return result


def ratio(num, den):
    return num / den if den else None


def kappa(a, b):
    if not a:
        return None
    observed = sum(x == y for x, y in zip(a, b)) / len(a)
    ca, cb = Counter(a), Counter(b)
    chance = sum(ca[label] * cb[label] for label in LABELS) / len(a) ** 2
    return (observed - chance) / (1 - chance) if chance < 1 else 1.0


def decision(verdicts, policy="unanimous"):
    if "ERROR" in verdicts:
        return "abstain"
    if policy == "majority":
        if verdicts.count("SUPPORTED") >= 2 and "CONTRADICTED" not in verdicts:
            return "accept"
        if verdicts.count("CONTRADICTED") >= 2 or all(v == "UNSUPPORTED" for v in verdicts):
            return "reject"
        return "abstain"
    if all(v == "SUPPORTED" for v in verdicts):
        return "accept"
    if "CONTRADICTED" in verdicts or all(v == "UNSUPPORTED" for v in verdicts):
        return "reject"
    return "abstain"


def metrics(ids, labels, verdicts, columns, policy="unanimous"):
    outcomes = [decision([verdicts[i][column] for column in columns], policy) for i in ids]
    accepted = [i for i, outcome in zip(ids, outcomes) if outcome == "accept"]
    positives = sum(labels[i] == "supported" for i in ids)
    true_accepted = sum(labels[i] == "supported" for i in accepted)
    return dict(n=len(ids), accept_precision=ratio(true_accepted, len(accepted)),
                accept_recall=ratio(true_accepted, positives),
                false_acceptance_rate=ratio(len(accepted) - true_accepted, len(accepted)),
                abstention_rate=ratio(outcomes.count("abstain"), len(ids)),
                parser_failure_rate=ratio(sum(any(verdicts[i][c] == "ERROR" for c in columns)
                                              for i in ids), len(ids)))


def dependence(ids, labels, verdicts, columns):
    if len(columns) != 2 or not ids:
        return dict(both_wrong_rate=None, error_correlation=None)
    wrong = [[int((decision([verdicts[i][c]]) == "accept") != (labels[i] == "supported"))
              for i in ids] for c in columns]
    n = len(ids)
    p, q = sum(wrong[0]) / n, sum(wrong[1]) / n
    both = sum(x and y for x, y in zip(*wrong)) / n
    denominator = math.sqrt(p * (1 - p) * q * (1 - q))
    return dict(both_wrong_rate=both, error_correlation=(both - p * q) / denominator if denominator else None)


def evaluate(verdicts_path, constructed_path, labels_a_path, labels_b_path,
             labels_c_path=None, critics=None, policy="unanimous"):
    if policy not in ("unanimous", "majority"):
        raise ValueError("unknown decision policy")
    constructed = read_csv(constructed_path, "id", ("id", "label", "origin"))
    a = read_csv(labels_a_path, "id", ("id", "label", "evidence", "rationale"))
    b = read_csv(labels_b_path, "id", ("id", "label", "evidence", "rationale"))
    c = read_csv(labels_c_path, "id", ("id", "label", "evidence", "rationale")) if labels_c_path is not None else None
    sources = {"a": a, "b": b}
    if c is not None:
        sources["c"] = c
    if any(set(source) != set(a) for source in sources.values()) or not set(constructed) <= set(a):
        raise ValueError("labeler and constructed ids do not align")
    if any(row["label"] not in LABELS for source in (*sources.values(), constructed) for row in source.values()):
        raise ValueError("unknown label")
    originals = [i for i in a if i not in constructed]
    contested = [i for i in originals if len({source[i]["label"] for source in sources.values()}) > 1]

    def original_label(i):
        votes = Counter(source[i]["label"] for source in sources.values())
        if c is not None and max(votes.values()) >= 2:
            return max(votes, key=votes.get)
        return min(votes, key=LABELS.index)

    final = {i: constructed[i]["label"] if i in constructed else original_label(i) for i in a}
    if c is None:
        labelers = {"kappa": kappa([a[i]["label"] for i in originals],
                                   [b[i]["label"] for i in originals])}
    else:
        labelers = {f"kappa_{left}{right}": kappa([sources[left][i]["label"] for i in originals],
                                                   [sources[right][i]["label"] for i in originals])
                    for left, right in (("a", "b"), ("a", "c"), ("b", "c"))}
        labelers["three_way_raw_agreement"] = ratio(len(originals) - len(contested), len(originals))
    for name, source in sources.items():
        ids = list(constructed)
        labelers[name] = dict(
            constructed_binary_accuracy=ratio(sum((source[i]["label"] == "supported") ==
                                                    (constructed[i]["label"] == "supported") for i in ids), len(ids)),
            constructed_five_class_accuracy=ratio(sum(source[i]["label"] == constructed[i]["label"] for i in ids), len(ids)),
            original_supported_count=sum(source[i]["label"] == "supported" for i in originals))
    result = dict(final_labels=final, contested=contested, labelers=labelers,
                  contested_detail=[dict(id=i, **{name: source[i]["label"] for name, source in sources.items()},
                                         final=final[i]) for i in contested])
    if policy != "unanimous":
        result["policy"] = policy
    if verdicts_path is None:
        return result
    verdict_rows = read_csv(verdicts_path, "claim_id", ("claim_id",))
    if set(verdict_rows) != set(a):
        raise ValueError("verdict and labeler ids do not align")
    available = [column for column in next(iter(verdict_rows.values())) if column.endswith("_verdict")]
    if critics is None:
        columns = available
    else:
        columns = [f"{name}_verdict" for name in critics]
        if not columns or len(set(columns)) != len(columns) or any(column not in available for column in columns):
            raise ValueError("critics must name distinct available verdict columns without the _verdict suffix")
    if not columns:
        raise ValueError("no critic verdict columns")
    verdicts = {i: {c: row[c].strip().upper() for c in columns} for i, row in verdict_rows.items()}
    if any(v not in VERDICTS for row in verdicts.values() for v in row.values()):
        raise ValueError("unknown critic verdict")
    result["critic_columns"] = columns
    result["metrics"] = {}
    result["dependence"] = {}
    result["false_acceptances_by_origin"] = {}
    for scope, ids in (("all", list(a)), ("uncontested", [i for i in a if i not in contested])):
        result["metrics"][scope] = {}
        result["dependence"][scope] = {}
        result["false_acceptances_by_origin"][scope] = {}
        for group, subset in (("pooled", ids), ("original", [i for i in ids if i not in constructed]),
                              ("perturbed", [i for i in ids if i in constructed])):
            groups = {"ensemble": columns, **{c.removesuffix("_verdict"): [c] for c in columns}}
            values = {name: metrics(subset, final, verdicts, cols,
                                    policy if name == "ensemble" else "unanimous") for name, cols in groups.items()}
            singles = [name for name in groups if name != "ensemble"]
            if singles:
                best = min(singles, key=lambda name: (values[name]["false_acceptance_rate"]
                            if values[name]["false_acceptance_rate"] is not None else 1,
                            -(values[name]["accept_recall"] or 0)))
                for metric in ("false_acceptance_rate", "accept_recall"):
                    ensemble_value, single_value = values["ensemble"][metric], values[best][metric]
                    values["ensemble"][f"gain_vs_best_single_{metric}"] = (ensemble_value - single_value
                                                                               if ensemble_value is not None and single_value is not None else None)
                values["ensemble"]["best_single"] = best
            result["metrics"][scope][group] = values
            result["dependence"][scope][group] = dependence(subset, final, verdicts, columns)
            result["false_acceptances_by_origin"][scope][group] = {
                name: dict(Counter((constructed[i]["origin"] if i in constructed else "original")
                    for i in subset if final[i] != "supported" and decision(
                        [verdicts[i][c] for c in cols], policy if name == "ensemble" else "unanimous") == "accept"))
                for name, cols in groups.items()}
    return result


def fmt(value):
    return "—" if value is None else f"{value:.3f}" if isinstance(value, float) else str(value)


def render(result):
    three_labelers = "c" in result["labelers"]
    policy = result.get("policy", "unanimous")
    lines = ["# Claim evaluation", "", "## Decision policy", "",
             MAJORITY_POLICY if policy == "majority" else POLICY]
    if policy == "majority":
        lines.append("Single critic rows use the unanimous rule on one verdict.")
    lines.extend(["",
             "## Labelers", "", "| Labeler | Constructed binary accuracy | Constructed five-class accuracy | Original supported |",
             "|---|---:|---:|---:|"])
    for name in (("a", "b", "c") if three_labelers else ("a", "b")):
        row = result["labelers"][name]
        lines.append(f"| {name} | {fmt(row['constructed_binary_accuracy'])} | {fmt(row['constructed_five_class_accuracy'])} | {row['original_supported_count']} |")
    if three_labelers:
        for pair in ("ab", "ac", "bc"):
            lines.append(f"Cohen's kappa {pair.upper()} on original rows: {fmt(result['labelers'][f'kappa_{pair}'])}")
        lines.append(f"Three-way raw agreement on original rows: {fmt(result['labelers']['three_way_raw_agreement'])}")
    else:
        lines.extend(["", f"Cohen's kappa on original rows: {fmt(result['labelers']['kappa'])}"])
    lines.extend(["", "## Contested original rows", "",
                  "| ID | A | B | C | Final |" if three_labelers else "| ID | A | B | Final |",
                  "|---|---|---|---|---|" if three_labelers else "|---|---|---|---|"])
    for row in result["contested_detail"]:
        lines.append(f"| {row['id']} | {row['a']} | {row['b']} | {row['c']} | {row['final']} |" if three_labelers
                     else f"| {row['id']} | {row['a']} | {row['b']} | {row['final']} |")
    if "metrics" not in result:
        return "\n".join(lines) + "\n"
    lines.extend(["", "Undefined rates use — when their denominator is zero. Parser failure means any ERROR in the evaluated critic set.",
                  "Error dependence treats accepting a non-supported row or failing to accept a supported row as wrong.",
                  "Gain is ensemble minus the single critic with the lowest false acceptance rate; ties use higher accept recall."])
    for scope, groups in result["metrics"].items():
        lines.extend(["", f"## {scope.title()} rows", ""])
        for group, values in groups.items():
            lines.extend([f"### {group.title()}", "",
                          "| Critic | n | Accept precision | Accept recall | False acceptance rate | Abstention rate | Parser failure rate |",
                          "|---|---:|---:|---:|---:|---:|---:|"])
            for name, row in values.items():
                lines.append("| " + " | ".join([name] + [fmt(row[k]) for k in
                    ("n", "accept_precision", "accept_recall", "false_acceptance_rate", "abstention_rate", "parser_failure_rate")]) + " |")
            ensemble = values["ensemble"]
            lines.append(f"\nGain versus {ensemble.get('best_single', '—')}: false acceptance rate "
                         f"{fmt(ensemble.get('gain_vs_best_single_false_acceptance_rate'))}; "
                         f"accept recall {fmt(ensemble.get('gain_vs_best_single_accept_recall'))}.\n")
            lines.append("| Critic | False acceptances by origin |")
            lines.append("|---|---|")
            for name, origins in result["false_acceptances_by_origin"][scope][group].items():
                lines.append(f"| {name} | {', '.join(f'{k}: {v}' for k, v in sorted(origins.items())) or 'none'} |")
            dep = result["dependence"][scope][group]
            lines.append(f"\nBoth critics wrong on same row: {fmt(dep['both_wrong_rate'])}; error correlation: {fmt(dep['error_correlation'])}.\n")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verdicts", type=Path)
    parser.add_argument("--constructed", required=True, type=Path)
    parser.add_argument("--labels-a", required=True, type=Path)
    parser.add_argument("--labels-b", required=True, type=Path)
    parser.add_argument("--labels-c", type=Path)
    parser.add_argument("--critics", help="comma-separated critic names without _verdict")
    parser.add_argument("--policy", choices=("unanimous", "majority"), default="unanimous")
    parser.add_argument("--labels-only", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if not args.labels_only and not args.verdicts:
        parser.error("--verdicts is required unless --labels-only is set")
    report = render(evaluate(None if args.labels_only else args.verdicts,
                             args.constructed, args.labels_a, args.labels_b,
                             labels_c_path=args.labels_c,
                             critics=args.critics.split(",") if args.critics is not None else None,
                             policy=args.policy))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report)
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
