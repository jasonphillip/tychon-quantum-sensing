"""Fabric register map (two-slot bitstream) + Q-format helpers.

SLAVE3 page 0x60040000 is split by axi4_demux2 into two sub-slaves:
  - M0 "gains"   @ 0x60040000..0x600407FF
  - M1 "pid_csr" @ 0x60040800..0x60040FFF

M0 reads remain blocked in the dashboard. For the resident idfix2 bitstream,
allowlisted M0 writes are safe and are required to set authoritative PID gains
and pulse `acc_start`; the live actuator is still read through the clean M1
`post_clamp_out` tap. Never touch the stale overlay address 0x60001000.
"""
from __future__ import annotations

# --- sub-window bases -----------------------------------------------------
GAINS_BASE = 0x60040000   # M0 -- writes allowlisted only for idfix2; do not read
CSR = 0x60040800          # M1

# --- M0 (SmartHLS PID gains/control) -------------------------------------
R_ACC_START = GAINS_BASE + 0x008   # WO  pulse one host-paced PID compute
R_KP = GAINS_BASE + 0x00C
R_KI = GAINS_BASE + 0x010
R_KD = GAINS_BASE + 0x014
R_OUT_MIN = GAINS_BASE + 0x018
R_OUT_MAX = GAINS_BASE + 0x01C
R_INNER_CLAMP = GAINS_BASE + 0x020

# --- M1 (pid_csr) register offsets ---------------------------------------
R_AXI_WRITE_COUNT = CSR + 0x000   # RO  liveness counter (+4 per M1 write)
R_CSR_VERSION = CSR + 0x004       # RO  0x00010000
R_ERROR_LOW = CSR + 0x010         # RW  error[31:0]  (Q34.30)
R_ERROR_HIGH = CSR + 0x014        # RW  error[63:32]
R_U_AI = CSR + 0x018              # RW  NN feedforward (Q16.16)
R_KP_SHADOW = CSR + 0x020         # RW  shadow gains (write/readback echo)
R_KI_SHADOW = CSR + 0x024
R_KD_SHADOW = CSR + 0x028
R_OUT_MIN_SHADOW = CSR + 0x02C
R_OUT_MAX_SHADOW = CSR + 0x030
R_INNER_CLAMP_SHADOW = CSR + 0x034
R_PRE_CLAMP = CSR + 0x040         # RO  (tied 0, disclosed stub)
R_POST_CLAMP = CSR + 0x044        # RO  live clamped actuator output (Q16.16)
R_INTEGRATOR = CSR + 0x048        # RO  (tied 0)
R_DERIVATIVE = CSR + 0x04C        # RO  (tied 0)
R_SATURATION = CSR + 0x050        # RO  bit0 = clamp flag
R_WATCHDOG = CSR + 0x054          # RO  bit0 = watchdog timeout (LIVE)
R_COOLDOWN = CSR + 0x058          # RO  (tied 0)
R_AI_ACTIVE = CSR + 0x05C         # RO  (tied 0)

CSR_VERSION_EXPECT = 0x00010000

# --- M0/M1 ranges for the safety guard -----------------------------------
M0_LO, M0_HI = 0x60040000, 0x600407FF
M1_LO, M1_HI = 0x60040800, 0x60040FFF

# --- safety constant (hls/include/rta_config.hpp) ------------------------
OUTER_SECTOR_CLAMP_FRACTION = 0.045   # AI output bounded to +-4.5% of range


def is_m0(addr: int) -> bool:
    """True if addr is in the M0 gains/control sub-window."""
    return M0_LO <= addr <= M0_HI


M0_WRITE_ALLOWLIST = {
    R_ACC_START,
    R_KP,
    R_KI,
    R_KD,
    R_OUT_MIN,
    R_OUT_MAX,
    R_INNER_CLAMP,
}


# --- Q-format helpers (ported from rung_g_replay.py) ---------------------
def f_to_q16(v: float) -> int:
    return int(round(v * 65536.0)) & 0xFFFFFFFF


def q16_to_f(raw: int) -> float:
    raw &= 0xFFFFFFFF
    return (raw - (1 << 32) if raw & 0x80000000 else raw) / 65536.0


def f_to_q34_30(v: float) -> tuple[int, int]:
    """Q34.30 64-bit -> (low32, high32)."""
    raw = int(round(v * (1 << 30))) & ((1 << 64) - 1)
    return raw & 0xFFFFFFFF, (raw >> 32) & 0xFFFFFFFF


# --- named register groups for the CSR panel -----------------------------
# (name, addr, kind) — kind drives formatting in the UI: hex | u32 | q16
CSR_READ_REGS = [
    ("axi_write_count", R_AXI_WRITE_COUNT, "u32"),
    ("csr_version", R_CSR_VERSION, "hex"),
    ("post_clamp_out", R_POST_CLAMP, "q16"),
    ("pre_clamp_out", R_PRE_CLAMP, "q16"),
    ("integrator", R_INTEGRATOR, "q16"),
    ("derivative", R_DERIVATIVE, "q16"),
    ("saturation_csr", R_SATURATION, "hex"),
    ("watchdog_csr", R_WATCHDOG, "hex"),
    ("kp_shadow", R_KP_SHADOW, "q16"),
    ("ki_shadow", R_KI_SHADOW, "q16"),
    ("kd_shadow", R_KD_SHADOW, "q16"),
]

# writable M1 shadow gains (write a float -> read back the same Q16.16 value)
WRITABLE_GAINS = {
    "kp": R_KP_SHADOW,
    "ki": R_KI_SHADOW,
    "kd": R_KD_SHADOW,
    "out_min": R_OUT_MIN_SHADOW,
    "out_max": R_OUT_MAX_SHADOW,
    "inner_clamp": R_INNER_CLAMP_SHADOW,
}

# Matching authoritative M0 writes for idfix2 LIVE mode.
AUTHORITATIVE_M0_GAINS = {
    "kp": R_KP,
    "ki": R_KI,
    "kd": R_KD,
    "out_min": R_OUT_MIN,
    "out_max": R_OUT_MAX,
    "inner_clamp": R_INNER_CLAMP,
}
