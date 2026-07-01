# NN Sector Certificate Plan - 2026-06-21

## Status

PARTIAL research setup only. No sector, Lipschitz, IQC, or closed-loop certificate was produced in this pass.

The current defensible claim remains: the demo has hardware clamps/slew/watchdog guards and a Lur'e/Circle-Criterion framing, but formal NN-in-loop stability is still a residual proof obligation. A real certificate still needs both the deployed network bound and a plant sector/model from roadmap #11.

## Objective

Certify a usable sector or Lipschitz bound for the deployed `fcnn_v2_residual_dataset_a` feedforward map, then feed that bound into the existing Circle-Criterion/IQC safety argument.

The certification target must be tied to a frozen deployed artifact, not an informal architecture description:

- float checkpoint SHA: `e0c314265017a999cd57c2b0c168c2d3dc229c9edbb3c630887ffb94ff57ed0a`
- deployed INT8/TFLite SHA: `e3b55da96ee633a58109007d4244304e2ad4a22853b10335fa41879e815b5371`
- V250 probe model: `fcnn_v2_residual_dataset_a.vnnx`

## Local Evidence

- `docs/safety_architecture.md` already frames the AI feedforward path as a sector-bounded nonlinearity but lists ReLU/NN sector verification and plant-model identification as open obligations.
- `docs/remediation_roadmap.md` #10 correctly says #10 depends on the deployed net plus #11 plant sector before the loop claim can close.
- `~/.corpus/polarfire-control-corpus/manifest.json` contains local references for Khalil/Circle-Popov, strengthened Circle/Popov for ReLU feedback, and Zames-Falb/IQC NN nonlinearities.
- `~/.corpus/polarfire-control-corpus/raw/arxiv.org/pdf250522889.md` is a useful recent lead for local sector bounds for FFNNs in a positive Lur'e framework, but it is not yet applied to this plant or net.

## Tool Leads Checked

- [alpha,beta-CROWN](https://github.com/Verified-Intelligence/alpha-beta-CROWN): good first verifier for ONNX/property feasibility and branch-and-bound bounds.
- [auto_LiRPA](https://github.com/Verified-Intelligence/auto_LiRPA): useful lower-level bound propagation library for CROWN/DeepPoly-style bounds on PyTorch graphs.
- [LipSDP](https://github.com/arobey1/LipSDP): SDP-based Lipschitz estimation lead for ReLU networks.
- [Marabou](https://github.com/NeuralNetworkVerification/Marabou): fallback SMT-style neural-network verifier if the exported property is awkward for CROWN tooling.

## Proposed Certificate Flow

1. Freeze the exact model artifact set: PyTorch checkpoint, TFLite, VNNX, normalization constants, and output dequantization constants.
2. Export the float network to ONNX and verify operator support. If the deployed INT8 graph is materially different, create a dequantized TFLite-to-ONNX surrogate and record the approximation boundary.
3. Define the input domain from the real deployment domain, not arbitrary uniform spectra. Start with the held-out `production_50k_v2_aic` min/max envelope plus a margin, then tighten to any known physical ODMR envelope.
4. Run alpha,beta-CROWN/auto_LiRPA for output bounds and local slope/Jacobian bounds over the chosen domain.
5. Run LipSDP or QC/IQC analysis for a global or domain-local Lipschitz bound. Expect global bounds to be conservative; a local/regime-bounded certificate is likely more useful.
6. Convert the NN bound into the sector notation used by `docs/safety_architecture.md`.
7. Combine with #11 plant sector and #9 measured ZOH/transport delay. Until those are present, mark the result as "NN bound only," not "closed-loop stability verified."

## Done When

- A committed certificate records tool version, model hashes, property file, input domain, bound value, runtime, and reproducer command.
- The safety doc is updated with the exact bound and its scope.
- Any dashboard/report language says "certified within <domain>" only after #9 and #11 are also resolved.

## Next Commands

```bash
cd ~/projects/odmr-edge-ml
python3 experiments/fcnn_v2_int8_float_equivalence.py

# Follow-up work:
# export deployed float model to ONNX
# run alpha,beta-CROWN/auto_LiRPA on the ONNX + property
# run LipSDP or QC/IQC bound estimation on the frozen ReLU network
```
