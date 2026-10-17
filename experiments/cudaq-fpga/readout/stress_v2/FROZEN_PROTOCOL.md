# Readout drift and calibration stress extension

Frozen 2026-10-17, before generation or evaluation. All v1 data, model weights, integer cores, and ABI remain unchanged.
The new seed is 202610171304. Each of five scenarios uses separate development, validation, and final physical parameter groups.
Final groups are independent from all previous datasets. Known-label calibration shots are separate from evaluation shots within each group.

The deployed method remains the frozen v1 boxcar. Compare raw input, host-calibrated input, a local matched filter, and shrinkage LDA.
Both comparator classifiers use only their group's calibration shots. No algorithm or threshold is selected from final results.
Host calibration estimates an affine IQ transform from calibration means and known nominal waveforms.
It does not receive hidden detuning, gain, phase, offsets, relaxation times, or final labels.
Final records include additional post-calibration receiver drift, defined in config.json.

The generator adds gain and phase drift, IQ imbalance, DC offsets, correlated noise, cavity mismatch, and stochastic relaxation.
Each excited record draws one exponential transition time. The cavity response remains continuous across that transition.
This is a prescribed stochastic relaxation model plus classical receiver noise. It is not a measurement-conditioned quantum trajectory simulation.
All parameter ranges are explicit assumptions. They are not measured hardware distributions.

Correctness gates concern model limits, independent numerical agreement, split isolation, exact integer arithmetic, and export integrity.
Utility gates are exploratory: nominal accuracy >=97%; receiver-drift accuracy >=90%; calibration gain >=3 percentage points.
Calibration coverage must exceed 95% in those two scenarios. Other stress scenarios diagnose limits without changing acceptance.
A utility failure does not authorize threshold relaxation or final-set tuning.

The export preserves Q11 interleaved I/Q input and the existing Q25 int64 score.
Only host preprocessing changes between raw and calibrated modes. Calibration is not implemented in FPGA fabric.
Raw and calibrated exports are paired views of the same underlying shots, not independent observations.
Export every final shot and valid calibrated view; do not select only correct classifications.
All source and artifact hashes, versions, ranges, decisions, and failure receipts will be retained.

Physics context comes from Blais et al., Circuit quantum electrodynamics, Section V.C.
Bengtsson et al., Model-based Optimization of Superconducting Qubit Readout, discusses readout relaxation and calibrated parameters.
Burnett et al., Decoherence benchmarking of superconducting qubits, reports temporal decoherence variability.
These sources motivate mechanisms. They do not validate our chosen numerical distributions.

Sources: https://arxiv.org/pdf/2005.12667 ; https://arxiv.org/pdf/2308.02079 ; https://arxiv.org/abs/1901.04417
