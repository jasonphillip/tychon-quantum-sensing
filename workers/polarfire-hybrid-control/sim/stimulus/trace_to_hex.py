#!/usr/bin/env python3
"""Convert odmr_representative_trace.csv to a $readmemh file for tb_power.

Each output line is one 128-bit hex word:
    {32'h0, u_ai_q16[31:0], error_hi[31:0], error_lo[31:0]}
where error is the Q34.30 (ap_fixpt<64,34>) two's-complement encoding of
error_hz split into low/high 32-bit halves (matching the M1 0x810/0x814
register pair), and u_ai is Q16.16 (ap_fixpt<32,16>) of u_ai_volts.

The CSV's ai_wd_timeout column is ignored: in the subsystem-level TB the
watchdog is a real instantiated counter cleared by vbx_output_valid pulses,
not a forced input.

Usage:
    python3 sim/stimulus/trace_to_hex.py \
        [sim/stimulus/odmr_representative_trace.csv] \
        [sim/stimulus/odmr_representative_trace.hex]
"""

import csv
import sys


def q_pack(value: float, frac_bits: int, width: int) -> int:
    scaled = round(value * (1 << frac_bits))
    return scaled & ((1 << width) - 1)


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else "sim/stimulus/odmr_representative_trace.csv"
    dst = sys.argv[2] if len(sys.argv) > 2 else "sim/stimulus/odmr_representative_trace.hex"
    rows = 0
    with open(src, newline="") as f, open(dst, "w") as out:
        reader = csv.DictReader(f)
        for row in reader:
            err = q_pack(float(row["error_hz"]), 30, 64)
            u_ai = q_pack(float(row["u_ai_volts"]), 16, 32)
            word = (u_ai << 64) | err  # [95:64]=u_ai, [63:32]=err_hi, [31:0]=err_lo
            out.write(f"{word:032x}\n")
            rows += 1
    print(f"wrote {rows} rows -> {dst}")


if __name__ == "__main__":
    main()
