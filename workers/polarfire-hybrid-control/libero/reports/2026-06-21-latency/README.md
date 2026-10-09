# 2026-06-21 Latency Bundle

Status: CONFIRMED on-kit helper bounds, not pure cycle latency.

Contents:

- `vnnx_latency_2026-06-21.txt` - output from `/root/bringup/vnnx_latency fcnn_v2_residual_dataset_a.vnnx 1000 20`.
- `pid_latency_2026-06-21.txt` - output from `/root/bringup/pid_latency 5000 100`.

Both helpers report `rdcycle=0`, `rdtime=1`, and `timebase_hz=1000000`, so the numbers are on-kit API/MMIO bounds. They are not internal V250 core cycles or pure fabric PID cycles.

Source helpers:

- `firmware/linux/vnnx_latency.c`
- `firmware/linux/pid_latency.c`

Target binary hashes used on the kit:

```text
a9752426ca834a2deee72bb0403c965958e4a0fa63c45c1d146ac6e86154f32c  vnnx_latency
5e1485fa94c1ed7cf6fbdc346e36da59eda9e2707cbc1bdce3f02184b0127930  pid_latency
```
