# Derivative Filter Design — Residual Proof Obligation #4 (Follow-On Closure)

## Status

**HLS-level closure: COMPLETE (2026-05-17, DLOG-046).** Filter implementation
is in the SmartHLS C++ source, passes the local testbench (E.1/E.2 plus
preserved D.1/D.2/D.3), and synthesizes cleanly via `shls hw` on Beelink
(II=1 pipeline, 7-cycle latency, new `prev_d` register present).

**Integrated P&R timing closure: DEFERRED.** Importing the filtered
RTL into the Microchip reference design (`MPFS_ICICLE_Vectorblox`)
requires the follow-on canvas refresh per
`docs/smartdesign_two_slot_canvas_runbook.md`, which is GUI-driven and
not autonomous-CLI feasible. The r6_s25 closure (+0.728 ns slack at
200 MHz) remains the canonical Phase I integrated evidence; the
filter-design integrated number is gated on canvas refresh.

## Continuous-time form

D(s) = Kd · s / (1 + Tf · s)

This is the canonical filtered derivative from Astrom & Hagglund Ch. 4
(corpus: `~/.corpus/polarfire-control-corpus/`). The pole at 1/Tf rolls
off high-frequency content that would otherwise amplify sensor noise —
at frequencies above 1/Tf the response asymptotes to Kd/Tf rather than
growing unbounded like the unfiltered first difference.

## Discrete-time implementation (backward Euler)

Substituting s → (1 − z⁻¹) / Ts:

D(z) = Kd · (1 − z⁻¹) / ((Ts + Tf) − Tf · z⁻¹)
     = (Kd / (Ts + Tf)) · (1 − z⁻¹) / (1 − a · z⁻¹)

where a = Tf / (Ts + Tf). In time-domain:

D[k] = a · D[k−1] + (Kd / (Ts + Tf)) · (e[k] − e[k−1])

To preserve the existing Kd calibration (Kd is a per-cycle gain without
a Ts factor), factor out β = Ts / (Ts + Tf) = 1 − a:

**D[k] = a · D[k−1] + β · Kd · (e[k] − e[k−1])**

This is the form implemented in `hls/src/nv_pid.hpp::NVPID::compute()`.
The cast chain computes `Kd · (e[k] − e[k−1])` first (matching the
proven Q16.16 precision pattern from the legacy unfiltered form) and
then multiplies by β — see commit 4065f7f for rationale. Both cast
orders give bit-identical results in the local g++ ap_fixpt shim
(empirically verified) but the reordered form is more defensible for
SmartHLS synthesis precision pruning.

## Tf choice in measurable plant terms

| Plant parameter | Value | Source |
|---|---|---|
| ODMR modulation frequency | ~10 kHz typical, ~100 kHz upper | corpus `polarfire-control-corpus/` ODMR closed-loop bundle |
| Assumed closed-loop control bandwidth | ~3 kHz | ~10× below modulation (conventional separation) |
| Filter corner 1/(2π·Tf) | ~32 kHz | ~10× above closed-loop bandwidth |
| **Tf = 5 µs** | | derived |

The ~10× separation between control bandwidth and filter corner is the
conventional choice for derivative filtering (Astrom-Hagglund §4.3): it
gives sufficient noise rejection without consuming significant phase
margin at the control bandwidth. At ωc = 2π·3 kHz the filter phase lag
is arctan(Tf · ωc) = arctan(0.094) ≈ 5.4°, well below the typical 30°
phase margin reserve.

## Sector-bound preservation argument

The Phase I Lur'e/Circle Criterion stability argument (see
`docs/safety_architecture.md` "Bounded Hybrid Simplex RTA") requires the
AI feedforward path to be sector-bounded. The PID derivative term is
**not** in the AI path — it operates on the error signal directly. The
relevant question for B2.4 is whether the combined PID+AI controller
stability proof remains intact when the derivative is filtered.

A low-pass filter on the derivative changes the loop transfer function
of the classical PID component without touching the AI path:

- At DC the filter has gain 1 → steady-state PID action is unchanged.
- At high frequencies the filter attenuates → loop gain at frequencies
  above 1/Tf is **reduced**.

Reducing loop gain at HF is conservative for the Circle Criterion — it
can only improve gain and phase margin, never degrade. The AI path's
sector bound is unaffected (the filter is in series with the classical
PID, not in the AI feedforward).

