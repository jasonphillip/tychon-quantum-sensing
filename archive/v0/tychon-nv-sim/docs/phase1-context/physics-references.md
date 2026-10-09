# Physics References

*Extracted from Section 3.5 of the architecture decisions document.*

Key external resources from the Fast-Track Research Report that accelerate or de-risk Repo 1.

| Resource | Date | URL | Relevance |
|---|---|---|---|
| SimOS (ETH Zürich Degen group) | Nov 2025 | [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0010465525004205) | Core physics engine. ODMR simulation, Lindblad dynamics, stochastic framework. |
| QuaCCAToo (HZB) | 2025 | [GitHub](https://github.com/QISS-HZB/QuaCCAToo) | Cross-validation, pre-built NV Hamiltonian, P1 DEER example. |
| CUDA-Q Dynamics NV+P1 demo | Jun 2025 | NVIDIA docs | GPU-accelerated reference. Physics on Blackwell hardware. |
| cuDensityMat v26.1.0 | Jan 2026 | cuQuantum SDK | GPU Lindblad dynamics with gradient APIs. aarch64 wheels available. |
| Tsunaki et al. digital twin | Oct 2025 | [arXiv:2510.14907](https://arxiv.org/abs/2510.14907) | End-to-end ODMR prediction + stability metrics. Validation blueprint. |
| QDsiM | Jan 2026 | No confirmed public repo | Parameterized noise catalog. Use documented approach as wrappers. |
| QuantumVillage UncutGem | Aug 2025 | [GitHub](https://github.com/QuantumVillage/UncutGem) | Open hardware/firmware reference for ODMR sweep orchestration. |
| Lönard et al. fast ODMR | 2025 | [arXiv:2504.20750](https://arxiv.org/abs/2504.20750) | Analytical resonance frequencies, orders of magnitude faster than diagonalization. |
| CCE P1 bath study | Mar 2025 | [arXiv:2503.05404](https://arxiv.org/abs/2503.05404) | T₂ values at 1-300 ppm P1 concentrations. Use values only, not pulse scaling. |
| SBQuantum space qualification | Sep 2025 | [arXiv:2509.19179](https://arxiv.org/abs/2509.19179) | Thermal cycling data, ~400 pT/√Hz, heading errors <5 nT. |
| Zenodo ODMR dataset | Pre-2026 | Zenodo | Empirical validation data. |
| Non-stationary noise modeling | Accepted 2026 | [PRA](https://journals.aps.org/prapplied/accepted/10.1103/13mr-493z) | Time-varying noise statistics (non-Markovian). |
| Ensemble ODMR computation | Sep 2025 | [arXiv:2509.15427](https://arxiv.org/abs/2509.15427) | Drop-in forward model for ensemble ODMR lineshapes with strain. |
