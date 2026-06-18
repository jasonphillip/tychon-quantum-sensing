# Two-Slot Demo — Scope, Evidence & Honest Claims (2026-06-18)

Demo-readiness statement for the clean two-slot PID + V250 bitstream on the Production MPFS250T
Icicle Kit (branch `bringup/2026-06-17-two-slot-pid`, demo `.job` sha256 `a5550f9e…`). Evidence
labels per `docs/agent_ground_truth_contract.md`. Full engineering log:
`docs/two_slot_handoff_2026-06-17.md` (2026-06-18 sections).

## Demo claim — exact wording (use this; do not overstate)

> On Production silicon this bitstream proves: **CoreVectorBlox V250 inference**, a **clean
> two-slot PID/control telemetry plane** (the `pid_csr` "M1" sub-slave), and a **live hardware
> watchdog / bumpless-transfer safety path**. The **live closed-loop actuator output through the
> M0 gains sub-slave is deferred**, because the **M0 gains slave has a silicon-observed AXI
> completion defect** (reads to `0x60040000…0x600407ff` do not complete). Closed-loop actuator
> dynamics are shown in the **software dashboard**; the **silicon** telemetry is the
> **control-plane + safety** path, honestly labeled.

- **Do** claim, on silicon: V250 inference; clean M1 PID/control telemetry; live watchdog safety.
- **Do NOT** claim, on silicon: a live closed-loop actuator output (it is M0-gated; see below).

## What is PROVEN on silicon (CONFIRMED, 2026-06-18)

| Item | Evidence |
|---|---|
| **V250 inference (Rung F)** | `vbx_probe` → `INFERENCE COMPLETED` (CTRL `0x00→0x04→done`, `error_val=0`, `VER=0x20000000`); `vnnx_smoke` → `out[0]=-2.9506`. **Requires a cold power-cycle after programming** (V250 POR; warm reset insufficient — confirmed across 2 cold boots). |
| **Clean M1 `pid_csr` control plane (Rung E)** | `csr_version=0x00010000`; `axi_write_count` monotonic (0→9 exact; +4/row under streaming); shadow-gain write/readback **bit-exact** (0.5→`0x8000`, 0.25→`0x4000`). A real decoded crossbar slave (vs the severed seed_7 eavesdropper). |
| **Watchdog / safety path** | `watchdog_csr=0x07` = bit0 timeout + trip count 3 — **LIVE**. With no recent V250 `output_valid`, the controller correctly enters **pure-PID bumpless fallback** (`mode=PID_ONLY_FALLBACK`). |
| **Rung G telemetry** | Software dashboard `sim/rung_g/rung_g_dryrun_2026-06-18.{csv,jsonl,png}` (120 rows, 16 clamp-active) + on-silicon per-row CSR liveness `…silicon_2026-06-18.*` (30 rows; write-counter climbs, watchdog live; `actuator_out=0`, M0-gated). |

## What is DEFERRED — the M0 gains-slave defect

- **Symptom (CONFIRMED, silicon):** any read of the M0 gains slave (`nv_pid_top.axi4target`,
  `0x60040000–0x600407ff`; incl. `acc_start` `0x60040008`, gains `0x6004000C–0x6004001C`) issues a
  **non-completing AXI transaction** → hangs a U54 hart → kit drops off the LAN (power-cycle to
  recover). M1 (`pid_csr`, `0x60040800+`) is unaffected.
- **Consequence (CONFIRMED, source):** `hls/src/nv_pid.hpp:21` resets `out_min/out_max` to `0`;
  `compute()` clamps the final output to `[out_min,out_max]` = `[0,0]` until those limits are
  written — and the limits are **M0-only**. So `post_clamp_out` stays `0` → **no nonzero live
  actuator without M0 access**.
- **HYPOTHESIS (root cause to fix):** the hand-written `axi4_demux2` M0 branch mis-handles the AXI
  **read-response** (R-channel / RID — `nv_pid_top` 1-bit ID vs the 9-bit demux side) and/or
  SmartHLS `ap_ctrl` gating. M0 was never read-tested on silicon before 2026-06-18; the 2026-06-17
  "both decoded clean" was an expectation, now **FALSIFIED for M0 reads**.

## Follow-up — path to a LIVE silicon closed-loop actuator (deferred; requires a rebuild)

1. **Fix `axi4_demux2` M0 read/write response handling** in RTL: verify the R-channel + RID and
   the B-channel for BOTH sub-slaves of the SLAVE3 (`0x60040000`) 1→2 splitter. Bench/sim the
   demux with reads to **both** M0 and M1 (and the ID pad/truncation) before synth — do not rely
   on synth survival alone.
2. **Rebuild + reprogram** the two-slot bitstream (synth → P&R → timing → export `.job` →
   FPExpress program). Preserve the current demo `.job` `a5550f9e…` and the rollbacks
   (V250 `4e3323e8…`, seed_7 `d5f3eb4e…`); capture before/after hashes.
3. **Cold power-cycle** after programming (mandatory for V250 init — the 2026-06-18 standing rule).
4. **Bounded first-contact M0 validation BEFORE enabling the actuator:** a single `timeout`-wrapped
   read of a M0 gains reg (e.g. `0x6004000C`); proceed only if it **completes** (no hang). Then set
   `out_min/out_max` + gains via M0 and confirm via M1 `post_clamp_out`.
5. **Then** run the full live closed-loop actuator replay (Rung G with a real, nonzero actuator).

> Note: the "write-only M0 probe" alternative was **explicitly declined** for the 2026-06-18
> session — no M0 access at all (read or write).

## Artifacts / rollback
- Demo `.job` `a5550f9e…` (bee `export/` + NAS; Fabric+sNVM only). Rollbacks: V250 `4e3323e8…`,
  seed_7 `d5f3eb4e…` (hash-verified, bee + NAS).
- Kit tools: `/root/bringup/{vbx_probe,vnnx_smoke,pid_ctl}` + `fcnn_v2_residual_dataset_a.vnnx`.
- Telemetry: `sim/rung_g/*2026-06-18*`.
