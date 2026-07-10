"""Low-level hardware links: KitLink (real silicon over ssh) and FakeKit (software).

Both expose the same minimal interface used by controller.Controller:
    wraw(addr, val) / rraw(addr) -> int        register access
    v250_check() -> dict                        run V250 inference probe
    latency_ms() -> float | None                ssh round-trip (None for fake)
    close()

KitLink wraps a single persistent `pid_ctl repl` ssh session (one process for the
whole server) with a lock so concurrent endpoints serialize. M0 reads are always
blocked; idfix2-only M0 writes are allowlisted and require explicit environment
opt-in. Reconnects if the ssh process dies.
"""
from __future__ import annotations

import csv
import json
import re
import shlex
import subprocess
import threading
import time

from . import config
from .registers import (
    CSR_VERSION_EXPECT,
    OUTER_SECTOR_CLAMP_FRACTION,
    M0_WRITE_ALLOWLIST,
    R_ACC_START,
    R_AXI_WRITE_COUNT,
    R_CSR_VERSION,
    R_ERROR_HIGH,
    R_ERROR_LOW,
    R_KD,
    R_KI,
    R_KP,
    R_OUT_MAX,
    R_OUT_MIN,
    R_POST_CLAMP,
    R_U_AI,
    R_WATCHDOG,
    f_to_q16,
    is_m0,
    q16_to_f,
)


class M0AccessError(RuntimeError):
    """Raised if unsafe code tries to touch the M0 gains/control slave."""


_OUT0_RE = re.compile(r"out\[0\].*?:\s*(-?[\d.]+)")
_ERRVAL_RE = re.compile(r"error_val=(\d+)")


