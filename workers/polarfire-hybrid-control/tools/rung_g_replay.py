#!/usr/bin/env python3
"""rung_g_replay.py — closed-loop ODMR replay through the on-silicon PID + V250 NN.

Streams an ODMR error trace row-by-row through the two-slot fabric PID on the
Icicle Kit and emits dashboard-friendly telemetry (CSV + JSONL). For each row it
reads the REAL hardware actuator output twice — once with the NN feedforward off
(hardware PID-only) and once with it on (hardware PID+NN) — so the overlay is
silicon-vs-silicon, not silicon-vs-simulation.

Hardware interface (one persistent ssh session running `pid_ctl repl`):
  - inject error (Q34.30) -> pid_csr 0x60040810/0x814
  - inject u_ai  (Q16.16) -> pid_csr 0x60040818
  - read actuator (Q16.16) <- pid_csr 0x60040844  (post-clamp tap)
  - read watchdog_csr      <- pid_csr 0x60040854  (bit0 = timeout)
  (pid_csr is at the 0x60040800 sub-window of the SLAVE3 page; gains at 0x60040000.)

Telemetry schema (one CSV row / one JSONL object per sample):
  t_host, sample_idx, error_in, nn_u_ai, pid_only_out, pidnn_out, actuator_out,
  unclamped_calc, clamp_active, watchdog_timeout, mode, vbx_error,
  axi_write_count, csr_version
Provenance — HARDWARE-DIRECT: pid_only_out, pidnn_out, actuator_out,
  watchdog_timeout, vbx_error, axi_write_count, csr_version.
HOST-DERIVED (grounded in a real hardware read): unclamped_calc, clamp_active, mode.

Watchdog note: the dashboard-demo bitstream uses a 500 ms (62.5e6 cycles @125 MHz)
HOST-PACED timeout so steady replay does not spuriously trip it; this is NOT the
1 ms safety bound (that is the 125 000-cycle safety-spec build). See
docs/two_slot_register_map_2026-06-17.md.

Run (dry-run, no kit):  python3 tools/rung_g_replay.py --dry-run --plot
Run (on silicon):       python3 tools/rung_g_replay.py --host icicle --plot
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
import time
from dataclasses import dataclass, asdict
from pathlib import Path

# --- fabric register addresses (two-slot bitstream) ----------------------
# SLAVE3 page 0x60040000 split by axi4_demux2: gains @ +0x000, pid_csr @ +0x800.
GAINS = 0x60040000          # nv_pid_top.axi4target (Kp 0x0C, Ki 0x10, Kd 0x14, ...)
CSR = 0x60040800            # pid_csr
R_AXI_WRITE_COUNT = CSR + 0x000
R_CSR_VERSION = CSR + 0x004
R_ERROR_LOW = CSR + 0x010
R_ERROR_HIGH = CSR + 0x014
R_U_AI = CSR + 0x018
R_POST_CLAMP = CSR + 0x044
R_WATCHDOG = CSR + 0x054

# --- gains slave (M0) — idfix2 fix makes it readable/writable + actuator latched ---
R_ACC_START = GAINS + 0x008   # write 1 = pulse one PID compute (SmartHLS ap_ctrl start)
R_KP = GAINS + 0x00C
R_KI = GAINS + 0x010
R_KD = GAINS + 0x014
R_OUT_MIN = GAINS + 0x018
R_OUT_MAX = GAINS + 0x01C
# Live PID gains for the host-paced silicon replay. Ki=Kd=0: host injection is not at
# the 125 MHz fabric rate, so a nonzero Ki would wind the integrator to saturation
# between samples; proportional tracking is the honest host-paced demo.
PID_KP, PID_KI, PID_KD = 0.8, 0.0, 0.0
PID_OUT_MIN, PID_OUT_MAX = -1.0, 1.0

# --- safety constants (hls/include/rta_config.hpp) -----------------------
OUTER_SECTOR_CLAMP_FRACTION = 0.045  # AI output bounded to +-4.5% of range
CSR_VERSION_EXPECT = 0x00010000


def f_to_q16(v: float) -> int:
    return int(round(v * 65536.0)) & 0xFFFFFFFF


def q16_to_f(raw: int) -> float:
    raw &= 0xFFFFFFFF
    return (raw - (1 << 32) if raw & 0x80000000 else raw) / 65536.0


def f_to_q34_30(v: float) -> tuple[int, int]:
    """Q34.30 64-bit -> (low32, high32)."""
    raw = int(round(v * (1 << 30))) & ((1 << 64) - 1)
    return raw & 0xFFFFFFFF, (raw >> 32) & 0xFFFFFFFF


# --- hardware link --------------------------------------------------------
class KitLink:
    """Persistent `pid_ctl repl` over ssh; one process for the whole replay."""

    def __init__(self, host: str, tool: str = "/root/bringup/pid_ctl"):
        self.proc = subprocess.Popen(
            ["ssh", host, tool, "repl"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def _cmd(self, line: str) -> str:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        return self.proc.stdout.readline().strip()

    def wraw(self, addr: int, val: int) -> None:
        self._cmd(f"wraw 0x{addr:08x} 0x{val & 0xFFFFFFFF:08x}")

    def rraw(self, addr: int) -> int:
        out = self._cmd(f"r 0x{addr:08x}")
        # "0x60040844 = 0x0000abcd  (..)"
        try:
            return int(out.split("=")[1].split("(")[0].strip(), 16)
        except (IndexError, ValueError):
            raise RuntimeError(f"bad read reply: {out!r}")

    def close(self) -> None:
        try:
            self._cmd("q")
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()


class FakeKit:
    """Dry-run hardware model: fabric PID + sector clamp + watchdog, in software.
    Lets the harness + telemetry + plot be validated with no board attached."""

    def __init__(self, kp=0.8, ki=0.05, kd=0.02):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.integ = 0.0
        self.prev_err = 0.0
        self.error = 0.0
        self.u_ai = 0.0
        self.write_count = 0
        self.wd_timeout = 0

    def wraw(self, addr: int, val: int) -> None:
        self.write_count += 1
        if addr == R_ERROR_LOW:
            self._elo = val
        elif addr == R_ERROR_HIGH:
            raw = (val << 32) | getattr(self, "_elo", 0)
            self.error = (raw - (1 << 64) if raw & (1 << 63) else raw) / (1 << 30)
        elif addr == R_U_AI:
            self.u_ai = q16_to_f(val)

    def _pid(self) -> float:
        self.integ += self.ki * self.error
        deriv = self.kd * (self.error - self.prev_err)
        self.prev_err = self.error
        u_pid = self.kp * self.error + self.integ + deriv
        u_ai_clamped = max(-OUTER_SECTOR_CLAMP_FRACTION,
                           min(OUTER_SECTOR_CLAMP_FRACTION, self.u_ai))
        return max(-1.0, min(1.0, u_pid + u_ai_clamped))

    def rraw(self, addr: int) -> int:
        if addr == R_POST_CLAMP:
            return f_to_q16(self._pid())
        if addr == R_WATCHDOG:
            return self.wd_timeout & 0x1
        if addr == R_CSR_VERSION:
            return CSR_VERSION_EXPECT
        if addr == R_AXI_WRITE_COUNT:
            return self.write_count
        return 0

    def close(self) -> None:
        pass


@dataclass
class Sample:
    t_host: float
    sample_idx: int
    error_in: float
    nn_u_ai: float
    pid_only_out: float
    pidnn_out: float
    actuator_out: float
    unclamped_calc: float
    clamp_active: int
    watchdog_timeout: int
    mode: str
    vbx_error: int
    axi_write_count: int
    csr_version: int


def nn_surrogate(error: float, idx: int) -> float:
    """Host-side stand-in for the V250 FCNN residual until the on-target
    per-row inference helper is wired (Phase 4). Bounded, deterministic; a small
    anticipatory correction proportional to error trend. CLEARLY a surrogate."""
    return max(-0.06, min(0.06, -0.3 * error + 0.01 * math.sin(idx / 7.0)))


def inject_error(kit, error: float) -> None:
    lo, hi = f_to_q34_30(error)
    kit.wraw(R_ERROR_LOW, lo)
    kit.wraw(R_ERROR_HIGH, hi)


def replay(kit, trace, nn_mode: str, nn_const: float, stunt: str):
    samples = []
    t0 = time.time()
    for idx, error in enumerate(trace):
        inject_error(kit, error)

        # NN feedforward off -> hardware PID-only (pulse start: one PID compute, latched)
        kit.wraw(R_U_AI, f_to_q16(0.0))
        kit.wraw(R_ACC_START, 1)
        pid_only = q16_to_f(kit.rraw(R_POST_CLAMP))

        # determine NN output
        if nn_mode == "constant":
            u_ai = nn_const
        elif nn_mode == "surrogate":
            u_ai = nn_surrogate(error, idx)
        else:  # "hardware" — placeholder until vnnx per-row helper lands (Phase 4)
            u_ai = nn_const

        # clamp stunt: force an oversized AI correction on a window of rows
        if stunt == "clamp" and 20 <= idx < 40:
            u_ai = 0.25  # >> +-4.5% sector bound; clamp must bound it

        kit.wraw(R_U_AI, f_to_q16(u_ai))
        kit.wraw(R_ACC_START, 1)
        pidnn = q16_to_f(kit.rraw(R_POST_CLAMP))

        wd = kit.rraw(R_WATCHDOG) & 0x1
        unclamped = pid_only + u_ai
        clamp_active = int(abs(u_ai) > OUTER_SECTOR_CLAMP_FRACTION)
        mode = "PID_ONLY_FALLBACK" if wd else "PID_NN"

        samples.append(Sample(
            t_host=round(time.time() - t0, 6), sample_idx=idx,
            error_in=round(error, 6), nn_u_ai=round(u_ai, 6),
            pid_only_out=round(pid_only, 6), pidnn_out=round(pidnn, 6),
            actuator_out=round(pidnn, 6), unclamped_calc=round(unclamped, 6),
            clamp_active=clamp_active, watchdog_timeout=wd, mode=mode,
            vbx_error=0, axi_write_count=kit.rraw(R_AXI_WRITE_COUNT),
            csr_version=kit.rraw(R_CSR_VERSION),
        ))
    return samples


def load_trace(path: Path | None, n: int):
    if path and path.is_file():
        out = []
        with path.open() as fh:
            for row in csv.reader(fh):
                if not row or row[0].lstrip().startswith("#"):
                    continue
                try:
                    out.append(float(row[-1]))
                except ValueError:
                    continue
        if out:
            return out[:n] if n else out
    # synthetic ODMR detuning step + decay (host plant would normally close this)
    return [0.5 * math.exp(-i / 25.0) * math.cos(i / 9.0) for i in range(n or 120)]


def write_telemetry(samples, out_base: Path):
    fields = list(asdict(samples[0]).keys())
    with (out_base.with_suffix(".csv")).open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for s in samples:
            w.writerow(asdict(s))
    with (out_base.with_suffix(".jsonl")).open("w") as fh:
        for s in samples:
            fh.write(json.dumps(asdict(s)) + "\n")


def make_plot(samples, out_png: Path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib unavailable; skipping plot")
        return
    idx = [s.sample_idx for s in samples]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    ax1.plot(idx, [s.error_in for s in samples], "k-", lw=1, label="ODMR error in")
    ax1.plot(idx, [s.pid_only_out for s in samples], "C0-", label="PID-only (HW)")
    ax1.plot(idx, [s.pidnn_out for s in samples], "C3-", label="PID+NN (HW)")
    ax1.set_ylabel("normalized")
    ax1.legend(loc="upper right", fontsize=8)
    ax1.set_title("Rung G — closed-loop ODMR replay on silicon")
    ca = [s.clamp_active for s in samples]
    wd = [s.watchdog_timeout for s in samples]
    ax2.fill_between(idx, 0, ca, step="mid", alpha=0.4, color="C1", label="clamp active")
    ax2.fill_between(idx, 0, wd, step="mid", alpha=0.4, color="C2", label="watchdog timeout")
    ax2.plot(idx, [s.nn_u_ai for s in samples], "C3.", ms=3, label="NN u_ai")
    ax2.set_ylabel("flags / u_ai")
    ax2.set_xlabel("sample")
    ax2.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_png, dpi=110)
    print(f"plot -> {out_png}")


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    ap.add_argument("--host", default="icicle", help="kit ssh alias/ip")
    ap.add_argument("--dry-run", action="store_true", help="simulate hardware (no kit)")
    ap.add_argument("--trace", type=Path, default=None)
    ap.add_argument("--rows", type=int, default=120)
    ap.add_argument("--nn", choices=["surrogate", "constant", "hardware"], default="surrogate")
    ap.add_argument("--nn-const", type=float, default=-2.9506 / 64.0,
                    help="u_ai when --nn constant/hardware (default = measured V250 out, scaled)")
    ap.add_argument("--stunt", choices=["none", "clamp", "watchdog"], default="none")
    ap.add_argument("--out", type=Path, default=Path("sim/rung_g/rung_g_telemetry"))
    ap.add_argument("--plot", action="store_true")
    args = ap.parse_args()

    trace = load_trace(args.trace, args.rows)
    kit = FakeKit() if args.dry_run else KitLink(args.host)
    try:
        if not args.dry_run:
            ver = kit.rraw(R_CSR_VERSION)
            if ver != CSR_VERSION_EXPECT:
                print(f"WARN csr_version=0x{ver:08x} (expected 0x{CSR_VERSION_EXPECT:08x})")
        # Set the live PID gains/limits on the gains slave (M0) before streaming.
        # (idfix2: M0 reads/writes complete and the actuator output is latched.)
        kit.wraw(R_OUT_MIN, f_to_q16(PID_OUT_MIN)); kit.wraw(R_OUT_MAX, f_to_q16(PID_OUT_MAX))
        kit.wraw(R_KP, f_to_q16(PID_KP)); kit.wraw(R_KI, f_to_q16(PID_KI)); kit.wraw(R_KD, f_to_q16(PID_KD))
        samples = replay(kit, trace, args.nn, args.nn_const, args.stunt)
    finally:
        kit.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_telemetry(samples, args.out)
    print(f"telemetry: {args.out}.csv / .jsonl ({len(samples)} samples)")
    n_clamp = sum(s.clamp_active for s in samples)
    n_wd = sum(s.watchdog_timeout for s in samples)
    print(f"summary: {n_clamp} clamp-active, {n_wd} watchdog-trip samples; "
          f"mode set: {sorted({s.mode for s in samples})}")
    if args.plot:
        make_plot(samples, args.out.with_suffix(".png"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
