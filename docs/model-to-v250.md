# From a TFLite model to inference on the V250

This page covers the path from a small trained model to a running inference on the CoreVectorBlox V250 soft NPU. The board is a Microchip PolarFire SoC Icicle Kit with an MPFS250T.

Every command below is copied from a file in this repo, and the file path sits next to it. Where the repo has no command for a step, I say so and the step is manual.

I ran the Microchip tools on one x86 machine over SSH. Below I call it your tools host. Where a quoted command named that machine, its user or a private path, I put a placeholder such as `<tools-host>` or `<work-dir>` in its place.

## What you need

- A Microchip PolarFire SoC Icicle Kit with the MPFS250T in package FCVG484 (`workers/polarfire-hybrid-control/libero/scripts/01_scaffold_proj.tcl`).
- An x86 tools host with Libero SoC 2025.2, SmartHLS and the VectorBlox SDK installed (`workers/polarfire-hybrid-control/firmware/linux/Makefile`).
- A Libero license that covers the CoreVectorBlox IP, since the scaffold script was written against Silver plus the free CoreVectorBlox license (`workers/polarfire-hybrid-control/libero/scripts/02_import_ip.tcl`).
- An SD card and a serial terminal at 115200 8N1. HSS prints on MMUART0 and Linux on MMUART1 (`workers/polarfire-hybrid-control/firmware/linux/README.md`).
- A Python environment with PyTorch and TensorFlow for the model side (`workers/odmr-edge-ml/README.md`).
- Two version pins that must hold together. VectorBlox SDK v2.0.3 goes with CoreVectorBlox IP v2.0.1, and the compile flag is `-c V250`. SDK v3.0 only supports the Video Kit, so it's out (`workers/polarfire-hybrid-control/AGENTS.md`).

The worked example is the FCNN in `workers/odmr-edge-ml/`. It takes 100 spectrum points plus an anchor channel of the same length and returns one number.

## 1 Bring or train a model

The V250 runs a restricted set of INT8 operators. I check the model before I train at scale, because a rejected graph found after the training run costs a day.

`workers/odmr-edge-ml/src/odmr_edge_ml/validation/ops_guard.py` exports the model with `torch.export` and compares every operator to a list. Install the package, then call the guard.

```bash
pip install -e ".[dev]"
```

The command comes from `workers/odmr-edge-ml/README.md`. Run it inside `workers/odmr-edge-ml/`. `workers/odmr-edge-ml/experiments/architecture_comparison.py` calls the guard like this.

```python
from odmr_edge_ml.validation.ops_guard import check_model_ops
report = check_model_ops(model, input_shape=(1, 100))
```

`report.is_compatible` is true only when every operator is known and allowed. The guard also checks module types, so `Conv1d` fails even when it lowers to something legal.

The guard allows `Linear`, `Conv2d`, `ReLU`, `ReLU6`, `Add`, `Mean`, `AdaptiveAvgPool2d` and layout operators such as reshape, permute and flatten (`workers/odmr-edge-ml/src/odmr_edge_ml/validation/ops_guard.py`). It bans `Conv1d`, normalization layers, `Dropout`, `GELU`, `SiLU`, `Sigmoid`, `Tanh`, `Softmax`, max pooling, `mul` and `matmul`. Where you wanted `Conv1d`, use `Conv2d` with `(1, k)` kernels, and keep every tensor shape static (`workers/odmr-edge-ml/AGENTS.md`).

The ban list is stricter than the compiler. On 2026-07-02 I compiled sigmoid, tanh and softmax in single-input graphs and `vnnx_compile` accepted them (`workers/polarfire-hybrid-control/docs/vnnx_ops_support_probe_2026-07-02.md`). The real limit in that probe was topology. A graph with two inputs compiled and then gave wrong simulator output, and a GRU cell crashed the compiler outright. So keep the model to one graph input.

The repo's quantization-aware training uses symmetric INT8 with one scale per tensor, because the VectorBlox SDK 2.0.x is per-tensor only (`workers/odmr-edge-ml/src/odmr_edge_ml/training/qat.py`). That file's docstring contradicts the "per-channel" line in `workers/odmr-edge-ml/AGENTS.md`, and I trust the code.

