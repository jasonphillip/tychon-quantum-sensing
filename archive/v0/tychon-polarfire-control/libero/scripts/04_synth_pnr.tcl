# 04_synth_pnr.tcl — Synthesis, Place & Route, Report Extraction
#
# Steps:
#   1. Run Synplify Pro synthesis
#   2. Run place and route
#   3. Extract SmartTime XML timing reports (verify Fmax >= 200 MHz)
#   4. Extract SmartPower XML power reports (verify total < 12 W)
#   5. Extract resource utilization (LUTs, LSRAM, Math Blocks, DSPs)
#
# Reports are committed to libero/reports/ and pushed to GitHub.
# Analysis happens on DGX Spark.
#
# Run on Beelink after 03_smartdesign.tcl:
#   source 04_synth_pnr.tcl

# TODO: Populate with Libero synthesis and report extraction commands
