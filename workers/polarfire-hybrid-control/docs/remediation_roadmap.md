# FPGA Demo — Remediation Roadmap (ROI-ranked)

**What this is.** A ranked plan to take each weak point from the skeptic Q&A sheet
(`09_skeptic_qa_honest_claims_2026-06-19.md`) from its current state to an *effective,
defensible* state. Ranked **#1 = best bang-for-buck** (cheap + high credibility gain) →
**#13 = long pole** (expensive/slow, lowest ROI for a Phase-I demo).

**How to read it.**
- **Section 1 (quick glance):** TL;DR, the ranked table, a suggested sprint sequence, and
  the dependency map. Read this in 2 minutes.
- **Section 2 (deep dive):** one self-contained playbook per item — current state →
  target → concrete steps → tools/skills → effort & cost (grounded with sources) →
  dependencies → risks → "done when." Feed this section to an LLM to generate a work plan.
- **Section 3 (research appendix):** the external grounding (benchmarks, datasets, tools,
  costs) with source links.

**Effort key:** XS = hours · S = 1–2 days · M = 3–10 days · L = 2–6 weeks · XL = months.
Hands-on time is separate from FPGA build/program **wall-time** (synth+P&R+program ≈ 1–2 h
per cycle on bee). Cost figures sourced where possible; anything marked **[needs quote]**
must be confirmed with a vendor — do not treat as final.

---

# SECTION 1 — QUICK GLANCE