## 2 Export INT8 TFLite

The export has one trap. A PyTorch `view()` that reads the batch size leaks `SHAPE`, `STRIDED_SLICE` and `PACK` operators into the TFLite file, and the compiler rejects them (`workers/odmr-edge-ml/src/odmr_edge_ml/models/fcnn_v2.py`).

The fix is a Keras model with a fixed batch of 1 and an already-shaped NHWC input. `workers/odmr-edge-ml/scripts/fix_fcnn_export.py` does this for the FCNN. It copies the trained weights over, converts the model and checks the operator set.

```bash
python scripts/fix_fcnn_export.py
```

That script is written for this repo's FCNN checkpoint and input shape. For your own model, copy the converter settings from the same file.

```python
converter = tf.lite.TFLiteConverter.from_keras_model(tf_model)
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.representative_dataset = representative_dataset
converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
converter.inference_input_type = tf.int8
converter.inference_output_type = tf.int8
```

The representative dataset yields up to 1,000 training samples, one at a time (`workers/odmr-edge-ml/scripts/fix_fcnn_export.py`). Pick samples that cover the range your model sees on the bench.

Then check the file before it leaves your machine. `workers/odmr-edge-ml/experiments/architecture_comparison.py` does it this way.

```python
from odmr_edge_ml.validation.tflite_ops import verify_tflite_ops
verify_tflite_ops(tflite_model)
```

It raises `TFLiteOpsError` if any banned operator is present (`workers/odmr-edge-ml/src/odmr_edge_ml/validation/tflite_ops.py`).

The hand-off artifact is a `.tflite` file, 7,656 bytes for the example (`workers/polarfire-hybrid-control/models/README.md`). I copied it to the tools host with `scp`. There's no wrapper for that step.

## 3 Compile to .vnnx on the tools host

The compile runs on the machine that has the VectorBlox SDK. On my tools host the SDK's own activation script failed, and a Python 3.10 virtual environment from the original install worked instead. Both activation lines are in `workers/polarfire-hybrid-control/tools/vnnx_ops_probe/run_vnnx_probe_bee.sh`.

```bash
source ~/vbx-env/bin/activate
source /c/Microchip/VectorBlox-SDK/setup_vars.sh
```

The first line is the one that worked (`workers/polarfire-hybrid-control/models/README.md`). Confirm the SDK version before you compile.

```bash
pip show vbx
```

Expect 2.0.3, and compile with the command from the same file.

```bash
vnnx_compile -c V250 -t <model>_integer_quant.tflite -o <model>.vnnx
```

The example input `fcnn_v2_residual_dataset_a_int8.tflite` compiles to a 12,832-byte `.vnnx` with SHA-256 `6c5cd21ae9d4ce9793f8bc143c2c53d564140bde3df1fda1ec08a5a1602512eb`. If your build of that same input differs in size or hash, suspect SDK drift first (`workers/polarfire-hybrid-control/models/README.md`).

Watch the compile output for the string `VECTORBLOX ERROR`. `run_vnnx_compile` in `workers/odmr-edge-ml/src/odmr_edge_ml/validation/tflite_ops.py` raises on it. No `.vnnx` file is committed in this repo, so keep yours out of git too.

## 4 Build the fabric

The V250 is soft IP. The kit's factory image doesn't contain it, so you need a bitstream with CoreVectorBlox V250 in the fabric.

There are two build paths in the repo, and only the second one produced the image that ran on my kit.

Path A is the four scaffold scripts. Source them in order from the Libero Tcl console, as the README shows (`workers/polarfire-hybrid-control/README.md`).

```
source libero/scripts/01_scaffold_proj.tcl
source libero/scripts/02_import_ip.tcl
source libero/scripts/03_smartdesign.tcl
source libero/scripts/04_synth_pnr.tcl
```

