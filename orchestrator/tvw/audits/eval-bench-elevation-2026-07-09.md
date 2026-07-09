# Evaluation — Elevating a Minimal Real-Hardware CW-ODMR Bench Demo (2026-07-09)

**Trigger:** xTech Phantum Round 1 feedback (received 2026-07-09; Judge #5 comments
dated 2026-06-11). Full analysis:
`~/projects/xtech_competition/research/round1_judge_feedback_analysis_2026-06-11.md`
(mirrored at `tychon-sbir/XTech Competition/draft_for_review/`).

**Question:** should a minimal real-hardware CW-ODMR bench demonstration
(Icicle Kit + entry-level NV head) be elevated to a program priority?

**Ruling: ELEVATE — recommended.** Presented as work to be considered; phase
tagging and budget approval are the user's call. Cost of the recommended bench
configuration is **~$2,800–3,300** (verified pricing below), with a floor of
~$1,400 and a stretch build at ~$6,500.

---

## 1. Three independent lines already converge on this

1. **Judge #5 (external).** The two decisive criticisms — "inadequate risk
   analysis relying on synthetic data for a complex photonic/RF system" and
   "lack of physical hardware via 'Phase I equivalent' phrasing… competes
   strictly at the FPGA/control layer" — jointly account for ~45% of the
   rubric weight (Technical Approach 25% + Scalability 20%). The heatmap
   decode shows the control-layer/sim story is *high-variance, not uniformly
   weak*: 2 judges bought it fully, 3 didn't. Hardware evidence de-risks the
   story rather than replacing it.
2. **polarfire lane (internal, 2026-06-02).**
   `polarfire-hybrid-control/docs/odmr_demo_credibility_2026-06-02.md` §3
   already ranked the credibility ladder and named "full HIL with a diamond =
   the real unlock, but the expensive long pole (RPO-1)." RPO-1 ("still
   blocked — Icicle is FPGA-only, not NV") is visible to any external reviewer
   reading the Phase II table.
3. **Dataset hunt (internal, 2026-06-21).**
   `polarfire-hybrid-control/docs/real_nv_dataset_hunt_2026-06-21.md` found
   **no public regime-matched CW-ODMR dataset** (20–70 µT ensemble) and
   concluded: "one recorded CW-ODMR sweep set in the target regime would be
   more valuable than another broad literature search." The bench is now the
   only unblocked route to real NV data.

A single bench artifact therefore serves four audiences at once: xTech
resubmission (Tech Approach, Scalability, Risks & Mitigation, Data
Attribution — external evidence replaces "on file"), any future SBIR
submission, an external reviewer (closes RPO-1; upgrades
`skeptic_qa_honest_claims.md`), and the ML lanes (real spectra for the
sim-to-real fidelity check the dataset hunt was chasing).

## 2. What "minimal" means — scope guardrails

