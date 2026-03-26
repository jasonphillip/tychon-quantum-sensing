"""CUDA-Q adapter — GPU-accelerated NV simulation.

CUDA-Q Dynamics provides GPU-accelerated Lindblad master equation
solvers. The NV+P1 demo achieves 64% runtime reduction on Blackwell.
This adapter will wrap cudaq for GPU-accelerated validation.

Requires: pip install cudaq (ARM64 wheels for DGX Spark)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tychon_nv_sim.config import SimulationConfig


class CudaQAdapter:
    """GPU-accelerated NV simulation adapter using CUDA-Q Dynamics."""

    def __init__(self, config: SimulationConfig) -> None:
        raise NotImplementedError(
            "CUDA-Q adapter not yet implemented. Use SimOSAdapter as the primary CPU backend."
        )

    def generate_odmr_spectrum(self, **kwargs):
        raise NotImplementedError
