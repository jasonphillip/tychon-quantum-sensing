# odmr-vector-tracking

This worker tests learned association of NV-diamond ODMR resonances through frequency-space crossings. A registered comparison on two sealed synthetic sets selected classical exact inversion as the reference under realistic conditions ([protocol](docs/comparison_study_protocol_2026-10.md)). Jason directed the coding agents and checked written claims with local critics. The worker uses [`nv-sensor-sim`](../nv-sensor-sim/README.md) time-series datasets and publishes FP32 evaluations in [`docs/`](docs/).

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
signature and known Zeeman slope as a fingerprint. The proposed method targets a fixed bias. In the broader system,
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

> **Comparison-study verdict (2026-10-15; pre-registered, confirmed on two sealed final sets).** Under realistic conditions (5 MHz lines, 1.5 % contrast, SNR 10, baseline slope, frequency offset) and in eleven of the twelve stress cells on each of two sealed sets, a classical per-frame fit followed by exact Hamiltonian inversion (`tracking/exact_inversion_baseline.py`) beats this learned tracker as trained (realistic cell: RMSE 0.93 vs 5.81 mT, angular p90-of-p90 68° vs 170°); the tracker loses 96 to 100 % of sequences in every cell of both sets and is locked on at most 4 % of frames (protocol Addendum (l)). On clean narrow-line spectra the two split (tracker better angular p90, classical better RMSE and far fewer lost sequences), and the classical estimator still loses 44 to 48 % of sequences. The classical estimator is therefore the study's reference; the learned tracker is not a usable estimator in its current form. The sentence below about "reliably to about 30–40° off the bias axis" describes the older standing evaluation and is superseded by this verdict. Protocol, addenda (a)–(l), results and decisions: `docs/comparison_study_protocol_2026-10.md`, `docs/comparison_study_decision_2026-10.md`, `docs/comparison_study_decision_2026-10_v2.md`.

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

See [`AGENTS.md`](AGENTS.md) for scope boundaries and cross-repo rules, and
[`docs/design/02_approach_and_testbed.md`](docs/design/02_approach_and_testbed.md) for the
first build increment.
