# DISPATCH → polarfire-hybrid-control lane — CW-ODMR bench scoping (2026-07-09)

**STATUS: HOLD — do not relay.** Gated on Jason's elevation + budget
decision. Hardware selection and purchasing are Jason's call at the TVW
level (pricing table lives in eval-bench-elevation-2026-07-09.md, addressed
to him) — they are NOT lane work and have been removed from this dispatch.

**From:** TVW orchestration lane
**Authority:** eval-bench-elevation-2026-07-09.md (TVW), triggered by xTech
Phantum Round 1 Judge #5 feedback.
**Paste this whole file into a polarfire-hybrid-control session — only after
Jason approves elevation and picks the hardware.**

---

## Context (read first, in this order)

1. `docs/odmr_demo_credibility_2026-06-02.md` — your own credibility ladder;
   this dispatch executes its §3 items 1→4 for real.
2. `docs/real_nv_dataset_hunt_2026-06-21.md` — no public regime-matched
   dataset exists; the bench is the only unblocked route to real NV data.
3. TVW `tvw/audits/eval-bench-elevation-2026-07-09.md` — priced BOM options
   (~$1.4k floor / ~$2.8k recommended / ~$6.5k stretch), links verified
   2026-07-09.

xTech Judge #5 dinged the program for "synthetic data for a complex
photonic/RF system" and "lack of physical hardware… competes strictly at the
FPGA/control layer." One bench artifact flips both for every future
submission and closes RPO-1 for the portfolio story.

## Deliverable ladder (stop-gated; B1 alone is already valuable)

- **B1 — first photons + recorded sweep set.** Ensemble CW-ODMR sweeps (CSV)
  around 2.87 GHz with real shot noise and lineshape asymmetry, bias field
  in/near 20–70 µT. Host-driven acquisition is acceptable for B1 — the kit
  does not need to be in the loop yet. Artifact drops into
  `hls/tb/stimulus/` (the dir already exists for this) and unblocks
  credibility fix #1 (replay real trace through the existing datapath).
- **B2 — Icicle-in-the-loop lock.** Existing PID datapath locks to the real
  discriminator signal; show re-lock after a field step; Allan deviation with
  −½ slope on the error signal.
- **B3 (stretch, separate approval).** NN-assist demo: "PID holds the lock;
  the NN corrects what the PID structurally can't see."

## Tasks for this session (scoping only — hardware is already chosen)

Jason has selected the hardware at the TVW level; the list accompanies this
dispatch when relayed. Your work is integration, not selection:

1. **Interface plan for the chosen hardware.** Control path for the selected
   MW source from the bench host (B1) and from the kit (B2); photodiode
   readout path into the kit for B2 (Rpi-header/mikroBUS SPI ADC options,
   required sample rate given the kHz-class servo, MSS-first vs fabric-first).
2. **Bench plan that protects demo-readiness.** The kit holds the golden
   idfix2 image (verified `kit_replug_inventory_2026-07-01.md`). B1 must not
   touch it at all; for B2, plan a separate SD card / clearly-named branch and
   a documented restore path. No reflash of the golden image without a
   separate go.
3. **Acquisition script skeleton** for B1 (sweep → CSV with metadata header),
   consuming the data spec that the odmr-vector-tracking lane will produce
   (TVW `dispatch-odmr-bench-dataspec-2026-07-09.md`). Don't finalize the
   schema until that spec lands — just stub it.

## Hard constraints

- **Geometry must be logged.** Every sweep records bias-field magnitude AND
  orientation relative to the diamond crystal axes (magnet position jig or
  measured splitting pattern). Downstream tracker architectures exploit a
  fixed-direction prior; unlogged geometry makes the data far less useful.
- **Honest-claims rails unchanged:** µT/√Hz-class is the honest sensitivity
  class for compact CW-ODMR; no "beats IMU"; no INT8/on-silicon language for
  the tracker (it is FP32); loop-pacing caveats stay until measured.
- Report results back UP to TVW (this lane does not issue cross-program
  dispatches itself).

## Return format

A single `docs/bench_cwodmr_scoping_2026-07-XX.md` with: interface plan for
the chosen hardware, kit-protection plan, B1 script stub location, open
questions for TVW/Jason.
