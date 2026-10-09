#!/usr/bin/env python3
"""Grade one watchdog observer/control CSV pair against the board test plan."""
import argparse
import csv
import math
import re
from pathlib import Path

Q = 1 / 65536


def rows(path):
    with open(path, newline="", encoding="utf-8") as stream:
        lines = [line for line in stream if not line.startswith("#")]
    return list(csv.DictReader(lines))


def integer(row, key):
    return int(row[key], 0)


def load(path, control=False):
    result = []
    for row in rows(path):
        value = {"t": integer(row, "t_ns"), "post": integer(row, "post_clamp_q16"),
                 "wd": integer(row, "wd_raw"), "trip": integer(row, "wd_trip_count"),
                 "writes": integer(row, "axi_write_count")}
        if control:
            value.update(idx=integer(row, "idx"), ai=float(row["u_ai"]),
                         phase=row["mode_phase"], overrun=integer(row, "overrun_ns"))
        else:
            value["gap"] = integer(row, "poll_gap_max_ns")
        result.append(value)
    if not result or any(b["t"] < a["t"] for a, b in zip(result, result[1:])):
        raise ValueError(f"empty or non-monotonic timestamps: {path}")
    return result


def settings(path):
    with open(path, encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("#"):
                return {key: float(value) for key, value in
                        re.findall(r"\b(out_min|out_max|inner_clamp)=([-+]?\d+(?:\.\d+)?)", line)}
    return {}


def changes(observer):
    clear = None
    edges = []
    for before, after in zip(observer, observer[1:]):
        if before["wd"] & 1 and not after["wd"] & 1:
            clear = after
        if not before["wd"] & 1 and after["wd"] & 1:
            edges.append({"rise": after, "clear": clear, "before": before, "fall": None})
        if before["wd"] & 1 and not after["wd"] & 1 and edges and edges[-1]["fall"] is None:
            edges[-1]["fall"] = after
    return edges


def grade(observer, control, scenario, period_us, limits):
    edges = changes(observer)
    events, grades = [], []
    previous = {row["idx"]: control[i - 1] for i, row in enumerate(control) if i}
    def add(rep, criterion, state, detail):
        grades.append((rep, criterion, state, detail))
    if not edges:
        add(0, "capture", "FAIL", "No timeout rise observed")
        return events, grades
    for rep, edge in enumerate(edges, 1):
        rise, clear, fall = edge["rise"], edge["clear"], edge["fall"]
        next_rise = edges[rep]["rise"]["t"] if rep < len(edges) else math.inf
        segment = [r for r in control if rise["t"] <= r["t"] < next_rise]
        prior = [r for r in control if r["t"] < rise["t"]]
        first = segment[0] if segment else None
        first_visible = next((r for r in segment if r["wd"] & 1), None)
        fallback = None
        recovery = None
        if scenario != "a":
            fallback = next((row for row in segment if row["idx"] in previous and
                             abs(row["post"] - previous[row["idx"]]["post"]) <= 1 and
                             abs(row["ai"] - previous[row["idx"]]["ai"]) > Q), None)
            if fallback:
                recovery = next((r for r in segment if r["idx"] > fallback["idx"] and
                                 abs(r["post"] - previous[r["idx"]]["post"]) > 1), None)
        trip_ns = rise["t"] - clear["t"] if clear else None
        high_ns = fall["t"] - rise["t"] if fall else None
        rise_latency_ns = fallback["t"] - rise["t"] if fallback else None
        latency_ns = (fallback["t"] - first_visible["t"] if scenario == "c0" and fallback and first_visible
                      else rise_latency_ns if scenario != "c0" else None)
        flat_count = recovery["idx"] - fallback["idx"] if fallback and recovery else None
        step = abs(recovery["post"] - previous[recovery["idx"]]["post"]) * Q if recovery else None
        write_delta = ((recovery["writes"] - fallback["writes"]) & 0xffffffff) if recovery and fallback else None
        write_updates = write_delta // 3 if write_delta is not None and write_delta % 3 == 0 else None
        trip_delta = (rise["trip"] - edge["before"]["trip"]) & 0x7fffffff
        poll_reject = any(r["gap"] > 50000 for r in observer if clear and clear["t"] <= r["t"] <= rise["t"])
        row = dict(repetition=rep, rise_t_ns=rise["t"], clear_t_ns=clear["t"] if clear else "",
                   trip_ns=trip_ns if trip_ns is not None else "", high_ns=high_ns if high_ns is not None else "",
                   first_core_visible_idx=first_visible["idx"] if first_visible else "",
                   fallback_idx=fallback["idx"] if fallback else "",
                   fallback_latency_ns=latency_ns if latency_ns is not None else "",
                   rise_to_fallback_ns=rise_latency_ns if rise_latency_ns is not None else "",
                   recovery_idx=recovery["idx"] if recovery else "", flat_updates=flat_count if flat_count is not None else "",
                   recovery_step=step if step is not None else "", write_updates=write_updates if write_updates is not None else "",
                   trip_count_delta=trip_delta, poll_rejected=int(poll_reject),
                   recovery_seconds=(recovery["t"] - fallback["t"]) / 1e9 if recovery else "")
        events.append(row)
        trip_ok = trip_ns is not None and 1_950_000 <= trip_ns <= 2_050_000
        if scenario in ("a", "b1", "b2"):
            add(rep, "A1" if scenario == "a" else "B1", "REJECT" if poll_reject else "PASS" if trip_ok else "FAIL",
                f"clear-to-rise={trip_ns} ns; poll gap over 50 us={poll_reject}")
        if scenario == "a":
            add(rep, "A2", "PASS" if trip_delta == 1 else "FAIL", f"trip delta={trip_delta}")
            if first and prior:
                paused = [r for r in observer if prior[-1]["t"] <= r["t"] < first["t"]]
                frozen_writes = bool(paused) and all(r["writes"] == paused[0]["writes"] for r in paused)
                frozen_post = bool(paused) and all(r["post"] == paused[0]["post"] for r in paused)
                hold_ns = first["t"] - prior[-1]["t"]
                add(rep, "A3", "PASS" if frozen_writes else "FAIL", f"AXI count frozen={frozen_writes}")
                add(rep, "A4", "OBSERVE" if frozen_post else "FAIL", f"actuator held={frozen_post}; hold_ns={hold_ns}; limit unset")
            else:
                add(rep, "A3", "FAIL", "No control rows bracketing pause")
                add(rep, "A4", "OBSERVE", "Hold unavailable; limit unset")
            continue
        if scenario in ("c0", "c1"):
            valid = high_ns is not None and abs(high_ns - 500_000) <= 100_000
            add(rep, "C1", "PASS" if valid else "REJECT", f"high_ns={high_ns}; expected 500000 +/- 100000")
            add(rep, "C2", "PASS" if valid and trip_delta == 1 else "FAIL" if valid else "REJECT", f"trip delta={trip_delta}")
            if not valid:
                continue
        if scenario in ("b1", "b2", "c0"):
            end_to_end = trip_ns + rise_latency_ns if trip_ns is not None and rise_latency_ns is not None else None
            add(rep, "B2", "PASS" if latency_ns is not None and 0 <= latency_ns <= 500_000 and
                end_to_end is not None and end_to_end <= 2_500_000 else "FAIL",
                f"fallback_latency_ns={latency_ns}; end-to-end_ns={end_to_end}")
            fallback_delta = abs(fallback["post"] - previous[fallback["idx"]]["post"]) * Q if fallback else None
            add(rep, "B3", "PASS" if fallback_delta is not None and fallback_delta <= .001 else "FAIL", f"fallback_step={fallback_delta}")
            if scenario in ("b1", "c0"):
                flat = fallback is not None and all(abs(r["post"] - previous[r["idx"]]["post"]) <= 1
                                                    for r in segment if r["idx"] > fallback["idx"] and
                                                    (scenario == "b1" or not recovery or r["idx"] < recovery["idx"]))
                add(rep, "B4", "PASS" if flat else "FAIL", f"sustained flat={flat}")
            if scenario in ("b2", "c0"):
                applicable = recovery is not None and not recovery["wd"] & 1
                add(rep, "B5", "PASS" if applicable and flat_count == 1000 and write_updates == 1000 else
                    "N/A" if recovery and recovery["wd"] & 1 else "FAIL",
                    f"flat_updates={flat_count}; axi_write_count/3={write_updates}")
                add(rep, "B6", "PASS" if applicable and flat_count == 1000 else "FAIL",
                    f"recovery_seconds={row['recovery_seconds']}; nominal_seconds={1000 * period_us / 1e6}")
                add(rep, "B7", "PASS" if step is not None and step <= .001 else "FAIL", f"recovery_step={step}")
            low = limits.get("out_min", -1); high = limits.get("out_max", 1)
            bounded = all(abs(r["ai"]) <= .09 + 1e-9 and low - Q <= r["post"] * Q <= high + Q for r in control)
            add(rep, "B8", "PASS" if bounded else "FAIL", f"AI <= 0.09 and actuator in [{low}, {high}]={bounded}")
        if scenario == "c1":
            tracked = not fallback and any(abs(r["post"] - previous[r["idx"]]["post"]) > 1
                                           for r in segment if r["idx"] > (first["idx"] if first else math.inf))
            flat_rows = [r for r in segment if fallback and r["idx"] >= fallback["idx"] and
                         (not recovery or r["idx"] < recovery["idx"])]
            low_at_starts = bool(fall) and all(not r["wd"] & 1 for r in segment)
            sustained = len(flat_rows) >= 1000 and all(abs(r["post"] - previous[r["idx"]]["post"]) <= 1 for r in flat_rows)
            add(rep, "C3", "PASS" if fallback and sustained and low_at_starts else "FAIL",
                f"flat_updates={len(flat_rows)}; actuator_tracking={tracked}; timeout_low_at_starts={low_at_starts}")
        if scenario == "c0":
            needed = [g for g in grades if g[0] == rep and g[1] in ("B2", "B3", "B4", "B5")]
            add(rep, "C4", "PASS" if len(needed) == 4 and all(g[2] == "PASS" for g in needed) else "FAIL",
                "requires B2 through B5; B4 checks flatness through recovery")
    return events, grades


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("observer", type=Path)
    parser.add_argument("control", type=Path)
    parser.add_argument("--scenario", required=True, choices=("a", "b1", "b2", "c0", "c1"))
    parser.add_argument("--period-us", required=True, type=int)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    if args.period_us <= 0: parser.error("--period-us must be positive")
    events, grades = grade(load(args.observer), load(args.control, True), args.scenario,
                           args.period_us, settings(args.control))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "events.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(events[0]) if events else ["repetition"])
        writer.writeheader(); writer.writerows(events)
    with (args.out_dir / "criteria.md").open("w", encoding="utf-8") as stream:
        stream.write(f"# Watchdog fallback: {args.scenario}\n\n| Repetition | Criterion | Result | Evidence |\n|---:|---|---|---|\n")
        for rep, criterion, state, detail in grades:
            stream.write(f"| {rep} | {criterion} | {state} | {detail} |\n")
        stream.write(f"\nRejected repetitions: {len(set(rep for rep, _, state, _ in grades if state == 'REJECT'))}\n")
    print(f"events={len(events)} criteria={len(grades)} failures={sum(g[2] == 'FAIL' for g in grades)}")


if __name__ == "__main__":
    main()
