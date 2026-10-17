# CUDA-Q and FPGA experiments

Three synthetic quantum workloads ran on a PolarFire SoC development kit on October 17, 2026.
CUDA-Q checked representative quantum evolutions and circuits on an NVIDIA GB10 workstation.
The CPU generated the full datasets. Small classical inference cores then processed frozen records in FPGA fabric.

These experiments extend the project beyond its original SBIR proposal scope.
They share the board and verification approach described in the [main project](../../README.md).
They are a separate experimental area, with their own inputs, failure records, and acceptance checks.
The original [proposal crosswalk](../../docs/proposal/README.md) remains the record of proposed and delivered sensing work.

## Measured FPGA results

| Demonstration | Frozen records | Exact replay calls | Fabric cycles | Core time at 125 MHz | Median host time |
| --- | ---: | ---: | ---: | ---: | ---: |
| [Qubit readout classifier](readout/README.md) | 10,240 | 102,400 | 85 | 0.680 µs | 22 µs |
| [Coupled-spin NV estimator](nv/README.md) | 2,061 | 20,610 | 23,479 | 187.832 µs | about 209 µs |
| [Small surface-code lookup](qec/README.md) | 4,864 | 48,640 | 4 | 0.032 µs | 9 µs |

All **171,650 calls** matched their frozen integer references, including full NV distance scores.
Each record ran ten times across two cold boots. Repeats are not independent scientific samples.
Each boot also passed 15 control checks, including forced timeout, active abort, and successful subsequent calls.
Existing VectorBlox V250 inference completed after both boots.

Core times are calculated from fabric counters and the configured 125 MHz clock.
Host times include input transfer, output reads, and software overhead. They exclude physical signal acquisition.
The [execution summary](evidence/summary.json) and [per-call receipts](evidence/board/) retain counts and timing distributions.

## What the experiments establish

The board executed three compact classical algorithms against saved synthetic inputs.
CUDA-Q supplied independent checks of selected quantum calculations. It did not generate the complete datasets.
These results establish neither a GPU speed advantage nor quantum advantage.
No live quantum sensor or QPU supplied the inputs. Board power and radiation tolerance were not measured.
Quantum error correction does not make an FPGA resistant to radiation.

The scientific limitations remain visible in each track:

- **Readout:** host calibration improved one drift result from 80.47% to 98.34%; stale calibration reached 65.63% in the worst group.
- **NV:** the frozen 99% floating/fixed agreement gate failed at 98.4375%. One low-shot mismatch case reached 249.5 kHz error.
- **QEC:** the FPGA processes one compressed syndrome. It does not implement the temporal decoder that performed better offline.

Correct FPGA arithmetic does not remove these model limitations.
The small models also have strong CPU or stabilizer-simulator alternatives.

## Verify saved evidence

From the repository root, use Python 3.11 or later:

```sh
python3 experiments/cudaq-fpga/verify_saved_evidence.py
python3 -m unittest discover -s experiments/cudaq-fpga -p test_saved_evidence.py -v
```

The first command hashes the published package and checks every saved FPGA result against frozen reference bytes.
It checks counter continuity, deadlines, timing summaries, control receipts, and the V250 regression receipts.
The tests check that missing, corrupted, and inconsistent evidence fails verification.
Neither command accesses hardware, trains models, or regenerates scientific datasets.
They verify the saved record; they do not independently witness the original hardware execution.

The [experiment CI workflow](../../.github/workflows/quantum-experiments.yml) runs these checks on Linux and macOS.
It also tests the runner's deadline handling with fake registers.
Track READMEs provide additional CPU checks and optional reproduction instructions.
Reusing these consumed seeds reproduces the recorded study; it does not create fresh evaluation evidence.

## Hardware scope and build evidence

The integrated target was MPFS250T-FCVG484 with the STD/EXT Libero configuration.
The new peripheral occupies `0x60040000` through `0x60040fff`.
Its identity is `0x51465047`, with ABI version `0x00010000`.
That address contains the quantum-demo interface in this image. Older PID commands are incompatible.
The authored runners verify identity before writes and restrict access to this 4 KiB region.

The [curated build receipt](evidence/build/summary.json) records positive setup and hold slack in the integrated design.
Worst setup/hold slack was +0.878/+0.006 ns; the FIC0 clock had +1.634/+0.059 ns.
Fifteen inherited FIC3 checks remained unconstrained. No FIC0 checks were unconstrained.
The small hold margin and inherited coverage gaps limit the timing claim.
Whole-design utilization was 85,567 LUT4s, 65,204 DFFs, and 102,415 logic elements.
These totals include the existing design and are not incremental costs for the three cores.

The programmed job SHA256 was `ec12633f2d78edef3d649b7e98af18253f11f5dc023187cc01edcd50d319b7db`.
The recovery image was preserved; recovery programming was not exercised during this run.
This repository includes authored interface RTL, C/C++ cores, runner sources, and HLS inputs.
Generated vendor IP, complete licensed projects, programming jobs, and raw vendor logs are excluded.
The RTL testbench requires regenerated HLS modules. This package does not provide a complete bitstream rebuild.

See [provenance](PROVENANCE.md) for file mappings and publication transformations.

## Next useful studies

1. Test readout calibration on an independent public measured dataset with sufficient labels and acquisition metadata.
2. Define a larger coupled-spin problem where CUDA-Q contributes materially; compare accuracy, runtime, and memory against strong CPU baselines.
3. Test a bounded temporal QEC interface before proposing another FPGA implementation. Compare with established decoders on equal information.

Register new evaluation seeds and acceptance rules before those studies.
Seek external technical review before treating these demonstrations as a deployable sensing or quantum-control product.