def _q(s: str) -> str:
    return shlex.quote(str(s))


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
    def m0_gate(self) -> tuple[bool, str]:
        if config.KIT_BITSTREAM != "idfix2":
            return False, "set KIT_BITSTREAM=idfix2 to enable idfix2-only M0 writes"
        if not config.ALLOW_IDFIX2_M0:
            return False, "set ALLOW_IDFIX2_M0=1 after idfix2 smoke verification"
        return True, "idfix2 M0 write allowlist enabled"

    def wraw(self, addr: int, val: int) -> None:
        if is_m0(addr):
            ok, reason = self.m0_gate()
            if not ok:
                raise M0AccessError(f"refusing M0 write 0x{addr:08x}: {reason}")
            if addr not in M0_WRITE_ALLOWLIST:
                raise M0AccessError(f"refusing M0 write 0x{addr:08x}: not in idfix2 allowlist")
        self._cmd(f"wraw 0x{addr:08x} 0x{val & 0xFFFFFFFF:08x}")

    def rraw(self, addr: int) -> int:
        if is_m0(addr):
            raise M0AccessError(f"refusing M0 read 0x{addr:08x}; dashboard only reads M1 taps")
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
        smoke = self._ssh_run(f"cd {config.BRINGUP} && ./vnnx_smoke {config.V250_MODEL} 2>&1")
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

    def v250_pid_loop(self, rows: int, warmup: int = 2):
        """Stream CSV rows from the on-kit V250 -> u_ai -> PID helper."""
        cmd = (
            f"cd {config.BRINGUP} && {config.V250_PID_LOOP} "
            f"{config.V250_MODEL} {int(rows)} {int(warmup)} "
            f"{config.V250_INPUT_CSV} 2>&1"
        )
        with self._lock:
            proc = subprocess.Popen(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                 self.host, cmd],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
            )
            header: list[str] | None = None
            raw_tail: list[str] = []
            try:
                assert proc.stdout
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    raw_tail = (raw_tail + [line])[-8:]
                    if line.startswith("row,"):
                        header = next(csv.reader([line]))
                        continue
                    if header and line[0].isdigit():
                        vals = next(csv.reader([line]))
                        if len(vals) == len(header):
                            yield dict(zip(header, vals))
                rc = proc.wait(timeout=5)
                if rc != 0:
                    raise RuntimeError("v250_pid_loop failed: " + " | ".join(raw_tail))
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()

    def v250_loop_status(self) -> dict:
        """Read the daemon pid/state files from the kit."""
        cmd = (
            f"pid=$(cat {_q(config.V250_LOOP_PID)} 2>/dev/null || true); "
            "alive=0; "
            'if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then alive=1; fi; '
            'printf "__ALIVE__=%s\\n" "$alive"; '
            'printf "__PID__=%s\\n" "$pid"; '
            f"if [ -s {_q(config.V250_LOOP_STATE)} ]; then cat {_q(config.V250_LOOP_STATE)}; fi"
        )
        out = self._ssh_run(cmd)
        alive = False
        pid: int | None = None
        state = None
        raw_lines = [ln for ln in out.splitlines() if ln.strip()]
        for line in raw_lines:
            if line.startswith("__ALIVE__="):
                alive = line.split("=", 1)[1].strip() == "1"
            elif line.startswith("__PID__="):
                raw = line.split("=", 1)[1].strip()
                if raw.isdigit():
                    pid = int(raw)
            elif line.lstrip().startswith("{"):
                try:
                    state = json.loads(line)
                except json.JSONDecodeError:
                    state = {"parse_error": line}
        return {
            "running": alive,
            "pid": pid,
            "state": state,
            "state_path": config.V250_LOOP_STATE,
            "pid_path": config.V250_LOOP_PID,
            "log_path": config.V250_LOOP_LOG,
        }

    def v250_loop_start(self, rows: int = config.DEFAULT_ROWS, warmup: int = 2) -> dict:
        """Start the persistent on-kit V250 -> PID helper daemon."""
        status = self.v250_loop_status()
        if status.get("running"):
            status["started"] = False
            status["note"] = "already running"
            return status

        helper = (
            f"{_q(config.V250_PID_LOOP)} {_q(config.V250_MODEL)} {int(rows)} {int(warmup)} "
            f"{_q(config.V250_INPUT_CSV)} 0.001 {config.V250_U_SCALE:.9f} {int(config.V250_LOOP_SLEEP_US)} "
            f"--daemon --state {_q(config.V250_LOOP_STATE)} --pid-file {_q(config.V250_LOOP_PID)}"
        )
        remote = (
            f"cd {_q(config.BRINGUP)} && "
            f"rm -f {_q(config.V250_LOOP_STATE)} {_q(config.V250_LOOP_PID)} {_q(config.V250_LOOP_LOG)}; "
            f"{helper} >{_q(config.V250_LOOP_LOG)} 2>&1 < /dev/null &"
        )
        r = subprocess.run(
            ["ssh", "-f", "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
             self.host, remote],
            capture_output=True, text=True, timeout=12,
        )
        if r.returncode != 0:
            raise RuntimeError((r.stdout + r.stderr).strip() or f"ssh start failed rc={r.returncode}")

        last = None
        for _ in range(20):
            time.sleep(0.1)
            last = self.v250_loop_status()
            if last.get("running") and last.get("state"):
                last["started"] = True
                return last
        last = last or self.v250_loop_status()
        last["started"] = False
        last["note"] = "start command returned, but no live state appeared"
        return last

    def v250_loop_stop(self) -> dict:
        """Stop the persistent on-kit helper daemon with TERM, then KILL if needed."""
        cmd = (
            f"pid=$(cat {_q(config.V250_LOOP_PID)} 2>/dev/null || true); "
            'if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then '
            'kill -TERM "$pid"; '
            'for i in 1 2 3 4 5 6 7 8 9 10; do '
            'sleep 0.1; kill -0 "$pid" 2>/dev/null || break; '
            'done; '
            'if kill -0 "$pid" 2>/dev/null; then kill -KILL "$pid"; fi; '
            "fi; "
            f"rm -f {_q(config.V250_LOOP_PID)}; "
            "true"
        )
        self._ssh_run(cmd)
        status = self.v250_loop_status()
        status["stopped"] = not status.get("running")
        return status

    def boot_marker(self) -> str | None:
        """Best-effort kernel boot marker used to invalidate stale evidence after power cycles."""
        try:
            r = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=2",
                 self.host, "cat /proc/sys/kernel/random/boot_id 2>/dev/null || uptime -s 2>/dev/null || true"],
                capture_output=True, text=True, timeout=3,
            )
        except subprocess.TimeoutExpired:
            return None
        val = (r.stdout or "").strip().splitlines()
        return val[0].strip() if val and val[0].strip() else None

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
    write/readback echo (like real M1) and a canned V250 result, so the
    dashboard behaves identically with no board attached.
    """

    kind = "dryrun"

    def __init__(self, kp=0.8, ki=0.05, kd=0.02):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.out_min, self.out_max = -1.0, 1.0
        self.integ = 0.0
        self.prev_err = 0.0
        self.error = 0.0
        self.u_ai = 0.0
        self.write_count = 0
        self.wd_timeout = 0
        self._elo = 0
        self._regs: dict[int, int] = {}   # shadow-gain store for readback echo

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
        elif addr == R_KP:
            self.kp = q16_to_f(val)
        elif addr == R_KI:
            self.ki = q16_to_f(val)
        elif addr == R_KD:
            self.kd = q16_to_f(val)
        elif addr == R_OUT_MIN:
            self.out_min = q16_to_f(val)
        elif addr == R_OUT_MAX:
            self.out_max = q16_to_f(val)
        elif addr == R_ACC_START:
            self._regs[addr] = val
        else:
            self._regs[addr] = val   # shadow gains et al.

    def _pid(self) -> float:
        self.integ += self.ki * self.error
        deriv = self.kd * (self.error - self.prev_err)
        self.prev_err = self.error
        u_pid = self.kp * self.error + self.integ + deriv
        u_ai = 0.0 if self.wd_timeout else self.u_ai
        u_ai_clamped = max(-OUTER_SECTOR_CLAMP_FRACTION,
                           min(OUTER_SECTOR_CLAMP_FRACTION, u_ai))
        return max(self.out_min, min(self.out_max, u_pid + u_ai_clamped))

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

    def boot_marker(self) -> str | None:
        return "dry-run"

    def close(self) -> None:
        pass
