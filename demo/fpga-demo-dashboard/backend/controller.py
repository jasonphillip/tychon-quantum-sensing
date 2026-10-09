"""High-level dashboard operations over a low-level link.

Controller(link)        -> LIVE (KitLink) or DRY-RUN (FakeKit)
ReplayController(path)   -> REPLAY (streams a saved .jsonl)

Both expose the same surface consumed by main.py:
    read_status() -> dict
    evidence() -> list[dict]
    v250_check() -> dict
    csr_read_all() -> list[dict]
    csr_write_gain(name, value) -> dict
    stream(rows, nn_mode, stunt, period) -> generator[dict]   (telemetry Samples)
    latency_ms() -> float | None
    close()
"""
from __future__ import annotations

import csv
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from . import config
from .registers import (
    AUTHORITATIVE_M0_GAINS,
    CSR_READ_REGS,
    CSR_VERSION_EXPECT,
    OUTER_SECTOR_CLAMP_FRACTION,
    R_ACC_START,
    R_AXI_WRITE_COUNT,
    R_CSR_VERSION,
    R_ERROR_HIGH,
    R_ERROR_LOW,
    R_INNER_CLAMP,
    R_KD,
    R_KI,
    R_KP,
    R_OUT_MAX,
    R_OUT_MIN,
    R_POST_CLAMP,
    R_U_AI,
    R_WATCHDOG,
    WRITABLE_GAINS,
    f_to_q16,
    f_to_q34_30,
    q16_to_f,
)


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
    """Host-side stand-in for the V250 FCNN residual (per-row on-target inference
    is a Phase-4 stretch). Bounded, deterministic — CLEARLY a surrogate."""
    return max(-0.06, min(0.06, -0.3 * error + 0.01 * math.sin(idx / 7.0)))


def load_trace(rows: int) -> list[float]:
    """ODMR error trace, normalized for the host-paced PID demo."""
    path = config.TRACE_CSV
    if path.is_file():
        out: list[float] = []
        with path.open() as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames and "error_hz" in reader.fieldnames:
                for row in reader:
                    try:
                        out.append(float(row["error_hz"]) / 200.0)
                    except (TypeError, ValueError):
                        continue
            else:
                fh.seek(0)
                for row in csv.reader(fh):
                    if not row or row[0].lstrip().startswith("#"):
                        continue
                    try:
                        out.append(float(row[-1]))
                    except ValueError:
                        continue
        if out and any(abs(v) > 1e-9 for v in out):
            return out[:rows] if rows else out
    return [0.5 * math.exp(-i / 25.0) * math.cos(i / 9.0) for i in range(rows or 120)]


def _fmt(kind: str, raw: int):
    if kind == "hex":
        return f"0x{raw:08x}"
    if kind == "q16":
        return round(q16_to_f(raw), 6)
    return raw  # u32


