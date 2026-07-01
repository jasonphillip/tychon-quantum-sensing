# Latency Measurements - 2026-06-21

## Summary

These measurements were taken against the currently resident idfix2 hardware on
the Icicle kit. The best rows now come from on-kit C helpers, not SSH process
startup loops.

Important caveat: userspace `rdcycle` traps on this Linux image, so both helper
binaries report `rdcycle=0` and fall back to `rdtime=1` with a 1 MHz timebase.
The numbers below are therefore on-kit API/MMIO timing bounds, not U54 cycle
counts and not pure fabric/V250 internal cycle latency.

| Path | Method | n | min | median | p99 | max | Claim label |
|---|---|---:|---:|---:|---:|---:|---|
| V250 model start + poll to complete | `/root/bringup/vnnx_latency`, on-kit helper around `vbx_cnn_model_start` and poll | 1000 | 31 us | 32 us | 33 us | 58 us | CONFIRMED on-kit API/start+poll bound |
| idfix2 PID M0 start pulse + M1 `post_clamp_out` read | `/root/bringup/pid_latency`, on-kit helper, M0 allowlist writes only | 5000 | 3 us | 4 us | 4 us | 50 us | CONFIRMED on-kit MMIO pulse/read bound |
| Dashboard/rung-G host-paced loop period | `tools/rung_g_replay.py --host icicle --rows 120`, `t_host` deltas | 119 | 6739 us | 10122 us | 15412 us | 15658 us | CONFIRMED host-visible replay period |

Older host-visible helper-process rows remain useful as acceptance bounds for
CLI smoke scripts, but they include process startup and helper setup:

| Path | Method | n | min | median | p99 | max |
|---|---|---:|---:|---:|---:|---:|
| V250 `vnnx_smoke` helper process | one SSH session, remote `date +%s%N` around each process | 30 | 760.776 ms | 761.767 ms | 762.981 ms | 762.981 ms |
| V250 `vbx_probe` helper process | one SSH session, remote `date +%s%N` around each process | 20 | 765.995 ms | 766.528 ms | 768.069 ms | 768.069 ms |
| Dashboard-style two-compute sample | persistent `pid_ctl repl`; error write, PID-only pulse/read, PID+NN pulse/read, counter read | 120 | 5537.5 us | 9121.7 us | 12970.1 us | 13245.2 us |

## Helper Artifacts

- `firmware/linux/vnnx_latency.c`
- `firmware/linux/pid_latency.c`
- `libero/reports/2026-06-21-latency/vnnx_latency_2026-06-21.txt`
- `libero/reports/2026-06-21-latency/pid_latency_2026-06-21.txt`

Binary hashes copied to `/root/bringup` during this run:

```text
a9752426ca834a2deee72bb0403c965958e4a0fa63c45c1d146ac6e86154f32c  vnnx_latency
5e1485fa94c1ed7cf6fbdc346e36da59eda9e2707cbc1bdce3f02184b0127930  pid_latency
```

## Commands

Build/copy was performed on bee using the SmartHLS-bundled RISC-V Linux
toolchain and the installed VectorBlox SDK, then the binaries were copied to the
kit under `/root/bringup`.

```bash
ssh icicle 'cd /root/bringup; timeout 30 ./vnnx_latency fcnn_v2_residual_dataset_a.vnnx 1000 20'
```

Key output:

```text
vnnx_latency model=fcnn_v2_residual_dataset_a.vnnx samples=1000 warmup=20 rdcycle=0 rdtime=1 timebase_hz=1000000
error_val=0 out0=-2.950607
total_ns min=31000 median=32000 p95=33000 p99=33000 max=58000
total_ticks min=31 median=32 p95=33 p99=33 max=57
```

```bash
ssh icicle 'cd /root/bringup; timeout 30 ./pid_latency 5000 100'
```

Key output:

```text
pid_latency samples=5000 warmup=100 rdcycle=0 rdtime=1 timebase_hz=1000000
csr_version=0x00010000 watchdog_raw=0x00000081
post_clamp_raw=0x00003439 post_clamp=0.203995 axi_write_count=0x0000401a
pulse_read_ns min=3000 median=4000 p95=4000 p99=4000 max=50000
```

```bash
python3 tools/rung_g_replay.py --host icicle --rows 120 --out /tmp/latency_rung_g_120
```

## Caveats And Next Step

- `vnnx_latency` measures the SDK start/poll path visible from userspace. It
  confirms a tight on-kit bound for one already-loaded `.vnnx` invocation, but
  it does not expose internal V250 core cycles.
- `pid_latency` maps only `0x60040000`, writes only the idfix2 M0 allowlist
  registers plus M1 error/feedforward registers, and reads M1 `R_POST_CLAMP`.
  It does not touch `0x60001000`.
- A pure fabric latency claim still needs either a readable hardware cycle
  counter latched from `acc_start` to actuator-valid or a post-layout simulation
  measurement tied to the idfix2 netlist.
