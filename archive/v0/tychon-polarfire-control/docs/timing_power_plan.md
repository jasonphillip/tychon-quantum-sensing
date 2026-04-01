# Timing and Power Extraction Methodology

## SmartTime (Static Timing Analysis)
- Extract post-P&R timing reports from Libero on Beelink
- Verify PID loop latency < 150 µs (expected: 50-75 ns with II=1 at 200 MHz)
- Verify AI inference latency < 1 ms via VectorBlox V250
- Reports committed to `libero/reports/` as XML

## SmartPower (Power Analysis)
- Run post-P&R power estimation with VCD activity factors
- Verify total payload power < 12 W
- VectorBlox V250 duty-cycled at 10-100 Hz with sleep mode between inferences
- Reports committed to `libero/reports/` as XML

## Workflow
1. Synthesis and P&R complete on Beelink
2. Run SmartTime via `04_synth_pnr.tcl` extraction step
3. Run SmartPower with representative activity factors
4. Commit XML reports to `libero/reports/`
5. Push to GitHub; analyze on DGX Spark
