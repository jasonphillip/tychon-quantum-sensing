"""Low-level hardware links: KitLink (real silicon over ssh) and FakeKit (software).

Both expose the same minimal interface used by controller.Controller:
    wraw(addr, val) / rraw(addr) -> int        register access
    v250_check() -> dict                        run V250 inference probe
    latency_ms() -> float | None                ssh round-trip (None for fake)
    close()

KitLink wraps a single persistent `pid_ctl repl` ssh session (one process for the
whole server) with a lock so concurrent endpoints serialize, plus an M0-read guard
so the dashboard can never wedge the kit. Reconnects if the ssh process dies.
"""
from __future__ import annotations

import re
import subprocess
import threading
import time

from . import config
from .registers import (
    CSR_VERSION_EXPECT,
    OUTER_SECTOR_CLAMP_FRACTION,
    R_AXI_WRITE_COUNT,
    R_CSR_VERSION,
    R_ERROR_HIGH,
    R_ERROR_LOW,
    R_POST_CLAMP,
    R_U_AI,
    R_WATCHDOG,
    f_to_q16,
    is_m0,
    q16_to_f,
)


class M0AccessError(RuntimeError):
    """Raised if anything tries to touch the M0 gains slave (reads wedge a hart)."""


_OUT0_RE = re.compile(r"out\[0\].*?:\s*(-?[\d.]+)")
_ERRVAL_RE = re.compile(r"error_val=(\d+)")


class KitLink:
    """Persistent `pid_ctl repl` over ssh — real on-silicon access."""

    kind = "live"

    def __init__(self, host: str | None = None):
        self.host = host or config.KIT_HOST
        self.tool = config.PID_CTL
        self._lock = threading.RLock()
        self.proc: subprocess.Popen | None = None
        self._open()

    # -- repl lifecycle ----------------------------------------------------
    def _open(self) -> None:
        self.proc = subprocess.Popen(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
             self.host, self.tool, "repl"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )

    def _cmd(self, line: str) -> str:
        with self._lock:
            if self.proc is None or self.proc.poll() is not None:
                self._open()
            assert self.proc and self.proc.stdin and self.proc.stdout
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()
            return self.proc.stdout.readline().strip()

    # -- register access (with M0 guard) ----------------------------------
    def wraw(self, addr: int, val: int) -> None:
        if is_m0(addr):
            raise M0AccessError(f"refusing M0 write 0x{addr:08x} (gains slave is gated)")
        self._cmd(f"wraw 0x{addr:08x} 0x{val & 0xFFFFFFFF:08x}")

    def rraw(self, addr: int) -> int:
        if is_m0(addr):
            raise M0AccessError(f"refusing M0 read 0x{addr:08x} (would wedge a U54 hart)")
        out = self._cmd(f"r 0x{addr:08x}")
        # reply form: "0x60040844 = 0x0000abcd  (1.234)"
        try:
            return int(out.split("=")[1].split("(")[0].strip(), 16)
        except (IndexError, ValueError):
            raise RuntimeError(f"bad read reply: {out!r}")

    # -- V250 inference ----------------------------------------------------
    def v250_check(self) -> dict:
        """Run vbx_probe (RESULT + error_val) and vnnx_smoke (out[0]) on the kit."""
        probe = self._ssh_run(f"cd {config.BRINGUP} && ./vbx_probe {config.V250_MODEL} 2>&1")
        smoke = self._ssh_run(f"cd {config.BRINGUP} && ./vnnx_smoke 2>&1")
        result = "INFERENCE COMPLETED" if "INFERENCE COMPLETED" in probe else "UNKNOWN"
        m_err = _ERRVAL_RE.search(probe)
        m_out = _OUT0_RE.search(smoke)
        return {
            "ok": result == "INFERENCE COMPLETED",
            "result": result,
            "error_val": int(m_err.group(1)) if m_err else None,
            "out0": float(m_out.group(1)) if m_out else None,
            "model": config.V250_MODEL,
            "simulated": False,
            "raw": (probe.strip().splitlines()[-6:] + smoke.strip().splitlines()[-2:]),
        }

    def _ssh_run(self, remote_cmd: str) -> str:
        try:
            r = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                 self.host, remote_cmd],
                capture_output=True, text=True, timeout=config.SSH_TIMEOUT,
            )
            return r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            return "ERROR: ssh timeout"

    # -- misc --------------------------------------------------------------
    def latency_ms(self) -> float | None:
        t0 = time.time()
        try:
            self.rraw(R_CSR_VERSION)
            return round((time.time() - t0) * 1000.0, 1)
        except Exception:
            return None

    def close(self) -> None:
        try:
            self._cmd("q")
            if self.proc:
                self.proc.wait(timeout=5)
        except Exception:
            if self.proc:
                self.proc.kill()


class FakeKit:
    """Dry-run software model: fabric PID + sector clamp + watchdog, in software.

    Ported from rung_g_replay.FakeKit, extended to honor M1 shadow-gain
    write/readback (bit-exact, like real M1) and a canned V250 result, so the
    dashboard behaves identically with no board attached.
    """

    kind = "dryrun"

    def __init__(self, kp=0.8, ki=0.05, kd=0.02):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.integ = 0.0
        self.prev_err = 0.0
        self.error = 0.0
        self.u_ai = 0.0
        self.write_count = 0
        self.wd_timeout = 0
        self._elo = 0
        self._regs: dict[int, int] = {}   # shadow-gain store (bit-exact readback)

    def wraw(self, addr: int, val: int) -> None:
        self.write_count += 1
        val &= 0xFFFFFFFF
        if addr == R_ERROR_LOW:
            self._elo = val
        elif addr == R_ERROR_HIGH:
            raw = (val << 32) | self._elo
            self.error = (raw - (1 << 64) if raw & (1 << 63) else raw) / (1 << 30)
        elif addr == R_U_AI:
            self.u_ai = q16_to_f(val)
        else:
            self._regs[addr] = val   # shadow gains et al.

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
        return self._regs.get(addr, 0)

    def v250_check(self) -> dict:
        return {
            "ok": True, "result": "INFERENCE COMPLETED", "error_val": 0,
            "out0": -2.9506, "model": config.V250_MODEL, "simulated": True,
            "raw": ["(dry-run) canned V250 result: out[0]=-2.9506, error_val=0"],
        }

    def latency_ms(self) -> float | None:
        return None

    def close(self) -> None:
        pass
