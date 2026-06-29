# odmr-vector-tracking

**Learned tracking of NV-diamond ODMR resonances through frequency-space crossings — to extend
vector-magnetometer dynamic range without a larger bias field.**

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
| **`odmr-vector-tracking`** (this) | the learned through-crossing tracker; produces a TFLite model |
| `polarfire-hybrid-control` | `vnnx_compile -c V250`; PID + NPU hybrid on MPFS250T silicon |
| `odmr-edge-ml` | sibling ML repo — the static scalar-residual regressor |

## Status

Inception (2026-06-29). Research-grade; the founding literature + prior-art sweep and the build
plan are in [`docs/`](docs/). Honest ceilings: ESLAC ~51 mT, GSLAC ~102.4 mT — target regime
~few mT → ~50 mT.

See [`CLAUDE.md`](CLAUDE.md) for scope boundaries and cross-repo rules, and
[`docs/design/02_approach_and_testbed.md`](docs/design/02_approach_and_testbed.md) for the
first build increment.