class Controller:
    """LIVE / DRY-RUN: drives a real link (KitLink) or software model (FakeKit)."""

    def __init__(self, link):
        self.link = link
        self.mode = "LIVE" if link.kind == "live" else "DRY-RUN"
        self._m0_smoke_ok = self.mode != "LIVE"
        self._m0_smoke_note = "dry-run software model" if self.mode != "LIVE" else "not run"
        now = time.time()
        self._m0_smoke_checked_at: float | None = now if self.mode != "LIVE" else None
        self._v250_ok = self.mode != "LIVE"
        self._v250_note = "dry-run software model" if self.mode != "LIVE" else "needs test"
        self._v250_checked_at: float | None = now if self.mode != "LIVE" else None
        self._last_axi_write_count: int | None = None
        self._last_reset_detected_at: float | None = None
        self._last_boot_marker: str | None = None
        self._last_boot_check_at = 0.0

    # -- idfix2 live actuator setup ---------------------------------------
    def _m0_gate(self) -> tuple[bool, str]:
        gate = getattr(self.link, "m0_gate", None)
        if callable(gate):
            return gate()
        return True, "dry-run software model"

    def _write_pid_defaults(self) -> None:
        self.link.wraw(R_OUT_MIN, f_to_q16(config.PID_OUT_MIN))
        self.link.wraw(R_OUT_MAX, f_to_q16(config.PID_OUT_MAX))
        self.link.wraw(R_KP, f_to_q16(config.PID_KP))
        self.link.wraw(R_KI, f_to_q16(config.PID_KI))
        self.link.wraw(R_KD, f_to_q16(config.PID_KD))
        self.link.wraw(R_INNER_CLAMP, f_to_q16(OUTER_SECTOR_CLAMP_FRACTION))

    def _pulse_compute(self) -> None:
        self.link.wraw(R_ACC_START, 1)

    def _ensure_live_actuator_ready(self) -> None:
        if self.mode != "LIVE":
            self._write_pid_defaults()
            return
        ok, reason = self._m0_gate()
        if not ok:
            raise RuntimeError(f"LIVE actuator disabled: {reason}")
        if self._m0_smoke_ok:
            return
        ver = self.link.rraw(R_CSR_VERSION)
        if ver != CSR_VERSION_EXPECT:
            raise RuntimeError(f"csr_version=0x{ver:08x}; expected 0x{CSR_VERSION_EXPECT:08x}")
        self._write_pid_defaults()
        lo, hi = f_to_q34_30(0.25)
        self.link.wraw(R_ERROR_LOW, lo)
        self.link.wraw(R_ERROR_HIGH, hi)
        self.link.wraw(R_U_AI, f_to_q16(0.0))
        self._pulse_compute()
        post = q16_to_f(self.link.rraw(R_POST_CLAMP))
        if abs(post) < 1e-4:
            raise RuntimeError("idfix2 M0 smoke failed: post_clamp_out stayed zero")
        self._m0_smoke_ok = True
        self._m0_smoke_note = f"idfix2 M0 smoke passed; post_clamp_out={post:.6f}"
        self._m0_smoke_checked_at = time.time()

    def _invalidate_live_evidence(self, reason: str) -> None:
        self._m0_smoke_ok = False
        self._m0_smoke_note = reason
        self._m0_smoke_checked_at = None
        self._v250_ok = False
        self._v250_note = reason.replace("recheck", "test")
        self._v250_checked_at = None
        self._last_reset_detected_at = time.time()

    def _observe_pid_state(self, wc: int) -> None:
        if self.mode != "LIVE":
            self._last_axi_write_count = wc
            return
        if self._last_axi_write_count is not None and wc < self._last_axi_write_count:
            self._invalidate_live_evidence("needs recheck after kit reset")
        self._last_axi_write_count = wc

    def _observe_boot_marker(self) -> str | None:
        if self.mode != "LIVE":
            return None
        now = time.time()
        if now - self._last_boot_check_at < 5.0:
            return self._last_boot_marker
        self._last_boot_check_at = now
        marker_fn = getattr(self.link, "boot_marker", None)
        if not callable(marker_fn):
            return self._last_boot_marker
        marker = marker_fn()
        if marker and self._last_boot_marker and marker != self._last_boot_marker:
            self._invalidate_live_evidence("needs recheck after kit reboot")
        if marker:
            self._last_boot_marker = marker
        return self._last_boot_marker

    # -- status / evidence -------------------------------------------------
    def read_status(self) -> dict:
        ver = self.link.rraw(R_CSR_VERSION)
        wc = self.link.rraw(R_AXI_WRITE_COUNT)
        self._observe_pid_state(wc)
        wd_raw = self.link.rraw(R_WATCHDOG)
        wd = wd_raw & 0x1
        ok, m0_reason = self._m0_gate()
        boot_marker = self._observe_boot_marker()
        return {
            "mode": self.mode,
            "kit_host": getattr(self.link, "host", None),
            "online": True,
            "csr_version": f"0x{ver:08x}",
            "csr_version_ok": ver == CSR_VERSION_EXPECT,
            "axi_write_count": wc,
            "watchdog_timeout": wd,
            "watchdog_raw": f"0x{wd_raw:08x}",
            "watchdog_note": "2 ms fabric watchdog image programmed; 250000 cycles at 125 MHz, cleared by fresh V250 completions",
            "watchdog_label": "Safe fallback active" if wd else "AI assist active",
            "latency_ms": self.link.latency_ms(),
            "actuator_gated": False,
            "actuator_source": "M1 post_clamp_out after idfix2 M0 acc_start pulse",
            "kit_bitstream": config.KIT_BITSTREAM or None,
            "m0_writes_enabled": ok,
            "m0_gate": m0_reason,
            "idfix2_smoke_ok": self._m0_smoke_ok,
            "idfix2_smoke_note": self._m0_smoke_note,
            "idfix2_smoke_checked_at": round(self._m0_smoke_checked_at, 3) if self._m0_smoke_checked_at else None,
            "v250_ok": self._v250_ok,
            "v250_note": self._v250_note,
            "v250_checked_at": round(self._v250_checked_at, 3) if self._v250_checked_at else None,
            "reset_detected_at": round(self._last_reset_detected_at, 3) if self._last_reset_detected_at else None,
            "kit_boot_marker": boot_marker,
            "last_read": round(time.time(), 3),
        }

    def evidence(self) -> list[dict]:
        try:
            ver_ok = self.link.rraw(R_CSR_VERSION) == CSR_VERSION_EXPECT
        except Exception:
            ver_ok = False
        ok, _ = self._m0_gate()
        m0_state = "pass" if self._m0_smoke_ok else ("warn" if ok else "fail")
        now = time.time()
        return [
            {"key": "v250", "label": "AI chip", "state": "pass" if self._v250_ok else "warn",
             "checked_at": round(self._v250_checked_at, 3) if self._v250_checked_at else None,
             "note": self._v250_note},
            {"key": "fpga", "label": "FPGA alive", "state": "pass" if ver_ok else "fail",
             "checked_at": round(now, 3) if ver_ok else None,
             "note": "csr_version OK" if ver_ok else "csr_version read failed"},
            {"key": "pid", "label": "PID path", "state": m0_state,
             "checked_at": round(self._m0_smoke_checked_at, 3) if self._m0_smoke_checked_at else None,
             "note": self._m0_smoke_note},
            {"key": "watchdog", "label": "Safety fallback", "state": "live",
             "checked_at": round(now, 3),
             "note": "2 ms fabric watchdog readout"},
        ]

    def v250_check(self) -> dict:
        result = self.link.v250_check()
        self._v250_ok = bool(result.get("ok"))
        self._v250_note = "inference completed" if self._v250_ok else str(result.get("result", "check failed"))
        self._v250_checked_at = time.time()
        result["checked_at"] = round(self._v250_checked_at, 3)
        return result

    def v250_loop_status(self) -> dict:
        if self.mode != "LIVE":
            return {"running": False, "available": False, "note": "V250 loop daemon requires LIVE mode"}
        if not hasattr(self.link, "v250_loop_status"):
            return {"running": False, "available": False, "note": "link does not expose daemon controls"}
        status = self.link.v250_loop_status()
        status["available"] = True
        return status

    def v250_loop_start(self) -> dict:
        if self.mode != "LIVE":
            raise RuntimeError("V250 loop daemon requires LIVE mode")
        ok, reason = self._m0_gate()
        if not ok:
            raise RuntimeError(f"V250 loop daemon disabled: {reason}")
        status = self.link.v250_loop_start(rows=config.DEFAULT_ROWS, warmup=2)
        state = status.get("state") or {}
        if status.get("running") and state:
            self._m0_smoke_ok = True
            self._m0_smoke_note = (
                f"v250_pid_loop daemon running; input_row={state.get('input_row')} "
                f"post_clamp_out={float(state.get('post_clamp', 0.0)):.6f}"
            )
            self._m0_smoke_checked_at = time.time()
        status["available"] = True
        return status

    def v250_loop_stop(self) -> dict:
        if self.mode != "LIVE":
            raise RuntimeError("V250 loop daemon requires LIVE mode")
        status = self.link.v250_loop_stop()
        state = status.get("state") or {}
        if status.get("stopped"):
            self._m0_smoke_note = (
                f"v250_pid_loop daemon stopped; last_row={state.get('row', 'unknown')}"
            )
            self._m0_smoke_checked_at = time.time()
        status["available"] = True
        return status

    # -- CSR panel ---------------------------------------------------------
    def csr_read_all(self) -> list[dict]:
        rows = []
        for name, addr, kind in CSR_READ_REGS:
            try:
                raw = self.link.rraw(addr)
                rows.append({"name": name, "addr": f"0x{addr:08x}",
                             "value": _fmt(kind, raw), "kind": kind})
            except Exception as e:
                rows.append({"name": name, "addr": f"0x{addr:08x}",
                             "value": None, "kind": kind, "error": str(e)})
        return rows

    def csr_write_gain(self, name: str, value: float) -> dict:
        """Write an M1 shadow gain and, when LIVE/idfix2 is enabled, the M0 gain too."""
        if name not in WRITABLE_GAINS:
            raise ValueError(f"unknown gain {name!r}; one of {list(WRITABLE_GAINS)}")
        addr = WRITABLE_GAINS[name]
        wc0 = self.link.rraw(R_AXI_WRITE_COUNT)
        self.link.wraw(addr, f_to_q16(value))
        readback = q16_to_f(self.link.rraw(addr))
        m0_addr = AUTHORITATIVE_M0_GAINS.get(name)
        m0_written = False
        if self.mode == "LIVE" and m0_addr is not None:
            ok, reason = self._m0_gate()
            if not ok:
                raise RuntimeError(f"M1 shadow wrote, but LIVE M0 gain disabled: {reason}")
            self.link.wraw(m0_addr, f_to_q16(value))
            m0_written = True
        wc1 = self.link.rraw(R_AXI_WRITE_COUNT)
        return {
            "name": name, "addr": f"0x{addr:08x}",
            "wrote": value, "readback": round(readback, 6),
            "bit_exact": abs(readback - value) < 1e-4,
            "axi_write_count_before": wc0, "axi_write_count_after": wc1,
            "m0_written": m0_written,
            "note": "M1 shadow readback plus authoritative idfix2 M0 write" if m0_written
                    else "M1 shadow register readback; LIVE authoritative M0 write unavailable",
        }

    # -- telemetry stream --------------------------------------------------
    def stream(self, rows: int, nn_mode: str, stunt: str, period: float):
        if nn_mode == "v250-loop":
            yield from self._stream_v250_loop(rows)
            return

        self._ensure_live_actuator_ready()
        trace = load_trace(rows)
        t0 = time.time()
        for idx, error in enumerate(trace):
            lo, hi = f_to_q34_30(error)
            self.link.wraw(R_ERROR_LOW, lo)
            self.link.wraw(R_ERROR_HIGH, hi)
            # NN off -> hardware PID-only
            self.link.wraw(R_U_AI, f_to_q16(0.0))
            self._pulse_compute()
            pid_only = q16_to_f(self.link.rraw(R_POST_CLAMP))
            # NN feedforward
            u_ai = nn_surrogate(error, idx) if nn_mode == "surrogate" else config.DEFAULT_NN_CONST
            if stunt == "clamp" and 20 <= idx < 40:
                u_ai = 0.25  # >> +-4.5% sector bound; clamp must bound it
            # watchdog stunt: simulate the V250 stalling (software/replay only) so the
            # NN feedforward drops out and the loop reverts to pure PID (bumpless).
            wd_stunt = stunt == "watchdog" and 50 <= idx < 80 and self.mode != "LIVE"
            if wd_stunt:
                u_ai = 0.0
            self.link.wraw(R_U_AI, f_to_q16(u_ai))
            self._pulse_compute()
            pidnn = q16_to_f(self.link.rraw(R_POST_CLAMP))
            wd_raw = self.link.rraw(R_WATCHDOG)
            wd = 1 if wd_stunt else (wd_raw & 0x1)
            actuator = pidnn  # M1 post_clamp_out is the live actuator tap
            yield asdict(Sample(
                t_host=round(time.time() - t0, 6), sample_idx=idx,
                error_in=round(error, 6), nn_u_ai=round(u_ai, 6),
                pid_only_out=round(pid_only, 6), pidnn_out=round(pidnn, 6),
                actuator_out=round(actuator, 6),
                unclamped_calc=round(pid_only + u_ai, 6),
                clamp_active=int(abs(u_ai) > OUTER_SECTOR_CLAMP_FRACTION),
                watchdog_timeout=wd,
                mode="PID_ONLY_FALLBACK" if wd else "PID_NN",
                vbx_error=0,
                axi_write_count=self.link.rraw(R_AXI_WRITE_COUNT),
                csr_version=self.link.rraw(R_CSR_VERSION),
            ))
            if period:
                time.sleep(period)

    def _stream_v250_loop(self, rows: int):
        if self.mode != "LIVE":
            raise RuntimeError("V250 loop telemetry requires LIVE mode and the on-kit helper")
        ok, reason = self._m0_gate()
        if not ok:
            raise RuntimeError(f"V250 loop disabled: {reason}")

        for raw in self.link.v250_pid_loop(rows, warmup=2):
            idx = int(raw["row"])
            error = float(raw["error_in"])
            u_ai = float(raw["u_ai"])
            actuator = float(raw["post_clamp"])
            watchdog = int(raw["watchdog_timeout"])
            pid_only = config.PID_KP * error
            if not self._m0_smoke_ok and watchdog == 0 and abs(actuator) > 1e-6:
                self._m0_smoke_ok = True
                self._m0_smoke_note = (
                    f"v250_pid_loop passed; input_row={raw.get('input_row', idx)} "
                    f"post_clamp_out={actuator:.6f}"
                )
                self._m0_smoke_checked_at = time.time()
            yield asdict(Sample(
                t_host=round(float(raw["t_ns"]) / 1_000_000_000.0, 6),
                sample_idx=idx,
                error_in=round(error, 6),
                nn_u_ai=round(u_ai, 6),
                pid_only_out=round(pid_only, 6),
                pidnn_out=round(actuator, 6),
                actuator_out=round(actuator, 6),
                unclamped_calc=round(pid_only + u_ai, 6),
                clamp_active=int(abs(u_ai) > OUTER_SECTOR_CLAMP_FRACTION),
                watchdog_timeout=watchdog,
                mode="PID_ONLY_FALLBACK" if watchdog else "PID_NN",
                vbx_error=0,
                axi_write_count=int(raw["axi_write_count"], 16),
                csr_version=CSR_VERSION_EXPECT,
            ))

    def latency_ms(self):
        return self.link.latency_ms()

    def close(self):
        self.link.close()


