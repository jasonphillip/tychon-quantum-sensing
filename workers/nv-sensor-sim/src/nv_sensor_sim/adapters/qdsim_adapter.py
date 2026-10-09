"""QDsiM adapter — noise injection from parameterized noise catalog.

QDsiM provides: seven-level NV model for CW wide-field ODMR,
parameterized noise catalog (photon shot noise, laser RIN, MW power
noise, MW phase noise, MW frequency jitter, temperature-dependent
ZFS shifts, dephasing distributions), and complete vector magnetic
field reconstruction.

STATUS: No released code. The reference paper is arXiv:2601.11649
("QDsiM: A Noise-Aware Simulation Toolkit for Quantum Diamond
Microscope", 2026-01-15). Re-verified 2026-08-28 (TVW external
sweep): the name "QDsiM" resolves to no public repository on GitHub
or Hugging Face — the only name-matches are unrelated dormant QDSim
projects (2016/2019). If code is ever released, implement here.
Until then, QDsiM's documented noise parameters are used via
physics/parameters.py and injected through SimOS (see
physics/noise_injection.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nv_sensor_sim.config import SimulationConfig


class QDsiMAdapter:
    """Noise injection adapter using QDsiM parameterized noise catalog."""

    def __init__(self, config: SimulationConfig) -> None:
        raise NotImplementedError(
            "QDsiM adapter not implemented — no public repository available. "
            "Noise injection is handled via SimOS + physics/noise_injection.py."
        )

    def generate_odmr_spectrum(self, **kwargs):
        raise NotImplementedError
