# Whole-Process Strategy Audit (2026-06-02)

**Why this exists.** Discovering that an early default (bare-metal vs Linux for NN inference) was likely the *wrong* choice prompted a step back: are there **other** inherited-default choices in the bring-up that don't serve the actual intent? This audit answers that. It was produced by a skeptical-architect research pass over the repo + corpora + web (paid APIs: exa + tavily; firecrawl MCP was not connected this session).

**The intent (restated):** convince a *technical reviewer* that a bounded-safe PID (in fabric) + on-chip NN (CoreVectorBlox V250) hybrid controller works on **real MPFS250T silicon**, with **measured** power and inference latency, applied to ODMR frequency tracking.

**Verification legend:** **[V]** = verified against repo/corpus/web this session · **[NC]** = needs-check (flagged, not assumed).

**Bottom line up front:** the approach is *sound in its hardest part and miscalibrated in its framing*. The genuinely hard assets are real and rare (timing-closed bitstream with V250 in fabric, compiled `.vnnx`, confirmed Production silicon, an honest safety doc, a disciplined evidence trail). But **three inherited defaults pull against the reviewer intent**, all fixable now at modest cost. In priority: (1) replace the eavesdropper bitstream with the clean two-slot integration; (2) move the whole MSS-software side (C–G) to Linux; (3) reframe the demo artifact from "replayed CSV" to "the loop closes + the safety mechanism catches a fault."

---

## Risk 1 — The "eavesdropper" bitstream is the demo's biggest credibility liability [V] · highest leverage

**Issue.** The demo runs the seed_7 `MPFS_ICICLE_Vectorblox` reference bitstream with `pid_io_block` bolted on as an *eavesdropper*: its AXI read-channel response is tied to an LED OR-tap, so **the MSS cannot read the PID's registers** (reads fall through to `nv_pid_top_top`'s slave), and **writes collide** — writing `Kp` at `0x0C` also drives `error[63:32]`; writing `acc_start` at `0x08` also drives `error_low` (per `docs/fic_0_address_map_2026-05-18.md`, `docs/seed_7_register_map_2026-05-04.md`).

**Why it undermines rung E specifically.** Rung E is sold as "AXI register loopback / write-then-readback" — and the project's own framing elevates software write-then-readback to *"the architectural proof of survival."* But the eavesdropper can only cleanly round-trip on **three** addresses (`Kd`/`out_min`/`out_max`); the headline gains `Kp`/`Ki` are aliased to stimulus inputs and the read path is severed. A reviewer's engineer who opens the netlist sees a severed read path + overlapping decode and concludes *"this is a tap hack, not an integration."* Needing to **narrate caveats during a demo is itself the tell.**

**Recommendation.** Do the clean two-slot SmartDesign integration that is **already scoped** (`docs/smartdesign_two_slot_canvas_runbook.md`, `libero/hdl/pid_csr_block.v` with 18 real CSRs incl. `csr_version=0x00010000` at a stable offset) **before** the reviewer-facing pass — at minimum before rung E/I. The HDL is already testbench-validated (D.1/D.2/D.3 pass per CLAUDE.md), just not netlist-validated.

**Cost/benefit.** Cost: one Libero GUI canvas session + re-synth/re-P&R/re-export (~50 min sweep infra already proven) + re-program. Benefit: converts the single most-scrutinized rung from "explainable hack" to "clean integration" and removes the write-collision caveats. **Highest-leverage change in the audit.** Fallback if schedule forbids: demo only the 3 clean addresses, never show `Kp`/`Ki` writes — honest but weaker. *Couples to Risk 6: a re-integration forces a re-export AND re-extraction of the axi4target offsets — guard the SmartHLS register-packing drift.*

---

## Risk 2 — Go Linux for the whole MSS-software side (C–G), not just inference (F) [V]

**Issue.** The inherited default is bare-metal for everything; the rung-F research already flips F to Linux. The same logic extends to C–E.

