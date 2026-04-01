# Tychon PolarFire Control — Claude Code Context

## Project
Tychon AI SBIR Phase I proposal FX255-PCS02-0044 (not selected 2026-05-12, never a contract): FPGA implementation of hybrid PID+AI control loop on RT PolarFire SoC.
Solo founder, 90-day sprint. This is Repo 3 of a three-repo architecture.

## Authoritative Documents
- `docs/phase1-context/requirements.md` — Deliverable 3 requirements extracted from playbook
- `docs/phase1-context/safety_architecture.md` — Lur'e/Circle Criterion formal framing

## Local Reference Documents (not in git)
- `docs/reference/tychon_repo3_scaffold_spec.md` — scaffold decisions, PID code rationale, safety architecture checklist
- `docs/reference/tychon_microchip_toolchain_reference.md` — SmartHLS/Libero/VectorBlox versions and CLI commands
- `docs/reference/beelink-fpga-machine-snapshot-2026-04-01.md` — Beelink synthesis machine installed tools and setup status
- `docs/reference/tychon_phase1_decision_log.md` — all architecture and engineering decisions with rationale
- `docs/reference/tychon_post_scaffold_quickref.md` — ordered next steps and validation sequence

Read these at the start of any session involving architecture decisions, SmartHLS pragmas, or cross-machine workflow. These files are gitignored — they exist only on local machines.

## What This Repo Does
- SmartHLS C++ PID controller with bumpless AI→PID transfer
- Sector saturation clamps (±5%) and slew-rate limiting on AI output
- Hardware watchdog (200 MHz counter, 1 ms timeout)
- Libero SoC project targeting MPFS250T with CoreVectorBlox V250
- Static timing analysis (SmartTime) and power estimation (SmartPower)

## What This Repo Does NOT Do
- No ML training (that's Repo 2: tychon-odmr-ml)
- No physics simulation (that's Repo 1: tychon-nv-sim)
- No SDK v3.0 — pinned to v2.0.x (see dependency verdicts)
- No Linux on MSS — bare-metal C only

## Critical Constraints
- VectorBlox SDK v2.0.3 (NOT v3.0) — matches CoreVectorBlox IP v2.0.1
- .vnnx files compiled with `-s V250` flag
- SmartHLS type: hls::ap_fixpt (NOT ap_fixed — that's Xilinx)
- Silver license targets MPFS250T (fallback MPFS460T), NOT RT PolarFire (Gold, Phase II)

## Cross-Machine Workflow
- Source edited on DGX Spark, pushed to GitHub
- Beelink pulls, runs SmartHLS and Libero synthesis, pushes reports
- Never edit source on Beelink

## Do NOT
- Add CI workflows unless explicitly asked
- Use VectorBlox SDK v3.0
- Target RT PolarFire (RTPF500ZT) — Phase II only
- Put .vnnx binaries in git
- Write firmware/main.c until SmartDesign memory map is locked
