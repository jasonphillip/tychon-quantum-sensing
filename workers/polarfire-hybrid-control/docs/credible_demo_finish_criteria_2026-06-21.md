# Credible Demo Finish Criteria - 2026-06-21

## Decision

The demo should be framed as a hardware-real hybrid control platform with an
honest, modest NN assist, not as a large ML-accuracy breakthrough.

The watchdog acceptance target is now:

- **2 ms fabric watchdog**, implemented as
  `WATCHDOG_TIMEOUT_CYCLES=250000` at 125 MHz.

This replaces the prior "exact 1 ms or bust" finish line for the Phase-I demo
story. A 1 ms build is still nice-to-have, but it is not required to make the
demo defensible.

## Why 2 ms Is Honest

- The Libero handoff/export blocker was resolved for the revised 2 ms target in
  `libero/reports/2026-06-21-watchdog-2ms/`.
- A verified 2 ms fabric watchdog is still a roughly 250x improvement over the
  prior 500 ms host-paced demo caveat.
- The claim becomes "2 ms fabric watchdog built, programmed, and checked on silicon," not
  "verified 1 ms safety."

## ML Claim

The deployed `fcnn_v2_residual_dataset_a` result should be described as:

- **about 5% deployed INT8 residual improvement over the PID baseline** on the
  simulator-derived held-out split.

Do not use the failed cascade's `8.71%` number as a current deployed result.
Do not present the NN as the core achievement. The NN is a bounded feedforward
assist layered on a real FPGA PID/safety datapath.

## What Is Worth Showing

The demo is worth showing if the first-screen story is:

1. Production MPFS250T silicon is running the V250 and clean idfix2 two-slot PID
   datapath.
2. Dashboard LIVE mode uses guarded M0 writes and M1 actuator readback.
3. Latency is measured with clear method caveats.
4. The actuator path, clamp behavior, and watchdog status are visible and
   evidence-backed.
5. The NN assist is modest but real, bounded, and honestly sourced.

## Revised Finish Criteria

For a credible near-term demo, finish when these are true:

1. Dashboard/live hardware path remains idfix2-gated and passes invalid-host,
   V250, CSR, actuator, and clamp smoke checks.
2. Latency table includes V250, PID pulse/read, and host-paced loop evidence,
   with pure fabric-cycle latency either measured or explicitly deferred.
3. A watchdog image is exported and programmed only after rollback gates; V250,
   CSR, actuator, and watchdog clear/trip behavior are checked on silicon. A
   physical cold power-cycle remains an operator follow-up if required by V250
   initialization.
4. SmartPower is either workload-annotated with nonzero VCD activity or clearly
   labeled default/vectorless.
5. The public ML statement says about 5%, simulator-derived, deployed INT8; it
   does not imply real NV validation or a large NN gain.

Still future/Phase-II unless separately proven:

- autonomous host-detached closed loop;
- real NV dataset validation;
- NN/plant formal certificate;
- environmental or flight qualification.
