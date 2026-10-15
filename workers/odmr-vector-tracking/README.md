# odmr-vector-tracking

**Learned tracking of NV-diamond ODMR resonances through frequency-space crossings — to extend
vector-magnetometer dynamic range without a larger bias field.**

Part of [Tychon quantum sensing](../../README.md), as the fourth worker (started 2026-06-29). It trains on time-series datasets from [`nv-sensor-sim`](../nv-sensor-sim/README.md) ([synthetic-data walkthrough](../../docs/synthetic-data.md)) and produces FP32 PyTorch checkpoints and evaluation reports in [`docs/`](docs/). It works in simulation only and is not connected to the FPGA loop.

## The problem in one paragraph

A nitrogen-vacancy (NV) ensemble magnetometer reads a full 3-component **B** by resolving the
four crystallographic NV axes, separated in frequency by a static bias field and tracked with a
lock-in amplifier + PID loop. When a large external field shifts the resonances until lines from
*different* axes cross, the lock loop — which follows a frequency, not an identity — mis-assigns
them and loses lock. That crossing is the recognized residual limit on frequency-locked vector
dynamic range (MIT Lincoln Lab, Clevenson et al., *APL* 112, 252406, 2018). The conventional
remedy is a bigger bias magnet (more line spacing), at a real hardware/SWaP/conops cost.

## The bet

Replace "track a frequency" with **"track an identity"**: a physics-informed, sequential model
that maintains the per-axis association *through* crossings, using each axis's hyperfine
signature and known Zeeman slope as a fingerprint. This extends usable dynamic range at a fixed
(smaller) bias. It is also the function that justifies a learned block alongside the FPGA PID —
the model does association/estimation, the PID does the fast loop, a safety layer bounds it.

## Where it sits

| Repo | Role |
|---|---|
| `nv-sensor-sim` | physics + datasets (owns resonance freqs, 8×3 geometry, bias regimes, the field-trajectory/collision generator) |
| **`odmr-vector-tracking`** (this) | the learned through-crossing tracker; FP32 PyTorch models today. A TFLite export is planned, not done |
| `polarfire-hybrid-control` | `vnnx_compile -c V250`; PID + NPU hybrid on MPFS250T silicon. This tracker has not been compiled or run there |
| `odmr-edge-ml` | sibling ML repo — the static scalar-residual regressor |

## Quick start

Run from `workers/odmr-vector-tracking`, with Python 3.11 or later:

```bash
cd workers/odmr-vector-tracking
make install      # pip install -e ".[dev]"
make test-unit
```

Training and evaluation scripts in `experiments/` read sequence datasets from `data/<name>` (gitignored). Generate them with the simulator's `scripts/generate_sequence_dataset.py` and the `sequence_*.yaml` configs.

## Status

> **Comparison-study verdict (2026-10-15; pre-registered, confirmed on two sealed final sets).** Under realistic conditions (5 MHz lines, 1.5 % contrast, SNR 10, baseline slope, frequency offset) and in every stress cell, a classical per-frame fit followed by exact Hamiltonian inversion (`tracking/exact_inversion_baseline.py`) beats this learned tracker as trained (realistic cell: RMSE 0.93 vs 5.81 mT, angular p90-of-p90 68° vs 170°); the tracker holds a full-vector lock on at most 4 % of sequences in any cell. On clean narrow-line spectra the two split (tracker better angular p90, classical better RMSE and far fewer lost sequences) and neither is reliable. The classical estimator is therefore the study's reference; the learned tracker is not a usable estimator in its current form. The sentence below about "reliably to about 30–40° off the bias axis" describes the older standing evaluation and is superseded by this verdict. Protocol, addenda (a)–(j), results and decisions: `docs/comparison_study_protocol_2026-10.md`, `docs/comparison_study_decision_2026-10.md`, `docs/comparison_study_decision_2026-10_v2.md`.

Started 2026-06-29. Research-grade; the founding literature + prior-art sweep and the build
plan are in [`docs/`](docs/). Honest ceilings: ESLAC ~51 mT, GSLAC ~102.4 mT — target regime
~few mT → ~50 mT.

**Default model: v6, an FP32 research default** (angular-coverage checkpoints + per-family
re-decode policy). It is the default for research evaluation in FP32 simulation. It is not a
deployed model. The canonical registry, md5s, decode policy, trade-off caveat, and measured
boundary are in [`docs/deployable_default.md`](docs/deployable_default.md).

Readiness of v6, one state at a time:

| state | v6 |
|---|---|
| trained (FP32) | yes, on simulated data |
| evaluated | yes, on synthetic sets only: the v1 standing eval (noise rungs clean to snr3), the dwell sets and the field-cone set |
| exported (INT8 or other format) | no |
| compiled for a target | no |
| executed on target hardware | no; there is no on-target parity run, and the tracker is not in the FPGA loop |

The tracker works in FP32 simulation only, reliably to about 30–40° off the bias axis, on
generic geometries. That figure comes from the field-cone set (clean rung, simulated). Coverage is
**geometry-specific**: it is exact on the directed degeneracy geometries, with a hard cliff past
the training envelope and a binding 3.0 mT field floor — not a blanket angle capability. The v2
checkpoints stay pinned as the sharper in-cone identity reference (numbers quoted from them must
say "v2 checkpoints").

See [`CLAUDE.md`](CLAUDE.md) for scope boundaries and cross-repo rules, and
[`docs/design/02_approach_and_testbed.md`](docs/design/02_approach_and_testbed.md) for the
first build increment.
