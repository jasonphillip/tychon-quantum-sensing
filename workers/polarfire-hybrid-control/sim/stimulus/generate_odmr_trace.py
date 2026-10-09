#!/usr/bin/env python3
"""Generate a representative ODMR-PID activity trace for SmartPower VCD ingestion.

Output: sim/stimulus/odmr_representative_trace.csv

CSV columns (one row per simulator clock cycle when consumed by
sim/modelsim_pid_workload.do):
  cycle             — int, monotonically increasing
  error_hz          — float, frequency-domain detuning error fed to nv_pid_top
                      (range ±5000 Hz, covering follow-on operating envelope)
  u_ai_volts        — float, AI feedforward output in actuator-domain volts
                      (range [-0.225, +0.225] within outer sector clamp)
  ai_wd_timeout     — int, 0/1, the ai_watchdog_timeout boolean

The trace is engineered to exercise:
  - steady-state at low and zero error (low toggle activity)
  - sector-clamp engagement at the boundary (u_AI = ±0.225 V)
  - high-amplitude error ramps (slew limiter engages)
  - watchdog trip + bumpless transfer (state-change activity in integrator)
  - recovery phase (transient settling)

This is a synthetic stand-in for an instrumented bench trace. Replace with
captured ODMR data once available; the workload-driven SmartPower workflow
is independent of the trace's provenance.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

DEFAULT_OUT = Path(__file__).resolve().parent / "odmr_representative_trace.csv"


def generate(out_path: Path, total_cycles: int = 1000) -> None:
    rows: list[tuple[int, float, float, int]] = []

    # Phase boundaries (cumulative).
    phases = [
        ("warmup",        200, _phase_warmup),
        ("steady_high",   200, _phase_steady_high),
        ("watchdog_trip", 300, _phase_watchdog_trip),
        ("recovery",      200, _phase_recovery),
        ("zero_error",    100, _phase_zero_error),
    ]
    cycle = 0
    for _name, count, fn in phases:
        for k in range(count):
            err, u_ai, wd = fn(k, count)
            rows.append((cycle, err, u_ai, wd))
            cycle += 1
        if cycle >= total_cycles:
            break

    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cycle", "error_hz", "u_ai_volts", "ai_wd_timeout"])
        for row in rows:
            w.writerow([row[0], f"{row[1]:.6f}", f"{row[2]:.6f}", row[3]])

    print(f"wrote {len(rows)} rows -> {out_path}")


def _phase_warmup(k: int, count: int) -> tuple[float, float, int]:
    """Linear ramp from 100 Hz to 1000 Hz; modest u_AI."""
    err = 100.0 + (1000.0 - 100.0) * k / (count - 1)
    u_ai = 0.10
    return err, u_ai, 0


def _phase_steady_high(k: int, count: int) -> tuple[float, float, int]:
    """Sinusoidal ±5000 Hz error, u_AI riding the sector-clamp boundary."""
    err = 5000.0 * math.sin(2.0 * math.pi * k / count * 4.0)  # 4 cycles per phase
    # u_AI alternates between +0.225 and -0.225 across each cycle.
    u_ai = 0.225 * math.copysign(1.0, math.sin(2.0 * math.pi * k / count * 4.0))
    return err, u_ai, 0


def _phase_watchdog_trip(k: int, count: int) -> tuple[float, float, int]:
    """Watchdog trip + bumpless transfer: error stays high but u_AI = 0
    while ai_watchdog_timeout asserts. The integrator absorbs the prior u_AI."""
    err = 5000.0
    u_ai = 0.0
    wd = 1
    return err, u_ai, wd


def _phase_recovery(k: int, count: int) -> tuple[float, float, int]:
    """Linear ramp from 5000 Hz back to 100 Hz; u_AI re-engages at 0.10 V."""
    err = 5000.0 - (5000.0 - 100.0) * k / (count - 1)
    u_ai = 0.10
    return err, u_ai, 0


def _phase_zero_error(k: int, count: int) -> tuple[float, float, int]:
    """Steady state: zero error, zero u_AI. Low activity baseline."""
    return 0.0, 0.0, 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT,
                   help=f"output CSV path (default: {DEFAULT_OUT})")
    p.add_argument("-n", "--total-cycles", type=int, default=1000,
                   help="total cycles to generate (default: 1000)")
    args = p.parse_args()
    generate(args.output, args.total_cycles)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