- `01_scaffold_proj.tcl` creates project `polarfire_hybrid_control` for MPFS250T, FCVG484, speed STD.
- `02_import_ip.tcl` imports the SmartHLS PID RTL and downloads CoreVectorBlox `Microsemi:SolutionCore:CoreVectorBlox:2.0.1`, configured as `VSIZE:V250`.
- `03_smartdesign.tcl` wires the AXI interconnect. Its own header calls it an early scaffold.
- `04_synth_pnr.tcl` runs synthesis, place and route, and writes reports. Line 39 passes an invalid `-script {REPORT}` option, and the Tcl around it swallows the error (`workers/polarfire-hybrid-control/libero/scripts/parallel/README.md`).

`00_full_pipeline.tcl` sources all four in one session.

Path B is the image that ran on my kit, and I didn't build it from Path A. I cloned a project from Microchip's Icicle Kit VectorBlox reference design, swapped the core to 2.0.1 and V250, and added a PID block. The reference design's constraints are mirrored in `workers/polarfire-hybrid-control/libero/constraints/icicle_reference/README.md`. The swap is recorded in `workers/polarfire-hybrid-control/docs/rung_f_v250_post_program_handoff_2026-06-16.md`.

The scripts for Path B sit in `workers/polarfire-hybrid-control/libero/scripts/two_slot/`, and they run in this order.
1. `patch_two_slot.py` patches the generated netlist and adds the PID subsystem at address `0x60040000`.
2. `build_two_slot_synth.tcl` imports the new HDL and synthesizes.
3. `build_two_slot_pnr.tcl` runs place and route and timing, then exports the `.job` programming file.
4. `rebuild_idfix2.tcl` is the later rebuild, where I added the M0 AXI completion fix and the actuator output latch.

If you only want the NPU, you don't need the PID. The V250 control page sits at `0x60030000` in both paths (`workers/polarfire-hybrid-control/firmware/linux/two_slot_vbx_pid.dtso`). The repo has no script that builds a V250-only image. That step is manual.

Run each Tcl file headless, in the form the header of `build_two_slot_synth.tcl` gives.

```
libero "SCRIPT:<work-dir>/build_two_slot_synth.tcl"
```

The same header says Tcl needs Windows-style paths. The scripts flush stdout after every stage and wrap each stage in `catch`, so a hang shows where it stopped.

## 5 Program the kit

FlashPro Express, a separate tool from Libero, does the programming. `program_two_slot_idfix2.tcl` runs the PROGRAM action only. It leaves eMMC, sNVM, HSS, U-Boot and Linux alone, and it refuses any job whose name lacks `two_slot_idfix2`. Its header gives the call.

```
/c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/fpexpress.exe \
  SCRIPT:"<work-dir>/program_two_slot_idfix2.tcl" \
  LOGFILE:"<work-dir>/two_slot_reports/program_idfix2.log"
```

For a first programming of a stock kit, `workers/polarfire-hybrid-control/libero/scripts/program_kit.tcl` is the simpler script. It reads a `.job` file, finds the FlashPro6 on the board and programs it.

Before you program, record the hash of the job you'll replace and the exact rollback command. I did that before every persistent change (`workers/polarfire-hybrid-control/README.md`).

Linux is the next step, and it's manual in the repo.
1. Decompress the image first with `gunzip -k mchp-base-image-mpfs-icicle-kit.rootfs-20260430113402.wic.gz`. A `.wic.gz` written straight to the card can corrupt the boot (`workers/polarfire-hybrid-control/firmware/linux/README.md`).
2. Write the `.wic` to the SD card with `dd` or USBImager, and check the device name twice.
3. Set the kit to boot from SD, then press RESET. The chain is HSS, then U-Boot, then Linux, and the login is `root`.

## 6 Run inference from Linux

Linux runs on the U54 cores and reaches the NPU through two kernel features (`workers/polarfire-hybrid-control/README.md`).

- `generic-uio` exposes the V250 control page as `/dev/uioN`.
- `/dev/udmabuf-ddr-nc0` provides non-cached DDR buffers for the model and the input and output data.

