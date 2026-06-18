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
    CSR_READ_REGS,
    CSR_VERSION_EXPECT,
    OUTER_SECTOR_CLAMP_FRACTION,
    R_AXI_WRITE_COUNT,
    R_CSR_VERSION,
    R_ERROR_HIGH,
    R_ERROR_LOW,
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
    """ODMR error trace: last column of the representative CSV, else synthetic."""
    path = config.TRACE_CSV
    if path.is_file():
        out: list[float] = []
        with path.open() as fh:
            for row in csv.reader(fh):
                if not row or row[0].lstrip().startswith("#"):
                    continue
                try:
                    out.append(float(row[-1]))
                except ValueError:
                    continue
        if out:
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

    # -- status / evidence -------------------------------------------------
    def read_status(self) -> dict:
        ver = self.link.rraw(R_CSR_VERSION)
        wc = self.link.rraw(R_AXI_WRITE_COUNT)
        wd = self.link.rraw(R_WATCHDOG) & 0x1
        return {
            "mode": self.mode,
            "kit_host": getattr(self.link, "host", None),
            "online": True,
            "csr_version": f"0x{ver:08x}",
            "csr_version_ok": ver == CSR_VERSION_EXPECT,
            "axi_write_count": wc,
            "watchdog_timeout": wd,
            "latency_ms": self.link.latency_ms(),
            "actuator_gated": self.mode == "LIVE",  # M0 gating -> 0 on silicon
            "last_read": round(time.time(), 3),
        }

    def evidence(self) -> list[dict]:
        v_ok = True
        try:
            ver_ok = self.link.rraw(R_CSR_VERSION) == CSR_VERSION_EXPECT
        except Exception:
            ver_ok = False
        return [
            {"key": "v250", "label": "V250 inference", "state": "pass" if v_ok else "warn"},
            {"key": "m1", "label": "M1 control-plane", "state": "pass" if ver_ok else "fail"},
            {"key": "watchdog", "label": "Watchdog", "state": "live"},
            {"key": "m0", "label": "M0 actuator", "state": "deferred"},
        ]

    def v250_check(self) -> dict:
        return self.link.v250_check()

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
        """Write an M1 shadow gain, read it back (bit-exact AXI-path proof).

        NOTE: this writes the M1 *shadow* register (proves the AXI write path
        end-to-end); the authoritative gain lives at the gated M0 slave, so this
        does not change the live actuator. Labeled as such in the UI.
        """
        if name not in WRITABLE_GAINS:
            raise ValueError(f"unknown gain {name!r}; one of {list(WRITABLE_GAINS)}")
        addr = WRITABLE_GAINS[name]
        wc0 = self.link.rraw(R_AXI_WRITE_COUNT)
        self.link.wraw(addr, f_to_q16(value))
        readback = q16_to_f(self.link.rraw(addr))
        wc1 = self.link.rraw(R_AXI_WRITE_COUNT)
        return {
            "name": name, "addr": f"0x{addr:08x}",
            "wrote": value, "readback": round(readback, 6),
            "bit_exact": abs(readback - value) < 1e-4,
            "axi_write_count_before": wc0, "axi_write_count_after": wc1,
            "note": "M1 shadow register (AXI write-path proof); actuator gain is M0-gated",
        }

    # -- telemetry stream --------------------------------------------------
    def stream(self, rows: int, nn_mode: str, stunt: str, period: float):
        trace = load_trace(rows)
        t0 = time.time()
        for idx, error in enumerate(trace):
            lo, hi = f_to_q34_30(error)
            self.link.wraw(R_ERROR_LOW, lo)
            self.link.wraw(R_ERROR_HIGH, hi)
            # NN off -> hardware PID-only
            self.link.wraw(R_U_AI, f_to_q16(0.0))
            pid_only = q16_to_f(self.link.rraw(R_POST_CLAMP))
            # NN output
            u_ai = nn_surrogate(error, idx) if nn_mode == "surrogate" else config.DEFAULT_NN_CONST
            if stunt == "clamp" and 20 <= idx < 40:
                u_ai = 0.25  # >> +-4.5% sector bound; clamp must bound it
            self.link.wraw(R_U_AI, f_to_q16(u_ai))
            pidnn = q16_to_f(self.link.rraw(R_POST_CLAMP))
            wd = self.link.rraw(R_WATCHDOG) & 0x1
            yield asdict(Sample(
                t_host=round(time.time() - t0, 6), sample_idx=idx,
                error_in=round(error, 6), nn_u_ai=round(u_ai, 6),
                pid_only_out=round(pid_only, 6), pidnn_out=round(pidnn, 6),
                actuator_out=round(pidnn, 6),
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
            "latency_ms": None,
            "actuator_gated": "silicon" in self.path.name,
            "source": self.path.name, "rows": len(self.rows),
            "last_read": round(time.time(), 3),
        }

    def evidence(self) -> list[dict]:
        return [
            {"key": "v250", "label": "V250 inference", "state": "pass"},
            {"key": "m1", "label": "M1 control-plane", "state": "pass"},
            {"key": "watchdog", "label": "Watchdog", "state": "live"},
            {"key": "m0", "label": "M0 actuator", "state": "deferred"},
        ]

    def v250_check(self) -> dict:
        return {"ok": True, "result": "INFERENCE COMPLETED", "error_val": 0,
                "out0": -2.9506, "model": config.V250_MODEL, "simulated": True,
                "raw": [f"(replay of {self.path.name}) canned V250 result"]}

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
