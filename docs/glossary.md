# Glossary

Terms used across this repository, grouped by area. The [primer](primer.md) explains the sensor in more depth.

## Sensing and physics

| Term | Meaning |
|---|---|
| NV center | Nitrogen-vacancy center: a defect in diamond, a nitrogen atom next to a missing carbon atom. Its electron spin responds to magnetic fields. |
| ODMR | Optically detected magnetic resonance. The NV spin is read through its red fluorescence while a microwave signal is swept; the glow dims at the spin resonance. |
| CW-ODMR | Continuous-wave ODMR: laser and microwave stay on while the frequency is swept. |
| MW | Microwave. The swept signal near 2.87 GHz. |
| Zero-field splitting | The 2.87 GHz spacing of the NV spin levels when no field is applied. Temperature shifts it slightly. |
| Zeeman splitting | The split of each resonance dip in a magnetic field, about 28 MHz per millitesla. |
| Bias field, bias axis | A fixed applied field that separates the dips of the four NV orientations. "Off the bias axis" is the angle between the measured field and that axis. |
| Line crossing | Dips from different NV orientations moving past each other as the field changes. A tracker that follows frequencies can swap them. |
| Lock-in amplifier | The classic way to follow one resonance: modulate, demodulate, and feed the error to a PID loop. |
| Allan deviation | A measure of sensor noise and drift against averaging time. |
| SimOS | The open-source spin-dynamics simulator that the simulator wraps. |
| CUDA-Q | NVIDIA's quantum programming toolkit. Studied for a GPU backend that is still a stub. |

## FPGA and toolchain

| Term | Meaning |
|---|---|
| FPGA | Field-programmable gate array: a chip whose logic is configured after manufacture. |
| SoC | System on chip. Here, processor cores and FPGA logic on one die. |
| PolarFire SoC | Microchip's FPGA family with RISC-V processor cores. |
| MPFS250T | The PolarFire SoC device on the Icicle kit. |
| Icicle kit | Microchip's PolarFire SoC development board. The only FPGA target in this project. |
| MSS | Microprocessor subsystem: the RISC-V cores and their peripherals on the PolarFire SoC. The control loop software runs here. |
| HSS | Hart Software Services: the boot and monitor firmware that runs on the MSS before Linux. |
| Fabric | The programmable logic of the FPGA, as opposed to the MSS. |
| FIC | Fabric interface controller: the bus bridge between the MSS and the fabric. |
| Bitstream | The file that configures the fabric. |
| Two-slot bitstream | The FPGA build used for the demo, with the PID controller and the V250 engine together. See [the scope note](../workers/polarfire-hybrid-control/docs/two_slot_demo_scope_2026-06-18.md). |
| Libero SoC | Microchip's FPGA design suite: synthesis, place-and-route, timing and programming. |
| SmartHLS | Microchip's high-level synthesis tool: C++ in, RTL out. |
| HLS, RTL | High-level synthesis; register-transfer level, the hardware description that synthesis consumes. |
| P&R | Place-and-route: mapping the synthesized design onto the chip and checking its timing. |
| VectorBlox | Microchip's neural-network accelerator IP and SDK for PolarFire. |
| V250 | The CoreVectorBlox configuration used here. |
| .vnnx | A network compiled by the VectorBlox SDK for the accelerator. |
| QuestaSim, ModelSim | HDL simulators used to test the generated RTL. |
| Yocto | The Linux build system behind the kit's Linux image. |
| PID | Proportional-integral-derivative controller, the classic feedback loop. |
| Watchdog | A fabric timer that detects a missed network deadline so the controller can hand over to plain PID. In the 2026-10-09 board test the handover worked when the next update saw the timeout, and not when the timeout cleared first. |
| RTA | Run-time assurance: a simple trusted controller bounds a complex one and can take over. Here PID, a clamp on the network's output and the watchdog. |
| HIL | Hardware in the loop: the kit runs the controller against recorded or replayed sensor data. |
| Soak test | A long run, here 8 hours, to catch stalls, drift and memory growth. |

## Machine learning

| Term | Meaning |
|---|---|
| FP32 | 32-bit floating point, the usual training precision. |
| INT8 | 8-bit integers, the precision the VectorBlox engine runs. |
| QAT | Quantization-aware training: training that simulates INT8 rounding so the network copes with it. |
| ONNX, TFLite | Model exchange formats on the way from PyTorch to the VectorBlox compiler. |
| MAE, RMSE | Mean absolute error and root mean squared error. |
| Kalman filter | A classic state estimator. Used as a stronger classical baseline for the tracker. |
| MMD, KS, sliced-Wasserstein | Two-sample tests that ask whether simulated and measured spectra come from the same distribution. |
| Pre-registered verdict | A pass/fail rule written and committed before the run it judges. |

## Orchestration and claim checks

| Term | Meaning |
|---|---|
| Orchestrator | The agent session that plans work and sends it to the repositories. See [orchestrator/](../orchestrator/). |
| Worker | The agent session that owns one repository and does the work there. |
| Dispatch | A written task from the orchestrator to a worker, with a goal, an acceptance check and a predicted effort. |
| Claim | One factual statement extracted from a report, to be checked against evidence. |
| Critic | A local language model that judges a claim against retrieved evidence. |
| Stop-gate | The check at the end of each pipeline stage. Work stops there until the gate passes. |
| Ollama, NIM | Two ways to serve models locally. The critics ran on Ollama; the NIM route was planned and skipped. |

## Lab

| Term | Meaning |
|---|---|
| DGX Spark | NVIDIA's desktop machine with a GB10 Grace Blackwell chip and 128 GB of unified memory. Four of them over time; see the [lab page](lab.md). |
| ConnectX-7, RoCE | The 200 Gb/s network cards linking the Sparks, and the RDMA protocol they run. |
| NUT | Network UPS Tools: lets one machine tell the others to shut down when the UPS runs low. |