A device-tree overlay creates the UIO node, and `two_slot_vbx_pid.dtso` is the one for the two-slot image. Don't use `seed7_vbx_pid.dtso` on that image, because it also maps `0x60001000`, the DMA controller page described under Traps (`workers/polarfire-hybrid-control/firmware/linux/README.md`). Build and apply the overlay on the kit, every boot, with the commands from the header of `two_slot_vbx_pid.dtso`.

```bash
dtc -@ -O dtb -o two_slot_vbx_pid.dtbo two_slot_vbx_pid.dtso \
    -Wno-reg_format -Wno-avoid_default_addr_size
mkdir -p /sys/kernel/config/device-tree/overlays/two_slot
cat two_slot_vbx_pid.dtbo > /sys/kernel/config/device-tree/overlays/two_slot/dtbo
```

Then check that the node and the buffer exist.

```bash
ls -l /dev/uio*
cat /sys/class/uio/uio*/name
ls /dev/udmabuf-ddr-nc0
```

One uio name should read `vbx` (`workers/polarfire-hybrid-control/firmware/linux/README.md`).

Build the test program on the tools host. The cross compiler is a Cygwin build and exits 127 without `cygwin1.dll` on the path, so set the path first. The lines come from `workers/polarfire-hybrid-control/firmware/linux/Makefile`.

```bash
SHLS=/c/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS
export PATH="$SHLS/swtools/binutils/riscv-gnu-toolchain/bin:$SHLS/dependencies/lib/cygwin:$PATH"
make CROSS=riscv64-unknown-linux-gnu- VBX_SDK=/c/Microchip/VectorBlox-SDK
```

Copy the program, the model and the overlay to the kit with the runbook's `scp` line.

```bash
scp pid_poke vnnx_smoke fcnn_v2_residual_dataset_a.vnnx seed7_vbx_pid.dtbo root@<target-ip>:/root/
```

Use it as a pattern. Send your own `.vnnx` and the `two_slot_vbx_pid.dtbo` you built, and skip `pid_poke`. Then run the test on the kit.

```bash
./vnnx_smoke fcnn_v2_residual_dataset_a.vnnx
```

`workers/polarfire-hybrid-control/firmware/linux/vnnx_smoke.c` runs these steps in order.

1. `vbx_cnn_init(NULL)` scans `/sys/class/uio/uioN/name` for `vbx`, maps the control page, and maps the udmabuf pool.
2. It reads the `.vnnx` file and copies it into a DMA buffer sized by `model_get_allocate_bytes`.
3. It points the input at the test vector embedded in the model, and allocates output buffers.
4. `vbx_cnn_model_start` begins the run, and `vbx_cnn_model_poll` spins until it ends. Interrupts are off on the Icicle build (`-DUSE_INTERRUPTS=0`).
5. It dequantizes each INT8 output as `(q - zero_point) * scale_fix16 / 65536`.

That poll loop never ends if the NPU stalls, so I run `workers/polarfire-hybrid-control/firmware/linux/vbx_probe.c` first. It's the bounded variant, and it prints the control, error and version registers at each stage.

`vnnx_smoke` uses only the embedded test input. To feed your own data, quantize it with the input scale and zero point that the `.vnnx` stores, and write it into the input buffer. `workers/polarfire-hybrid-control/firmware/linux/v250_pid_loop.c` does this for CSV rows, but it also drives the PID registers, so it needs the two-slot image. There's no standalone "run my input" program in the repo. That step is manual.

## 7 Check the result

On my kit the model's test vector gave `out[0]=-2.9506` at scale 0.022873 and zero point 1 (`workers/polarfire-hybrid-control/firmware/linux/README.md`). In the print format of `vnnx_smoke.c`, that run reads like this.

```
V250 control plane alive (vbx_cnn initialized).
model: 1 input(s), 1 output(s)
inference complete.
out[0] len=1 scale=0.022873 zp=1: -2.9506
```

