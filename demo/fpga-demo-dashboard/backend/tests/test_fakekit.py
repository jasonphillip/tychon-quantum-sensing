"""Register-level checks for the dry-run PID link."""

import math

from backend.links import FakeKit, MAX_SLEW_PER_CYCLE
from backend.registers import (
    OUTER_SECTOR_CLAMP_FRACTION,
    R_ACC_START,
    R_AI_ACTIVE,
    R_AXI_WRITE_COUNT,
    R_COOLDOWN,
    R_CSR_VERSION,
    R_DERIVATIVE,
    R_ERROR_HIGH,
    R_ERROR_LOW,
    R_INNER_CLAMP,
    R_INTEGRATOR,
    R_KD,
    R_KI,
    R_KP,
    R_OUT_MAX,
    R_OUT_MIN,
    R_POST_CLAMP,
    R_PRE_CLAMP,
    R_SATURATION,
    R_U_AI,
    R_WATCHDOG,
)


OUTPUT_REGS = (
    R_AXI_WRITE_COUNT, R_CSR_VERSION, R_PRE_CLAMP, R_POST_CLAMP,
    R_INTEGRATOR, R_DERIVATIVE, R_SATURATION, R_WATCHDOG,
    R_COOLDOWN, R_AI_ACTIVE,
)


def q16(value):
    return round(value * 65536) & 0xFFFFFFFF


def from_q16(value):
    value &= 0xFFFFFFFF
    return (value - (1 << 32) if value & (1 << 31) else value) / 65536


def write_error(kit, error):
    raw = round(error * (1 << 30)) & ((1 << 64) - 1)
    kit.wraw(R_ERROR_LOW, raw & 0xFFFFFFFF)
    kit.wraw(R_ERROR_HIGH, raw >> 32)


def test_output_reads_are_latched_and_do_not_advance_pid():
    kit = FakeKit()
    write_error(kit, 0.25)
    kit.wraw(R_U_AI, q16(0.03))
    kit.wraw(R_ACC_START, 1)
    state = (kit.integ, kit.prev_err, kit._ai_latch)
    first = tuple(kit.rraw(addr) for addr in OUTPUT_REGS)
    for _ in range(5):
        assert tuple(kit.rraw(addr) for addr in OUTPUT_REGS) == first
        assert (kit.integ, kit.prev_err, kit._ai_latch) == state
    write_error(kit, -0.7)
    kit.wraw(R_U_AI, q16(-0.04))
    assert kit.rraw(R_POST_CLAMP) == first[OUTPUT_REGS.index(R_POST_CLAMP)]
    assert (kit.integ, kit.prev_err, kit._ai_latch) == state


def test_zero_inner_clamp_removes_ai_on_next_start():
    kit = FakeKit(kp=0.0, ki=0.0, kd=0.0)
    kit.wraw(R_U_AI, q16(0.04))
    for _ in range(4):
        kit.wraw(R_ACC_START, 1)
    assert from_q16(kit.rraw(R_POST_CLAMP)) > 0
    kit.wraw(R_INNER_CLAMP, q16(0.0))
    assert from_q16(kit.rraw(R_POST_CLAMP)) > 0
    kit.wraw(R_ACC_START, 1)
    assert kit.rraw(R_POST_CLAMP) == q16(0.0)
    assert kit._ai_latch == 0.0


def test_twenty_step_register_trace_matches_independent_reference():
    kit = FakeKit()
    kp, ki, kd = 0.8, 0.05, 0.02
    out_min, out_max = -1.0, 1.0
    inner = OUTER_SECTOR_CLAMP_FRACTION
    integral = previous_error = previous_ai = 0.0
    trace = []
    expected = []

    for step in range(20):
        if step == 4:
            kp = from_q16(q16(0.65))
            kit.wraw(R_KP, q16(0.65))
        if step == 7:
            inner = from_q16(q16(0.002))
            kit.wraw(R_INNER_CLAMP, q16(0.002))
        if step == 12:
            inner = 0.0
            kit.wraw(R_INNER_CLAMP, q16(0.0))
        if step == 15:
            inner = from_q16(q16(0.025))
            kit.wraw(R_INNER_CLAMP, q16(0.025))
        if step == 17:
            out_min, out_max = -0.5, 0.5
            kit.wraw(R_OUT_MIN, q16(out_min))
            kit.wraw(R_OUT_MAX, q16(out_max))

        error = 0.27 * math.cos(step / 3) - 0.06
        raw_error = round(error * (1 << 30)) & ((1 << 64) - 1)
        signed_error = raw_error - (1 << 64) if raw_error & (1 << 63) else raw_error
        error = signed_error / (1 << 30)
        ai = from_q16(q16(0.06 * math.sin(step / 2) + 0.015))
        write_error(kit, error)
        kit.wraw(R_U_AI, q16(ai))
        kit.wraw(R_ACC_START, 1)
        trace.append(from_q16(kit.rraw(R_POST_CLAMP)))

        integral += ki * error
        derivative = kd * (error - previous_error)
        previous_error = error
        pid = kp * error + integral + derivative
        change = max(-MAX_SLEW_PER_CYCLE, min(MAX_SLEW_PER_CYCLE, ai - previous_ai))
        slewed_ai = previous_ai + change
        bound = (out_max - out_min) * inner
        previous_ai = max(-bound, min(bound, slewed_ai))
        output = max(out_min, min(out_max, pid + previous_ai))
        expected.append(from_q16(q16(output)))

    assert len(trace) == 20
    for actual, want in zip(trace, expected):
        assert abs(actual - want) <= 1e-9
