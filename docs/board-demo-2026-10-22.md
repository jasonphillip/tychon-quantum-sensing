# Actual-board demonstration, 2026-10-22

**Replayed synthetic input.** This recording shows the published INT8 model running on the PolarFire SoC Icicle Kit's VectorBlox V250 NPU over the same 512 synthetic ODMR spectra as the [2026-10-14 evidence run](../workers/odmr-edge-ml/docs/deployed_model_on_kit_2026-10.md). No diamond, no measured spectrum and no sensor was involved.

**The board.** The production PolarFire SoC Icicle Kit (MPFS250T) in its grey enclosure, cables through the drilled side holes, photographed July 2026. The [lab page](lab.md) describes the setup.

![The PolarFire SoC Icicle Kit in its enclosure, with the MPFS250T under the centre of the board](media/icicle-kit-in-enclosure.jpg)

**The run.**

![Terminal recording of the actual-board run: SSH to the kit, input hashes, pfkit infer, and a bit-for-bit comparison](media/board-demo-2026-10-22.gif)

The recording ([asciinema cast](media/board-demo-2026-10-22.cast), 62 seconds) shows four steps.

1. The board answers over SSH: `riscv64`, its uptime, and the UIO node `vbx@60030000` that exposes the V250.
2. The inputs are hashed. `model.vnnx` (`55bf88b7…`) and `input.int8.npy` (`f774fa0e…`) are byte-identical to the published run.
3. `pfkit infer` copies the runner, the model and the input to the kit, runs `vbx_run`, and copies `hw.bin` back. The kit reported 512 of 512 samples, no NPU error, and a median of 0.038 ms per sample.
4. `compare.py` finds the fresh `hw.bin` identical to the published `hw.bin` (`08047435…`) and to the CPU INT8 simulation, 512 of 512 rows.

**What this establishes.** The model conversion and the on-kit inference path work, and they repeat on these inputs eight days after the evidence run.

**What this does not establish.** Sensing. The published accuracy on this set is a final-field error of 14.47 µT, worse than a 12.6 µT constant predictor. The timing covers inference start and poll only, not acquisition or the control loop. No radiation or flight qualification is implied; the board is a commercial Icicle Kit.

Tools: `pfkit` from the public [polarfire-agent-skills](https://github.com/jasonphillip/polarfire-agent-skills) repository, with the kit image carrying the `vbx_only` overlay. The dashboard's [dry-run recording](../demo/fpga-demo-dashboard/README.md#dry-run-recording) is a different thing: a software model with no hardware behind it.