`vbx_probe` should end with `RESULT: INFERENCE COMPLETED` and `VER=0x20000000`. In that version word, major 2 and size 0 mean CoreVectorBlox 2.0 and V250. The control register moves from `0x00` to `0x04` to done, and `ERR` stays 0 (`workers/polarfire-hybrid-control/docs/rung_f_v250_on_silicon_results_2026-06-16.md`).

For timing, `vnnx_latency` takes a model, a sample count and a warmup count (`workers/polarfire-hybrid-control/firmware/linux/vnnx_latency.c`). My run used 1,000 samples and 20 warmups, and start plus poll had a median of 32 µs and a p99 of 33 µs (`workers/polarfire-hybrid-control/libero/reports/2026-06-21-latency/vnnx_latency_2026-06-21.txt`). The report header shows `rdcycle=0`, `rdtime=1` and a 1 MHz timebase, so the number is an on-kit API bound at 1 µs resolution and says nothing about V250 core cycles (`workers/polarfire-hybrid-control/libero/reports/2026-06-21-latency/README.md`).

Accuracy needs a separate check. My float-versus-INT8 harness runs the TFLite file on a CPU, and with it I measured an INT8-versus-float mean absolute error of 0.0346 µT on the test split (`workers/odmr-edge-ml/README.md`). The kit's output on the same inputs is a second comparison, and you have to run that one yourself.

I write every run to a report folder, and that habit paid off. Each bring-up run in this repo has its own folder under `workers/polarfire-hybrid-control/libero/reports/`, named by date, with logs, the hashes of the binaries and a README that states what the numbers do and don't prove. The 2026-06-21 latency folder is a small example of the shape, and `workers/polarfire-hybrid-control/tools/audit_libero_reports.py` audits such a folder.

## Traps

- My first bitstream carried CoreVectorBlox 1.1.12 (V500) while the software targeted 2.0.1 (V250). Inference started and the control register stuck at `0x02` forever. The 2.0.1 rebuild fixed it (`workers/polarfire-hybrid-control/docs/rung_f_v250_on_silicon_results_2026-06-16.md`). Read the version register at `0x60030028` before you debug anything else.
- A float operator left in the graph is the other export failure. The converter settings in step 2, `TFLITE_BUILTINS_INT8` with INT8 input and output, keep them out.
- If you write the fabric side in SmartHLS, the fixed-point type is `hls::ap_fixpt<W,I>`. `ap_fixed` is the Xilinx name (`workers/polarfire-hybrid-control/AGENTS.md`).
- Headless Tcl needs Windows-style script paths and plain `run_tool -name {SYNTHESIZE}`. Don't run parallel synthesis from cloned projects. Setting `RANDOM_SEED` in batch Tcl did not change placement (`workers/polarfire-hybrid-control/libero/scripts/parallel/README.md`).
- The `0x60001000` page is the DMA controller, and one read there wedged a U54 core, so leave that page alone.
- After my V250 rebuild, Linux hung in the `microchip-pcie` probe at `0x3000000000`. The workaround was a boot-time `fdt set` that disables the node, and the details are in `workers/polarfire-hybrid-control/docs/rung_f_v250_on_silicon_results_2026-06-16.md`. A V250 run doesn't need PCIe.
- A stale `workers/polarfire-hybrid-control/firmware/README.md` still says the firmware is bare-metal and a placeholder, but the Linux path in `firmware/linux/` replaced it.

## The other route

hls4ml merged a Libero backend in January 2026, and it shipped in release v1.3.0 on 2026-03-20. It handles Dense layers only and builds on SmartHLS, and its pull request #1240 calls it an initial implementation that is not feature complete. Those facts come from the hls4ml project itself, and I haven't run the backend.

It builds the network as fabric logic, so the V250 soft NPU isn't involved. In this repo the MLP uses Dense layers (`nn.Linear` in `workers/odmr-edge-ml/src/odmr_edge_ml/models/mlp.py`), so both routes apply to it. The FCNN, which is `Conv2d` only (`workers/odmr-edge-ml/src/odmr_edge_ml/models/fcnn.py`), fits only the V250 route.

For the measured results on the kit, see `workers/polarfire-hybrid-control/README.md`.