**Evidence.** Per `docs/rung_f_vectorblox_inference_research_2026-06-02.md` [V]: the only Microchip-supported V250 path boots Yocto (UIO `/dev/uioN` + udmabuf-nc + dma-proxy); bare-metal F means hand-rolling DDR bring-up + an uncached allocator + **fabric-master-to-L2 cache coherency that Microchip does not document** (the byte-deterministic failure class this project's debugging rules dread). Web confirms it: Microchip support #000017296 validates VectorBlox 2.0.3 on the **production Icicle Kit via Yocto `.wic` only** [V]. Going Linux unifies the demo into one userspace program (poke PID CSRs via `/dev/mem`/UIO, run inference via the SDK, stream CSV) — and the **safety/real-time story is unaffected because it lives entirely in fabric** (HLS datapath, 200 MHz watchdog counter, clamps); the MSS is supervisory only [V].

**Notable finding.** The README's stated rationale for bare-metal — *"Linux jitter violates the <150 µs guarantee"* — is **incoherent with the architecture**: the <150 µs loop is the *fabric* PID, not MSS software. That line is a stale inherited justification and should be corrected.

**Recommendation.** Adopt Linux for C–G. **SD-card boot is non-destructive and takes precedence over eMMC** [V], so iteration is cheap and the destructive-eMMC concern (Part-J) largely evaporates. Prebuilt Icicle images exist (`linux4microchip/meta-mchp` releases — the old `meta-polarfire-soc-yocto-bsp` is **archived** [V]).

**Cost/benefit.** Cost: ~½–1.5 days Yocto/SD setup + abandoning partial SoftConsole bare-metal scaffolding (small sunk cost). Benefit: removes the **single largest technical risk** in the plan (multi-day cache-coherency stall) and arguably yields a *more* credible artifact ("here's the chip, ssh in, run it"). **[NC]:** confirm the seed_7 MSS config still has MMC/eNVM-HSS enabled (the VectorBlox merge could have disabled them).

---

## Risk 3 — UART-CSV + offline plot vs a synthetic baseline is the weakest defensible artifact [V]

**Issue.** The demo medium (stream CSV over UART, plot in Python vs a *synthetic* baseline) proves the datapath runs, but the comparison is silicon-vs-simulation *of your own model* — it does not show the controller controlling anything.

**Benchmark.** The gold-standard comparable is the SensorsINI **CartPole / F1TENTH FPGA neural-controller** (arXiv 2407.08681): a NN imitating MPC on a cheap FPGA, shown **closing a physical loop at kHz**, with public code/hardware [V]. Peer-reviewed FPGA NN-PID HIL motor/generator papers (MDPI Sensors 22/889; ACCENTS SG-excitation HIL) are the same shape. The differentiator in all of them is a **closed loop**, not a replayed trace.

**Recommendation (tiered — do as many as fit):**
- **(a) minimum** — keep the CSV but make the plot **closed-loop in software**: feed the actuator output back through a plant model on the host so the trace shows error *converging*, and overlay **PID-only vs PID+NN** to make the NN's value legible. (hours; strictly improves the existing artifact)
- **(b) strong** — the **LED/PWM tracking control-effort (rung H)** as the visceral 30-s video. This is the CartPole-equivalent and is cheap (already planned).
- **(c) strongest realistic** — a tiny **hardware-in-the-loop**: emulate the ODMR plant on the host (or a 2nd MCU) so the kit drives a setpoint and the loop visibly locks; record it.

Real optical ODMR HIL (NV magnetometer in loop) is the most convincing but out of scope/cost for a demo (it is the open RPO-1).

**Cost/benefit.** Pivot the *framing* from "we replayed a trace" to "the loop closes," using software-in-the-loop convergence + the LED video. Low cost, large credibility delta.

---

## Risk 4 — Icicle/V250 is the correct choice, but mind two concrete gotchas [V]

**Finding.** The SDK's *supported examples* target the Video Kit (V1000); Icicle/V250 is less trodden — but this is **not** a credibility problem. Icicle is the right platform (matches the silicon, ODMR is not a vision demo, lower power). Web confirms two hard facts:
1. Microchip explicitly validated VectorBlox 2.0.3 on the **production Icicle Kit (MPFS250T) with V500/V250**, and warns **"a VNNX generated with V1000 cfg will NOT work on Icicle"** — the project's `-c V250` compile pin is correct and load-bearing [V].
2. That same validation **recommends dropping the VectorBlox core clock to 75/150 MHz** (from 100/200) on Icicle for timing closure [V].

**Recommendation.** Treat the 200 MHz fabric-clock assumption for the V250 path as **[NC]** against the seed_7 closure — if Microchip de-rated to 150 MHz for V250 on Icicle, the timing-closure clock domain and **any 200 MHz-derived latency math must be re-checked.** Also: the published validation used **V500**; confirm V250 (our model is a tiny 12.5 KB FCNN) doesn't change IO scaling.

**Cost/benefit.** A few hours cross-checking clock + reg base (`0x60030000`, IRQ 124) against the seed_7 map. Avoids a falsifiable latency claim and a subtle timing violation that only bites on real silicon.

---

## Risk 5 — The safety story is asserted, not demonstrated [V]

**Issue.** The Lur'e/Circle-Criterion sector-bound is the *intellectual* differentiator, but the demo plan never *exercises* it. Six Residual Proof Obligations are explicitly open (plant ID, ZOH phase margin, transport delay, derivative-filter SI, ReLU sector verification, workload SmartPower), and `safety_architecture.md` flags that the signal path has **no valid/ready handshake** (a stale inference is indistinguishable from a fresh one). A reviewer's controls reviewer will ask *"show me the clamp/watchdog firing"* — and currently nothing in A–I does.

**Recommendation.** Make safety **demonstrable** with a scripted adversarial segment:
- inject an out-of-sector / oversized NN output and **show the ±5% clamp + slew limiter visibly bound it** in the trace;
- **stall the inference path and show the 1 ms watchdog trip → bumpless transfer to pure PID** with no actuator discontinuity (the `tb_bumpless` logic already exists — promote it to a live on-silicon stunt).

Pair with an honest caveat card listing the 6 open RPOs as the funded-work roadmap (reviewers reward *known* gaps over hidden ones).

**Cost/benefit.** ~half-day firmware/host stimulus mode reusing existing clamp/watchdog HDL. Turns the paper-stability claim into the demo's most differentiated moment.

---

## Risk 6 — Toolchain/version pins: two real biters, one resolved [V]

- **SmartHLS register-packing drift [V, active] — highest-probability silent firmware bug.** The May-17 RPO-4 HLS rebuild is **NOT** the bitstream version; firmware must be authored against the **Apr-28** `tychon-polarfire-control` driver or the `axi4target` offsets are wrong (`docs/fic_0_address_map_2026-05-18.md`). If you re-integrate (Risk 1) you must re-export **and** re-extract offsets. **Guard this.**
- **ES-vs-Production silicon [V, resolved 2026-06-02].** The `.ppd` targets Production; the new kit (IDCODE `1F81A1CF`, no `_ES`) passes chain check. But the prior ES block proves the bitstream/silicon-class coupling is rigid — don't re-export against the wrong die.
- **VectorBlox SDK 2.0.3 / Python 3.10 / flatc 23.5.26 / WSL [V].** The working compile path is the WSL `~/vbx-env` venv (the documented `setup_vars.sh` fails on CRLF + missing py3.10 in MINGW64). Reproducible but fragile — keep it pinned.
- **SoftConsole 2022.2 [V].** Only matters if you stay bare-metal; adopting Risk 2 (Linux) drops SoftConsole off the critical path entirely.

---

## Cross-references

- Rung-F architecture detail: `docs/rung_f_vectorblox_inference_research_2026-06-02.md`
- Deployment mechanics (Linux path, bare-metal memory, compat matrix, the #000017296 content): `docs/vectorblox_deployment_reference_2026-06-02.md`
- Domain credibility (what the ODMR demo must show, NN value-add, latency reframe): `docs/odmr_demo_credibility_2026-06-02.md`
- Searchable: extended `polarfire-control-corpus` (deployment/demo) + `odmr-pnt-nv-docs` (NN/ODMR physics) — see those docs' "Sources" for ingested URLs.

## Recommended sequencing impact on the A–I plan

If the top-3 changes are adopted, the plan shifts from "bare-metal A→I" to: **re-integrate (clean CSR block) → re-export/re-extract → program → boot Linux from SD → one userspace program does PID-poke + V250 inference + ODMR replay → add the closed-loop framing + the scripted safety stunt → capture.** That is a different-shaped plan than the current `goal-take-the-existing-wobbly-hollerith.md`, and the decision should be made before plan day, not at the F1 gate.
