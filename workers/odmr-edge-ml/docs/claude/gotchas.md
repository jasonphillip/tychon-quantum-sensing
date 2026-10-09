# odmr-edge-ml — known gotchas

Companion to `CLAUDE.md` (the map). Moved here verbatim from `CLAUDE.md` on 2026-09-04. The "Scalar residual" bullet also stays in `CLAUDE.md` § Modeling rule because it constrains every production model.

## Known Gotchas

- **FCNN TFLite export**: The FCNN uses `batch_shape` in its forward pass which can introduce dynamic shape ops. `scripts/fix_fcnn_export.py` patches this for V250 compatibility.
- **torch.ao.quantization deprecation**: FX QAT raises DeprecationWarning on torch>=2.10. Suppress with `warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")`. Functionally correct on torch 2.11.
- **Scalar residual, not 3D vector**: CW-ODMR spectra at target field strengths (20-70 µT) cannot resolve B-field direction due to quantum degeneracy. All production models predict scalar ΔB residual corrections, not 3D vectors. The config default `output_dim: 3` is legacy — experiments override to `output_dim: 1`.