Target artifact ladder (each rung is independently usable; from the
credibility doc's cheapest-fix ordering):

- **B1 — first photons + one real sweep set.** Recorded ensemble CW-ODMR
  sweeps (CSV) with real shot noise and asymmetric lineshape, in/near the
  20–70 µT regime, with bias-field geometry logged. Drops directly into
  `hls/tb/stimulus/` — kills the "idealized signal" objection even before any
  closed loop exists, and satisfies the dataset-hunt goal.
- **B2 — closed-loop lock.** Existing PID datapath locks to the real
  discriminator signal; demonstrate re-lock after a field step; Allan
  deviation with −½ slope on the error signal.
- **B3 (stretch) — NN-assist demo** per the defensible-claim framing: "PID
  holds the lock; the NN corrects what the PID structurally can't see."

Honesty rails (unchanged by the bench): µT/√Hz-class sensitivity is the
honest claim for compact CW-ODMR (not nT); no "beats IMU" claim; tracker
remains FP32 (O11 open — "built for the V250 slot," not "running on
silicon"); loop-pacing caveats stay until measured otherwise.

## 3. Cost research — entry-level NV head options (verified 2026-07-09)

### Tier 0 — outreach-grade existence proof (~$135–250)

| Item | Price | Link |
|---|---|---|
| **Uncut Gem** open-source NV sensor (Quantum Village) — ESP32 + ADF4351 MW gen ($25) + LED + $10 NV diamond; full BOM | **~$115–135** | [arXiv 2509.18329](https://arxiv.org/html/2509.18329v1) · [github.com/QuantumVillage/UncutGem](https://github.com/QuantumVillage/UncutGem) |
| Bülau et al. educational CW-ODMR component set (LED, photodiode+TIA, low-cost MW resonator) — demonstrates fluorescence, ODMR, Zeeman | **<€100** | [Magnetism 5(3):18, 2025](https://www.mdpi.com/2673-8724/5/3/18) (companion resonator paper: [MDPI](https://www.mdpi.com/2673-8244/5/4/69)) |

Too toy-grade as the *sole* judge-facing artifact, but proves the optics/MW
chain is not exotic, and the Uncut Gem design files are a free reference
implementation.

### Tier 1 — credible bench, RECOMMENDED (~$2,800–3,300)

Anchor design: [arXiv 2512.03106](https://arxiv.org/html/2512.03106v2)
(portable LED-based diamond magnetometer, **~$4,500 full BOM, ~1 µT/√Hz**) —
its $400 Red Pitaya line item is exactly the role the already-owned Icicle
Kit fills, and its $2,000 diamond line can be substituted down.

| Component | Option | Price | Link |
|---|---|---|---|
| NV diamond | Adámas 3×3×0.3 mm HPHT, [NV]≈2 ppm (high NV content, good for LED excitation) | **~$601** (indexed list price; store is quote-per-item) | [adamasnano.com/diamond-plates](https://www.adamasnano.com/diamond-plates) |
| NV diamond (alt) | Element Six **DNV-B1** 3×3×0.5 mm, ~300 ppb, in stock | **$1,897.73** | [thorlabs.com/single-crystal-diamonds](https://www.thorlabs.com/single-crystal-diamonds) |
| NV diamond (high-density alt) | Element Six **DNV-B14** 3×3×0.5 mm, ~4.5 ppm, in stock | **$4,091.98** | same |
| MW source | Windfreak **SynthNV** 34 MHz–4.4 GHz (covers 2.87 GHz; incl. power detector) | **$799** | [windfreaktech.com](https://windfreaktech.com/product/rf-signal-generator-and-power-detector/) |
| MW source (alt) | Windfreak **SynthNV Pro** 12.5 MHz–6.4 GHz | **$1,599** ($1,573 at [Saelig](https://www.saelig.com/category/windfreak.htm)) | [windfreaktech.com](https://windfreaktech.com/product/synthnv-pro-12-5mhz-6-4-ghz-rf-signal-generator-plus-rf-detector/) |
| MW source (floor) | ADF4351 eval board (35 MHz–4.4 GHz) | ~$25–40 | per Uncut Gem BOM |
| Detector | Amplified Si photodetector (PDA36A2-class) | ~$400 | per 2512.03106 BOM |
| Excitation | High-power green LED + driver | ~$550 (LED $250 + T-Cube driver $300) | per 2512.03106 BOM |
| Filters/optics/mechanics | 600 nm SP + 638 nm LP filters, prism, mixing rod, SM1 tubes, magnets, PCB resonator | ~$450–700 | per 2512.03106 BOM lines |

**Recommended buy (~$2,800):** Adámas high-NV plate ($601) + SynthNV ($799) +
LED excitation (~$550) + amplified PD (~$400) + filters/optics/resonator
(~$500). Floor build (~$1,400): same but ADF4351 + bare photodiode/TIA.
Stretch (~$6,500): DNV-B14 + SynthNV Pro for maximum contrast headroom.

### Tier 2 — turnkey educational kits (quote-only; not recommended)

- qutools **quNV is deprecated** ([qutools.com/qunv-deprecated](https://qutools.com/qunv-deprecated/)); successor is the [quEDU](https://qutools.com/quedu/) platform + [quADD-NV](https://qutools.com/quadd-nv/) board — no published price, quote-only.
- CIQTEK [ODMR Teaching System](https://www.ciqtekglobal.com/optically-detected-magnetic-resonance-teaching-system_p2.html) / "Diamond I" education instrument — quote-only via distributors ([Emona AU](https://emona.com.au/products/engineering-teaching-equipment/quantum-computing/ciqtek-diamond/), [ETCON](https://etconanalytical.com/ciqtek-quantum-computing/)).

Both re-introduce "someone else's box" between our control layer and the
physics, cost an expected 5–10× Tier 1, and weaken the story that *our* FPGA
stack drives the sensor. Only worth a quote request if bench-labor time turns
out to be the binding constraint.

**Market context:** research-grade NV magnetometer *systems* average ~$128k
(2025, [Dataintelo market report](https://dataintelo.com/report/nv-center-diamond-for-quantum-sensing-market))
— useful as the comparator anchor the judge asked for in Submission Quality.

## 4. Costs and risks of elevation

- **Founder bandwidth** is the real cost; hardware dollars are minor. The
  in-flight ML dispatches (dispatch-8/increment-7) run in worker lanes and do
  not contend; bench work is polarfire-lane sessions + parts lead time.
- **Alignment/contrast risk** is bounded: the anchor paper publishes the
  exact architecture and achieved sensitivity; Uncut Gem + the Bülau
  resonator paper are free reference designs. This is replication, not
  research.
- **Demo-state risk:** the Icicle Kit currently holds the golden idfix2
  demo image (verified live 2026-07-01, `kit_replug_inventory_2026-07-01.md`).
  Bench integration must not brick demo-readiness — guardrail written into
  the polarfire dispatch.
- **Overclaim risk:** a bench invites "real hardware!" language creep.
  `skeptic_qa_honest_claims.md` discipline extends to bench claims (§2 rails).

## 5. Dispatches drafted — ON HOLD pending Jason's decision

Hardware selection and purchasing are Jason's decisions at the TVW level;
the pricing in §3 is his decision package, not lane work. The drafts below
carry a HOLD header and contain no hardware-selection tasks:

- `tvw/audits/dispatch-polarfire-bench-cwodmr-2026-07-09.md` — polarfire
  lane: integration plan for whatever hardware Jason picks, golden-image
  protection, B1 acquisition script stub.
- `tvw/audits/dispatch-odmr-bench-dataspec-2026-07-09.md` —
  odmr-vector-tracking lane: pure data-spec work (sweep parameters,
  fidelity-check quantities, geometry metadata). nv-sensor-sim gets a
  follow-on sim-calibration dispatch once first real sweeps exist — not
  dispatched now.

## 6. Decision requested from Jason

1. Approve or reject elevation.
2. If approved: pick hardware from §3 (floor ~$1.4k / recommended ~$2.8k /
   stretch ~$6.5k) — TVW can assemble the exact cart on request.
3. Only then relay the two dispatches.
4. Optional: request quotes from qutools/CIQTEK only if build-labor becomes
   the constraint.