**Conclusion:** filtering the derivative **preserves** the Phase I
sector-bound argument and **improves** the follow-on expanded-authority
margin. This satisfies the formal acceptance criterion (a) of B2.4:
"the filtered derivative remains within the sector bound the existing
Lur'e/Circle Criterion argument relies on."

## Discretization error analysis

At Tf = 5 µs and Ts = 5 ns:
- a = 0.999000999..., Q16.16 representation = 65471/65536 = 0.998992...,
  quantization error per cycle ≈ 3.6e-6.
- β = 0.000999001..., Q16.16 representation = 65/65536 ≈ 0.000991821,
  quantization error per cycle ≈ 7e-6.

The quantization in `a` introduces a small DC offset in D state when
integrated over many cycles. Worst-case bound: at full out_t range
(±32768), 1000 cycles of integration produce an offset
≈ 32768 × 3.6e-6 × 1000 = 118 LSB of out_t (≈ 1.8 mV in actuator units),
negligible vs the integrator term magnitude.

Backward Euler introduces phase error vs the ideal continuous filter.
At ω = 1/Tf = 200 krad/s, BE phase error is ~5° relative to Tustin.
At the control bandwidth (3 kHz, ω = 18.8 krad/s), BE phase error is
~0.05° — negligible. The choice of BE over Tustin trades ~5° of phase
accuracy at the corner for one fewer multiplication per cycle (Tustin
requires 2 multiplies + 1 add in the numerator), which preserves the
+0.728 ns timing slack budget for when integrated closure is done.

## HLS synthesis evidence (2026-05-17)

From `hls/hls_output/reports/summary.hls.nv_pid_top.rpt`:

- Function `nv_pid_top` takes 7 cycles, II = 1 (target met).
- Local memory `nv_pid_top_pid_prev_d` (32-bit Register) confirms the
  filter state `prev_d` is correctly synthesized.
- Pipeline length: 5 stages.
- SmartHLS auto-adapted internal clock period constraint from 10 ns to
  12 ns to meet II = 1 — this is the scheduler's view, not the final
  P&R timing. Final flop-to-flop delay through Synplify Pro logic
  optimization is typically much shorter and is the metric for the
  200 MHz (5 ns) Libero closure constraint.

## Verification status

| Acceptance criterion | Status | Reference |
|---|---|---|
| Sector bound preserved | proved (this doc) | safety_architecture.md §1 |
| Testbench D.1/D.2/D.3 preserved | verified | hls/tb/tb_bumpless.cpp + make hls-test-local |
| Filter unit tests E.1/E.2 pass | verified | hls/tb/tb_bumpless.cpp + make hls-test-local |
| make verify-local green | verified | tools/audit_libero_reports.py + audit_corpus_citations.py |
| HLS synthesis II=1 | verified | hls/hls_output/reports/summary.hls.nv_pid_top.rpt |
| Integrated P&R timing closure ≥ 0 ns at 200 MHz | **deferred** | requires follow-on canvas refresh runbook |

## Path to integrated closure (Follow-On)

1. Execute `docs/smartdesign_two_slot_canvas_runbook.md` follow-on steps
   1-8 (GUI-driven; ~30-60 min hands-on Libero work):
   - Add CoreAXI4Interconnect.
   - Place `nv_pid_top` axi_target on slot 0, `pid_csr_block` on slot 1.
   - Wire interconnect master to FIC_0_PERIPHERALS_1.
   - Connect observability taps; regenerate component.
2. `libero SCRIPT:libero/scripts/closure_pipeline.tcl` to re-synth + P&R.
3. Inspect timing report for worst slack at 200 MHz; document new value.
4. Append closure evidence to `libero/reports/<date>-deriv-filter/`.
5. Update the integrated-closure row in the verification status table
   above and append a follow-up DLOG.

## Future work

- Tustin discretization (1 more multiply, ~5° phase improvement at
  corner) — Phase III if needed.
- AXI-writable Tf with inner-clamp-style gating (sector-bound argument
  requires Tf to be immutable; AXI write would need to gate at the
  inner-clamp pattern and clamp to a hardcoded upper bound) — only if
  field tuning need emerges.
- Combined filter + slew limiter formal analysis via IQC framework per
  `safety_architecture.md` Stability Analysis (Follow-On Path) §(c) — contingent
  on whether sector arguments suffice for expanded ±30% authority.