class ReplayController:
    """REPLAY: serve status + telemetry from a saved .jsonl capture."""

    kind = "replay"
    mode = "REPLAY"

    def __init__(self, path: Path):
        self.path = path
        self.rows = [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]

    def read_status(self) -> dict:
        last = self.rows[-1] if self.rows else {}
        return {
            "mode": self.mode, "kit_host": None, "online": True,
            "csr_version": "0x00010000", "csr_version_ok": True,
            "axi_write_count": last.get("axi_write_count", 0),
            "watchdog_timeout": last.get("watchdog_timeout", 0),
            "watchdog_label": "Safe fallback active" if last.get("watchdog_timeout", 0) else "AI assist active",
            "latency_ms": None,
            "actuator_gated": False,
            "actuator_source": "saved telemetry capture",
            "m0_writes_enabled": False,
            "idfix2_smoke_ok": "silicon" in self.path.name and max(
                abs(float(r.get("actuator_out", 0))) for r in self.rows
            ) > 0 if self.rows else False,
            "source": self.path.name, "rows": len(self.rows),
            "last_read": round(time.time(), 3),
        }

    def evidence(self) -> list[dict]:
        now = round(time.time(), 3)
        return [
            {"key": "v250", "label": "AI chip", "state": "pass", "checked_at": now,
             "note": "replay uses saved inference evidence"},
            {"key": "fpga", "label": "FPGA alive", "state": "pass", "checked_at": now,
             "note": "saved replay capture"},
            {"key": "pid", "label": "PID path", "state": "pass", "checked_at": now,
             "note": "saved actuator capture"},
            {"key": "watchdog", "label": "Safety fallback", "state": "live", "checked_at": now,
             "note": "saved watchdog capture"},
        ]

    def v250_check(self) -> dict:
        return {"ok": True, "result": "INFERENCE COMPLETED", "error_val": 0,
                "out0": -2.9506, "model": config.V250_MODEL, "simulated": True,
                "raw": [f"(replay of {self.path.name}) canned V250 result"],
                "checked_at": round(time.time(), 3)}

    def csr_read_all(self) -> list[dict]:
        last = self.rows[-1] if self.rows else {}
        return [
            {"name": "csr_version", "addr": "0x60040804", "value": "0x00010000", "kind": "hex"},
            {"name": "axi_write_count", "addr": "0x60040800",
             "value": last.get("axi_write_count", 0), "kind": "u32"},
            {"name": "post_clamp_out", "addr": "0x60040844",
             "value": last.get("actuator_out", 0), "kind": "q16"},
        ]

    def csr_write_gain(self, name: str, value: float) -> dict:
        raise RuntimeError("CSR writes are unavailable in REPLAY mode")

    def stream(self, rows: int, nn_mode: str, stunt: str, period: float):
        for s in self.rows[: rows or None]:
            yield s
            if period:
                time.sleep(period)

    def latency_ms(self):
        return None

    def close(self):
        pass
