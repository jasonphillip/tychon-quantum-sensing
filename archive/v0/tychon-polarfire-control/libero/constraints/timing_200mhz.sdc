# timing_200mhz.sdc — Timing Constraints
#
# 200 MHz fabric clock constraint for PolarFire SoC
# Period = 5.0 ns

create_clock -name {clk} -period 5.0 [get_ports {clk}]
