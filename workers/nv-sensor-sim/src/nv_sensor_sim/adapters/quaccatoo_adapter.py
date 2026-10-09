"""QuaCCAToo adapter — cross-validation backend (HZB).

QuaCCAToo provides pre-built NV ground-state Hamiltonians with
zero-field splitting, hyperfine coupling, Zeeman interaction, and
P1 center DEER sensing (Example 07). This adapter will be implemented
for cross-validation of SimOS results.

See: github.com/QISS-HZB/QuaCCAToo
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nv_sensor_sim.config import SimulationConfig


class QuaCCATooAdapter:
    """Cross-validation adapter using QuaCCAToo (HZB)."""

    def __init__(self, config: SimulationConfig) -> None:
        raise NotImplementedError(
            "QuaCCAToo adapter not yet implemented. Use SimOSAdapter as the primary backend."
        )

    def generate_odmr_spectrum(self, **kwargs):
        raise NotImplementedError