**TL;DR.** The cheapest, highest-impact move is **#1: stop overclaiming** (correct the
dashboard/report numbers — hours, zero hardware). Then a **~2-week first sprint (#2–#6)**
fills the easy measurement gaps and closes 2 of the 6 proof obligations using work that's
already staged. The genuinely hard, slow item is **#12: getting real NV data** — it's the
*highest raw impact* (it kills the #1 skeptic point) but the longest, so **start its
procurement in parallel on day 1** even though its ROI rank is low. Environmental/flight
testing (#13) is months and $$$ — defer to Phase II and lean on PolarFire's existing
rad-tolerance for now.

**If you only do three things:** #1 (fix claims), #2 (measure latency), #8 (close the loop
in real time). Those three convert the three worst skeptic findings into defensible facts.

### Ranked table

| # | Item | Closes (Q#) | Hands-on | $ cost | Impact | Done when |
|---|------|-------------|----------|--------|--------|-----------|
| 1 | Correct the overclaims (dashboard + report) | Q4,Q6,Q8 wording | XS (hrs) | $0 | **High** | Numbers match artifacts; no unqualified "real/closed-loop/bit-exact/1 ms/200 MHz" |
| 2 | Measure end-to-end latency on silicon | Q5 | S | $0 | **High** | Committed table: PID-path + V250 inference + loop period in µs, from `rdcycle` |
| 3 | Commit a real post-layout resource table | Q7 | XS–S | $0 | Med | `resourceusage.rpt` for the shipped bitstream in repo; package label fixed |
| 4 | Build the sub-2 ms watchdog bitstream | Q6,Q8 | S | $0 | Med-High | `WATCHDOG_TIMEOUT_CYCLES=250000` build programmed; <=2 ms trip verified on silicon |
| 5 | Close RPO-4 (derivative-filter P&R integration) | Q8 | XS–S | $0 | Med | Filtered-derivative datapath through P&R; integrated timing number committed |
| 6 | Close RPO-6 (workload-driven SmartPower) | Q8 | S | $0 | Med | VCD-driven SmartPower report committed (real activity, not default toggle) |
| 7 | INT8-vs-float equivalence + honest accuracy harness | Q4 | S–M | $0 | Med-High | Quant-error report committed; "~5%" claim sourced; "bit-exact" wording fixed |
| 8 | Real-time fabric loop closure (sensed error + in-loop V250) | Q1,Q3 | M | $0 | **High** | Loop runs on fabric at rate w/o host pacing; unplug-the-host test still closes loop |
| 9 | Close RPO-2 + RPO-3 (ZOH phase margin + transport delay) | Q8 | M | $0 | Med | Sampled-data phase-margin number + measured nominal loop delay committed |
| 10 | Close RPO-5 (NN ReLU sector / Lipschitz certificate) | Q8 | M–L | $0 | **High** | Verified sector/Lipschitz bound on the deployed net → plugged into Circle Criterion |
| 11 | Close RPO-1 (plant-model identification) | Q8,Q2 | M–L | $0–low | High | Identified sector-bounded ODMR plant model (from rig data or validated sim) |
| 12 | Acquire real NV data / pass sim-to-real | Q2,Q3 | L | ~$2–8k | **Highest** | Real in-regime ODMR set; sim-to-real fidelity passes; small real val/fine-tune set |
| 13 | Environmental / flight qualification | Q9 | XL | $20–100k+ **[needs quote]** | Low (Phase I) | Thermal/vibe/rad campaign report — or interim: cite RTPF rad-tolerance + bench thermal |

### Suggested sequence

- **Sprint 0 (today, hours):** #1. Pure documentation/UI edit — removes the self-inflicted
  credibility loss immediately. Also: kick off #12 procurement (long lead) in parallel.
- **Sprint 1 (~2 weeks, mostly already-staged):** #2 → #3 → #4 → #5 → #6. Fills the
  measurement gaps and closes RPO-4 + RPO-6 with infra that already exists.
- **Sprint 2 (~2–3 weeks):** #7 (accuracy honesty) + #8 (real-time loop) + #9 (sampled-data
  margins, uses #2's latency number).
- **Sprint 3 (research, ~3–6 weeks, parallelizable):** #10 (NN certificate) + #11 (plant ID,
  needs #12 or a validated plant) + #12 landing (real data).
- **Deferred / Phase II:** #13.

### Dependency map (what blocks what)

```
#1  (independent — do first)
#2  latency ───────────────► #9  (ZOH phase margin needs the measured delay)
#3,#4,#5,#6 (independent, staged infra)
#7  (independent)
#8  real-time loop ────────► strengthens #9, #2 (in-loop timing)
#12 real NV data ─────┬────► #11 plant ID ────► #10 NN sector cert (needs plant + net)
                      └────► Q2/Q3 honesty, fine-tune set
#10 needs: deployed net (have) + sector bound (tool) + plant model (#11)
#13 (independent, but lowest ROI — defer)
```

**Highest *raw impact* regardless of ROI rank:** #12 (real data) and #10 (NN safety
certificate). Their ROI rank is low only because they're slow — **start them early in
parallel**, don't wait for the cheap items to finish.

---

# SECTION 2 — DEEP DIVE (per item)

## #1 — Correct the overclaims (dashboard + report)
- **Closes:** the wording half of Q4/Q6/Q8 (the "skeptic catches" that are self-inflicted).
- **Current state:** dashboard/report say "8.71% vs PID", "bit-exact INT8", "200 MHz",
  "1 ms watchdog", "closed-loop", and imply real/validated NV data. The repos' own
  artifacts contradict each (see `09_skeptic_qa_honest_claims_2026-06-19.md`).
- **Target (effective):** every headline number traceable to a committed artifact; every
  strong word ("real", "closed-loop", "bit-exact", "guarantees stability") either removed or
  qualified.
- **What it takes:**
  1. Dashboard string edits in `~/projects/fpga-demo-dashboard/frontend/src` (Tier-3 model
     card + metrics) and `backend/main.py:model_card()` (`deployed_out0`, accuracy text).
  2. Replace "8.71%" → "~5% MAE/Allan reduction (deployed `fcnn_v2_residual_dataset_a`)";
     "bit-exact INT8" → "INT8 deployment; bit-exact runner reproducibility (not INT8≈float)";
     "200 MHz" → "PID fabric 125 MHz / V250 core 200 MHz"; "1 ms watchdog" → "500 ms
     host-paced (demo); sub-2 ms hardware target pending"; "closed-loop" → "host-paced datapath
     with injected error"; remove/qualify any "real NV data"/"verified safety".
  3. Mirror the same edits in the SBIR final report / `final_report_outline.md`.
- **Tools/skills:** plain edits; the `update-config` skill not needed. Reuse the exact
  defensible phrasings already written in the skeptic-QA sheet.
- **Effort & cost:** **XS (2–4 h), $0.**
- **Dependencies:** none.
- **Risks:** none technical — only the discipline to not silently re-introduce the claims.
- **Done when:** a reviewer diffing the dashboard against the artifacts finds no
  unsupported number; "bit-exact" and "real data" no longer appear unqualified.
- **Bang-for-buck:** #1 — it's free and it stops a reviewer from catching you in an
  overclaim, which is far more damaging than the narrower true numbers.

## #2 — Measure end-to-end latency on silicon
- **Closes:** Q5 (the "no measured latency" GAP).
- **Current state:** II=1 pipeline by construction (`hls/src/nv_pid.cpp:22`), derivative
  filter 7-cycle (`docs/derivative_filter_design.md:8`); V250 only an upper bound (<~5 ms
  poll granularity). "<150 µs" is a design target, never measured.
- **Target (effective):** a committed table of measured latencies — (a) fabric PID compute
  (pulse-start → actuator-valid), (b) V250 single-inference latency, (c) full per-sample
  loop period — in µs/cycles, on silicon.
- **What it takes:**
  1. **V250 inference:** use the documented path — the VectorBlox `soc-c` `run-model` loop
     with `rdcycle` timestamps around `vbx_cnn_model_start`/`poll`/`wfi`
     (`docs/vectorblox_deployment_reference_2026-06-02.md:48`). Run N=1000 rows, report
     min/median/p99. **Expected « 1 ms** (our net is ~2,905 params vs MobileNet-v1's
     37 ms on the same V250 — ~1000× fewer MACs → tens–hundreds of µs; see Appendix A).
  2. **Fabric PID compute:** add a fabric cycle counter latched between `acc_start` and
     `actuator_out_write_en` (a tiny RTL counter in `pid_subsystem`, read via the M1
     `pid_csr`), or measure with SmartDebug/`rdcycle` around the `pid_ctl` pulse→read. The
     II=1 datapath should be a handful of cycles at 125 MHz (tens of ns).
  3. **Loop period:** timestamp the `rung_g_replay`/firmware per-sample iteration.
- **Tools/skills:** VectorBlox SDK `soc-c` example (already on bee), `pid_ctl`, optional
  small RTL counter (reuses the watchdog counter pattern in `libero/hdl/watchdog_timer.v`).
- **Effort & cost:** **S (1–2 days), $0.** Mostly a C loop + one report.
- **Dependencies:** none (kit is up, idfix2 resident, V250 cold-init confirmed).
- **Risks:** `rdcycle` on the U54 measures host+poll overhead, not pure NPU compute —
  report it as a *bounded* number and separate poll overhead from compute where possible.
- **Done when:** `docs/latency_measured_<date>.md` commits the three numbers with method.
- **Bang-for-buck:** #2 — converts a headline "we don't know" into a number that is almost
  certainly favorable, for ~1 day of work.

## #3 — Commit a real post-layout resource-utilization table
- **Closes:** Q7.
- **Current state:** only "109 DSP / 54,491 LUT" as a *synth-survival GATE note*; no
  committed P&R util table for the shipped bitstream; reports carry a FCVG1152-vs-FCVG484
  package-label inconsistency.
- **Target:** a committed `resourceusage.rpt` (LUT4/DFF/uSRAM/LSRAM/Math, with % of
  MPFS250T) for the exact idfix2 bitstream, on the correct FCVG484 package.
- **What it takes:** re-run report extraction on the existing idfix2 P&R database on bee
  (no re-synthesis) — `run_tool -name {GENERATEREPORTS}` / the `audit_libero_reports.py`
  extractor in `tools/`; copy the report into `libero/reports/`. Sanity-check against the
  ESA EDHPC comparable (V500 on MPFS250T ≈ 18.35% LUT4 / 22.45% Math; Appendix A).
- **Tools/skills:** Libero on bee, `tools/audit_libero_reports.py`.
- **Effort & cost:** **XS–S (~0.5–1 day), $0.**
- **Dependencies:** the idfix2 P&R database still on bee (confirm it wasn't cleaned).
- **Risks:** if the idfix2 P&R DB was deleted, you re-run P&R (adds ~1 h wall-time).
- **Done when:** committed util table for idfix2 + a one-line package-label correction.
- **Bang-for-buck:** high — a near-free committed number replaces a hand-wavy note.

## #4 — Build the sub-2 ms watchdog bitstream
- **Closes:** the watchdog-overclaim half of Q6/Q8.
- **Current state:** `WATCHDOG_TIMEOUT_CYCLES` is a single parameter (default 200_000;
  `libero/hdl/watchdog_timer.v:23`); the demo build ships a 500 ms (62.5e6-cycle)
  host-paced timeout. At the real 125 MHz fabric, 200_000 cycles = **1.6 ms**, so even the
  "spec" constant is off.
- **Target:** a programmed bitstream whose watchdog trips at **2 ms or less**. The
  near-term target is `WATCHDOG_TIMEOUT_CYCLES = 250_000` at 125 MHz, with the trip
  verified on silicon. A 1 ms image remains nice-to-have, but exact 1 ms is no longer
  the Phase-I demo credibility gate.
- **What it takes:**
  1. Set `WATCHDOG_TIMEOUT_CYCLES = 250_000` (125 MHz-correct 2 ms) in the two-slot
     parameterization; rebuild via the patcher (`libero/scripts/two_slot/patch_two_slot.py`).
  2. Synth → P&R → timing → export `.job` → FPExpress program (Red-zone: needs Jason's
     go for the program step) → **cold power-cycle** (V250 init) → verify watchdog_csr trips
     at or below 2 ms after heartbeat stops.
- **Tools/skills:** the two-slot build chain on bee; FPExpress; the rung_g watchdog stunt
  for verification.
- **Effort & cost:** **S (1–2 days hands-on; +~2 h P&R/program wall-time), $0.**
- **Dependencies:** preserve idfix2/demo/seed_7 rollbacks (hash-verified) before programming.
- **Risks:** any reprogram needs the cold-cycle ritual; standard guardrails apply.
- **Done when:** a watchdog-target bitstream programmed + a silicon log showing a <=2 ms trip.
- **Bang-for-buck:** high — turns the watchdog target into a demonstrated silicon fact for
  ~1 RTL constant + a build.

## #5 — Close RPO-4 (derivative-filter P&R integration)
- **Closes:** one of the six RPOs (Q8).
- **Current state:** HLS-level **COMPLETE** (filtered derivative, II=1, 7-cycle, `prev_d`
  register — `docs/derivative_filter_design.md:5-8`, DLOG-046); only the **P&R-integrated
  timing number** is deferred (gated on the canvas/two-slot refresh).
- **Target:** the filtered-derivative datapath carried through P&R in the two-slot build,
  with the integrated timing number committed (closing RPO-4's last gap).
- **What it takes:** include the filtered-derivative HLS output in the next two-slot rebuild
  (likely fold into the #4 build), capture the VERIFYTIMING slack, commit the report.
- **Tools/skills:** SmartHLS + Libero on bee.
- **Effort & cost:** **XS–S (~1 day on top of a build), $0.**
- **Dependencies:** rides the #4 (or any) two-slot rebuild.
- **Risks:** minor timing impact from the extra register stage — already budgeted (II=1).
- **Done when:** committed integrated timing for the filtered-derivative datapath.
- **Bang-for-buck:** high — closes a named proof obligation for almost no marginal work.

## #6 — Close RPO-6 (workload-driven SmartPower)
- **Closes:** one of the six RPOs (Q8).
- **Current state:** **infra prepped, not closed** (`docs/workload_smartpower_2026-05-17.md`,
  DLOG-047). Step 1 + testbench in place; steps 2–4 (ModelSim → VCD → SmartPower
  VCD-activity import) deferred; three documented gaps (testbench port assumptions, wrong
  project path, unverified SmartPower VCD Tcl form).
- **Target:** a committed SmartPower report driven by **real switching activity** (VCD from
  a simulated ODMR-PID workload), replacing the default-toggle upper bound.
- **What it takes:** fix the three documented gaps; run ModelSim on the two-slot RTL with
  the ODMR stimulus → VCD; feed VCD activity into SmartPower; commit the dynamic+static
  breakdown.
- **Tools/skills:** ModelSim/QuestaSim + Libero SmartPower on bee; the staged
  `sim/modelsim_pid_workload.do` and `libero/scripts/05_smartpower_workload.tcl`.
- **Effort & cost:** **S (1–2 days), $0.**
- **Dependencies:** a two-slot RTL build (have); valid ODMR stimulus (have, the replay CSV).
- **Risks:** the doc notes the PID datapath produced near-zero outputs in the first attempt
  (stimulus didn't exercise it) — use a stimulus that actually drives nonzero activity.
- **Done when:** committed VCD-driven SmartPower report.
- **Bang-for-buck:** high — closes a named RPO with infra that's already 60% built.

## #7 — INT8-vs-float equivalence + honest accuracy harness
- **Closes:** the substance of Q4 (the "bit-exact" overclaim + the deployed number).
- **Current state:** "bit-exact INT8" means int8-runner reproducibility (cascade), not
  INT8≈float; deployed INT8 output clamps to ±~2.9 µT; deployed reduction is ~5% (4.97%
  AIC-test), not 8.71% (that was the failed cascade).
- **Target:** (a) a committed quant-error report (INT8 vs float on the real test split:
  MAE/RMSE/max, % saturated); (b) the accuracy claim sourced to `fcnn_v2_residual_dataset_a`
  at ~5%; (c) **decision:** is ~5% "effective"? If not, a short retrain/architecture pass.
- **What it takes:**
  1. Eval harness in `odmr-edge-ml/evaluation/`: run float `.pt` and INT8 `.tflite` on the
     held-out `production_50k_v2_aic` test split (NOT uniform-random inputs — use real
     spectra so the quant error isn't overstated), report the deltas.
  2. If ~5% is judged insufficient: revisit the ±2.25 µT label clamp / output scale (the
     deployed model clamps 6.5% of outputs — headroom exists) or a small architecture bump;
     re-export, re-quantize, re-measure. Treat as a separate timeboxed effort.
- **Tools/skills:** PyTorch + TFLite; the existing `clamped_eval.py` / `scalar_residual_v2.py`.
- **Effort & cost:** **S (harness, 2–3 days)** ; **+M (1–2 weeks)** only if you retrain to
  raise the number. **$0** (local GPU; no token/inference cost).
- **Dependencies:** none for the harness; the `.vnnx` recompile (if retrained) is a
  cross-repo handoff to `polarfire-hybrid-control`.
- **Risks:** retraining may not beat ~5% materially — the residual signal over a good PID
  lock is genuinely small; set a target before spending the 1–2 weeks.
- **Done when:** committed quant-error report + accuracy claim sourced; dashboard fixed.
- **Bang-for-buck:** med-high — the harness is cheap and kills a named overclaim; the
  retrain is optional and lower ROI.

## #8 — Real-time fabric loop closure (sensed error + in-loop V250)
- **Closes:** Q1 + Q3 (the "host-paced, injected error, inference run separately" findings).
- **Current state:** the loop is driven step-by-step over ssh; error is injected into a CSR
  (not sensed); V250 inference runs separately, not per-row in the loop.
- **Target:** the sensor→PID→(NN feedforward)→actuator loop runs **on fabric/MSS at rate
  without host pacing**, with the V250 `output_valid` feeding the controller per cycle. The
  falsification test: pull the host link and the loop keeps closing (the opposite of the
  static-dashboard failure).
- **What it takes:**
  1. Feed error from a fabric/MSS source (replay BRAM or a streamed input) instead of a host
     CSR poke; the two-slot datapath already has `vbx_pulse_gen` and the `output_valid`
     wiring — drive the per-sample compute from fabric, not from `pid_ctl`.
  2. Run the V250 per-row in the loop so the watchdog stays out of fallback (today it sits
     in `PID_ONLY_FALLBACK` because no recent `output_valid`). This is the "bring u_AI into
     the live loop" item already flagged as next-step in the wiki README.
  3. Demonstrate on silicon; optionally add a real sensor front-end later (ties to #12).
- **Tools/skills:** SmartHLS/RTL on bee; firmware/Linux runtime; ModelSim for the loop TB.
- **Effort & cost:** **M (1–2 weeks), $0.** Real FPGA/firmware integration + a rebuild.
- **Dependencies:** a two-slot rebuild; benefits from #2's timing to prove real-time margin.
- **Risks:** keeping the NN in-loop without tripping the watchdog requires the inference
  cadence to beat the watchdog window — #2's latency number tells you if it fits.
- **Done when:** a silicon run where the loop closes with the host detached, V250 in-loop,
  watchdog NOT in permanent fallback.
- **Bang-for-buck:** high — this is the single change that turns "datapath demo" into
  "real-time control," answering the two most damaging structural skeptic points.

## #9 — Close RPO-2 + RPO-3 (ZOH phase margin + transport-delay bound)
- **Closes:** two of the six RPOs (Q8).
- **Current state:** open — sampled-data closure changes the Nyquist contour (RPO-2); the
  revised sub-2 ms watchdog target is the near-term worst-case delay, nominal must be measured (RPO-3).
- **Target:** a committed sampled-data phase-margin number (ZOH-aware) and the measured
  nominal loop transport delay, with the analysis tying to the Circle-Criterion framing.
- **What it takes:** standard sampled-data control analysis (Tustin/ZOH equivalent of the
  PID at the real loop rate; phase margin from the discrete loop) + use #2's measured loop
  delay as the nominal transport delay; document against Khalil §11 / Åström-Hägglund Ch.6
  (already cited in `docs/safety_architecture.md:61-62`).
- **Tools/skills:** Python/MATLAB control toolbox; the corpus Lur'e/Circle bundle.
- **Effort & cost:** **M (3–5 days), $0.**
- **Dependencies:** **#2 (latency)** for the nominal delay; a plant model (#11) sharpens it
  but a conservative bound can be stated without it.
- **Risks:** without a real plant (#11), the margin is assumption-bounded — state the
  assumption explicitly.
- **Done when:** committed phase-margin + delay numbers in `safety_architecture.md`.
- **Bang-for-buck:** med — analysis-only, closes two RPOs, but lower visibility than #8.

## #10 — Close RPO-5 (NN ReLU sector / Lipschitz certificate)
- **Closes:** the keystone safety RPO (Q8) — "the AI is sector-bounded *only if* the trained
  weights satisfy a sector bound."
- **Current state:** open; the clamp bounds the *output magnitude* but there's no certificate
  that the NN map itself is sector/slope bounded.
- **Target:** a verified sector (or Lipschitz) bound on the deployed `fcnn_v2_residual` map,
  fed into the Circle-Criterion condition → a real (not asserted) absolute-stability argument
  within the stated plant assumptions.
- **What it takes:**
  1. The deployed net is **tiny and conv-only (~2,905 params, ReLU)** — ideal for off-the-
     shelf verification. Compute a global Lipschitz/sector bound with **LipSDP** (SDP over
     slope-restricted ReLU) or **α,β-CROWN** (VNN-COMP-winning, scalable); both are mature.
  2. Combine with an IQC/Lur'e formulation (recent 2024–2025 results give *network-level*
     sector bounds suitable for Lur'e analysis — Appendix B) to state the closed-loop
     condition.
  3. Verify the INT8-deployed weights (not just float) satisfy the bound, or bound the
     quant perturbation (ties to #7).
- **Tools/skills:** LipSDP / α,β-CROWN (open source); an SDP solver (MOSEK/SCS); local GPU.
- **Effort & cost:** **M–L (1–2 weeks), $0** (tools are free/open; runs on the Sparks).
- **Dependencies:** the net (have) + a plant sector (from #11) to *close the loop* claim;
  the *NN bound itself* needs neither and can be produced first.
- **Risks:** a global Lipschitz bound may be loose; may need slope-restricted/per-layer or
  local bounds to get a usable sector — still tractable at this size.
- **Done when:** a committed certificate (bound + method + tool version) and the Circle-
  Criterion condition evaluated with it.
- **Bang-for-buck:** high *impact*, mid ROI — this is what makes "sector-bounded by design"
  into "sector-bounded, certified." Now feasible off-the-shelf; start it early.

## #11 — Close RPO-1 (plant-model identification)
- **Closes:** RPO-1 (Q8) and underpins Q2 honesty.
- **Current state:** open and **explicitly blocked** — "Icicle is FPGA-only, not NV"
  (`docs/odmr_demo_credibility_2026-06-02.md:38`). The Circle Criterion needs a
  sector-bounded plant; Phase I assumes "any positive gain."
- **Target:** an identified ODMR plant model (transfer function / sector bound) from either
  (a) real benchtop rig data (#12) or (b) a validated high-fidelity simulation.
- **What it takes:** step/chirp excitation of the ODMR lock loop (on the rig from #12, or in
  a validated sim), fit a plant model, extract the sector/gain bound for the Circle
  Criterion.
- **Tools/skills:** system-ID (Python `sippy`/MATLAB); the nv-sensor-sim plant if validated.
- **Effort & cost:** **M–L (1–2 weeks given data/model), $0–low.**
- **Dependencies:** **#12** (real data) for a *credible* plant; can be done against the sim
  first but a skeptic discounts a sim-only plant.
- **Risks:** a sim-only plant inherits the unvalidated-sim problem (Q2) — the real value
  comes once #12 lands.
- **Done when:** committed plant model + sector bound feeding #9/#10.
- **Bang-for-buck:** mid — high value but gated on #12 for credibility.

## #12 — Acquire real NV data / pass sim-to-real
- **Closes:** Q2 (the #1 skeptic kill) and the data half of Q3; unblocks #11.
- **Current state:** 100% simulated; the only real dataset (Zenodo micro-diamond, near-zero
  field) **failed** the PCA fidelity check (min cos 0.009 vs ≥0.80) due to **regime
  mismatch** — it's a different measurement regime than the simulator's 20–70 µT
  longitudinal ensemble CW-ODMR.
- **Target:** real ODMR spectra **in the simulator's regime** (bulk/microdiamond *ensemble*,
  CW-ODMR, 20–70 µT) sufficient to (a) pass/repair the sim-to-real fidelity check and
  (b) provide a small real validation + fine-tune set.
- **What it takes — three options, cheapest first:**
  1. **Find a regime-matched public dataset.** The failed Zenodo set was wide-field
     micro-diamond; search for *ensemble CW-ODMR* sweeps near the sim's field range (recent
     vector-magnetometry/ensemble papers publish Zenodo data — Appendix C). Cheapest if it
     exists. **XS–S, ~$0.**
  2. **Build a benchtop CW-ODMR ensemble rig.** This is the regime the simulator targets,
     so it's the *right* validation source. Documented low-cost builds exist: MDPI/EPJ-QT
     teaching rigs for a **low-three-digit € BOM** (LED + microdiamond + ADF435 MW board +
     BPW34 photodiode), or a sturdier bench with an Element Six DNV-B1/B14 diamond (~$2k
     each) + green laser + MW source. **L (3–8 weeks build+characterize), ~$2–8k.**
  3. **Borrow/collaborate** (a quantum-sensing lab or the CIQTEK ODMR teaching system) for a
     data-collection session. **S–M, low $, depends on access.**
- **Tools/skills:** lab build; reuse `nv-sensor-sim/validation/reference_comparison.py` and
  `pca_fidelity_zenodo.py` for the fidelity check; `acquire-corpus` for dataset hunting.
- **Effort & cost:** **L (weeks), ~$2–8k** for the rig path; near-$0 if a public set fits.
- **Dependencies:** none to start — **kick off day 1**, it's the long pole.
- **Risks:** even in-regime real data may reveal sim gaps (no shot noise, no real lineshape
  artifacts — Q4 of the data report) requiring sim upgrades; budget for a sim-fidelity loop.
- **Done when:** sim-to-real fidelity passes (or is honestly characterized) on in-regime
  data, and a real val/fine-tune set exists.
- **Bang-for-buck:** **highest raw impact, lowest ROI rank** because it's slow/costly —
  hence "start now in parallel," don't block the cheap wins on it.

## #13 — Environmental / flight qualification
- **Closes:** Q9.
- **Current state:** benchtop only; no thermal/vibration/radiation/flight testing.
- **Target (full):** a thermal (e.g., MIL-STD-810), vibration, and radiation (TID + heavy-ion
  SEU) campaign with a report. **Target (interim, cheap):** cite that the design family is
  the **rad-tolerant RT PolarFire (RTPF)** — PolarFire is already used for space CNN work
  (ESA EDHPC; Appendix A) — and do a **bench thermal sweep** of the Icicle Kit, without a
  full campaign.
- **What it takes (full):** board prep + TMR/scrubbing engineering; beam time at a heavy-ion
  facility (TAMU/LBNL/NSRL) per JESD57/ASTM F1192; Co-60 TID; thermal chamber + shaker.
- **Tools/skills:** external test houses (NASA NEPP-style); not in-house.
- **Effort & cost:** **XL (months), ~$20–100k+ all-in [needs quote]** (beam time + boards +
  engineering). The interim rad-tolerance citation + bench thermal is **S, ~$0–low**.
- **Dependencies:** a stable final bitstream; budget approval.
- **Risks:** large cost/schedule; only justified by a customer requirement.
- **Done when (interim):** a committed note citing RTPF rad-tolerance + bench thermal data.
  **(Full):** third-party campaign report.
- **Bang-for-buck:** **lowest for Phase I** — defer; do the interim citation instead.

---

# SECTION 3 — RESEARCH APPENDIX (external grounding)

### A. V250 inference latency + PolarFire resource/space comparables
- Microchip "ML on the Edge and Space" webinar: **VectorBlox V250** — MobileNet-v1 **37.0 ms
  / 27 FPS**, MobileNet-v2 39.0 ms, ResNet-50 **4 FPS** (~250 ms), Tiny-YOLOv3 5 FPS; V250
  fabric clock **~153 MHz**, peak 79 GOPs; a TMR-free **space** table for RT PolarFire
  (RTPF500T). Our ~2,905-param conv-only net is ~1000× fewer MACs → expect **« 1 ms**
  (tens–hundreds of µs). Source: microchip.com.hk ML-on-the-Edge-and-Space webinar PDF.
- ESA EDHPC 2023 CNN-on-PolarFire study (Icicle Kit): **V500 on MPFS250T = 18.35% LUT4 /
  19.11% DFF / 22.45% Math blocks**; notes "currently only PolarFire FPGA is rad-hard." Good
  comparable for #3 and the #13 interim rad-tolerance claim. Source: indico.esa.int EDHPCv2.
- VectorBlox SDK is **licensed free** (vs the $30k video-encoder IP) — no tooling cost for
  the inference path. Source: Hackster FPGAdventures.

### B. Neural-network closed-loop stability / sector-bound verification (for #10)
- **LipSDP** — SDP Lipschitz bounds via slope-restricted activations (tight, standard).
- **α,β-CROWN** — VNN-COMP-winning, scalable NN verifier; used for NN-controller safety.
  See VNN-COMP 2024 summary (arXiv 2412.19985).
- **Sector-bounded NN-in-loop (Lur'e):** "Ensuring Both Positivity and Stability Using
  Sector-Bounded Nonlinearity for Systems with Neural Network Controllers" (arXiv 2406.12744);
  "Positive Lur'e Certificates / Delay-Independent Safe Control with NNs" (arXiv 2510.06661);
  "Lyapunov-stable Neural Control … efficient synthesis and verification" (arXiv 2404.07956);
  "Aperiodic-sampled NN controllers with closed-loop stability verifications" (arXiv 2506.18386);
  Hu et al. "Safety Verification … via Quadratic Constraints and SDP" (the QC/IQC basis).
- Takeaway: network-level sector descriptions suitable for Circle/Lur'e analysis now exist
  off-the-shelf; our net's size makes this a days–weeks task, not a research program.

### C. Real NV / ODMR data + low-cost benchtop rigs (for #12)
- Low-cost CW-ODMR ensemble builds (the simulator's regime):
  - MDPI Quantum Beam Sci. "Components for an Inexpensive CW-ODMR NV-Based Magnetometer" —
    full BOM (LED ~€0.30, BPW34 photodiode ~€1.20, ADF435 MW board ~€30, **microdiamond
    from Adámas** ~€3/piece from a €578/30 mg batch). (mdpi.com/2673-8724/5/3/18)
  - EPJ Quantum Technology 2025 "Low-cost ODMR experiments with NV centers" — full setup
    for a "low three-digit euro amount." (link.springer.com/…/s40507-025-00326-5)
  - arXiv 2512.03106 "Portable LED-based diamond magnetometer" — Element Six **DNV-B1 /
    DNV-B14** ensemble diamonds ~**$2,000** each.
  - Commercial teaching bench: **CIQTEK ODMR Teaching System** (desktop, room-temp).
- Open datasets / prior art to mine first (cheapest path):
  - arXiv 2603.14728 "A Deep-Learning-Boosted Framework for Quantum Sensing with NV Centers"
    — directly relevant ML-for-NV prior art.
  - arXiv 2505.24574 "Bias-field-free … vector magnetometry"; arXiv 2301.04106 "Simulation of
    ODMR Spectra from NV Ensembles" (open sim tool); Sengottuvel et al. 2025 near-zero-field
    Zenodo (DOI 10.5281/zenodo.14833488 — note: near-zero field, may again be off-regime).
- Lesson from the failed check: match the **measurement regime** (ensemble CW-ODMR, 20–70 µT
  longitudinal), not just "NV data," or the fidelity check fails on regime mismatch again.

### D. Radiation / environmental qualification (for #13)
- Facilities/standards: heavy-ion SEE at **TAMU / LBNL / NSRL**, Co-60 for **TID**, per
  **JESD57 / ASTM F1192**; NASA **NEPP** has published Microsemi RTG4 + Xilinx campaigns.
  (sciencedirect S0168900215013984; etd.gsfc.nasa.gov radiation-effects; radiationtestsolutions.com)
- **No public per-campaign price found** — **[needs quote]**. Plan on multi-day beam time +
  board prep + TMR/scrubbing engineering; treat $20–100k+ all-in as an *unverified* planning
  placeholder until a facility quotes it.
- Cheaper interim credibility: the design family (**RTPF**) is rad-tolerant and already used
  for space CNN work (Appendix A) — cite that + a bench thermal sweep instead of a campaign.

---

*Sources are listed inline above; the underlying repo claims (file:line) are in
`09_skeptic_qa_honest_claims_2026-06-19.md`. Effort/cost are planning estimates — the
FPGA build items assume the idfix2 P&R database is intact on bee; the #12 rig cost assumes
a benchtop ensemble build, not a metrology-grade instrument. Cost figures marked
[needs quote] are unverified and must be confirmed with vendors.*
