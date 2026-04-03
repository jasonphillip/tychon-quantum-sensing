"""High-level Hamiltonian construction composing SimOS primitives.

Provides functions to build NV Hamiltonians with temperature-shifted ZFS,
transverse B_perp injection, and P1 concentration effects.
"""

from __future__ import annotations

import numpy as np

from simos.systems import NV

# Temperature coefficient of ZFS: dD/dT ≈ -74.2 kHz/K
_DD_DT_HZ_PER_K = -74.2e3
_T_REF_K = 300.0
_GAMMA_NV = NV.yNV


def temperature_zfs_shift(temperature_K: float, reference_T: float = _T_REF_K) -> float:
    """Compute ZFS shift due to temperature deviation.

    Parameters
    ----------
    temperature_K : float
        Current temperature in Kelvin.
    reference_T : float
        Reference temperature in Kelvin (default 300 K).

    Returns
    -------
    float
        ZFS shift in angular frequency (rad/s).
    """
    delta_D_hz = _DD_DT_HZ_PER_K * (temperature_K - reference_T)
    return 2 * np.pi * delta_D_hz


def build_nv_hamiltonian(
    nv_system: NV.NVSystem,
    B_field: np.ndarray,
    temperature_K: float = 300.0,
    b_perp_T: float = 0.0,
    use_optics: bool | None = None,
) -> tuple:
    """Build the full NV Hamiltonian with temperature and transverse field corrections.

    Parameters
    ----------
    nv_system : NV.NVSystem
        SimOS NV system instance.
    B_field : np.ndarray
        Magnetic field 3-vector [Bx, By, Bz] in Tesla.
    temperature_K : float
        Sample temperature in Kelvin.
    b_perp_T : float
        Transverse magnetic field magnitude in Tesla.
    use_optics : bool or None
        If True, treat as optical model (returns H_GS, H_ES).
        If False, treat as spin-only (returns (H,)).
        If None, auto-detect from nv_system attributes.

    Returns
    -------
    tuple
        If optics enabled: (H_GS, H_ES).
        If optics disabled: (H,) single-element tuple.
    """
    result = nv_system.field_hamiltonian(Bvec=B_field)
    delta_D_rad = temperature_zfs_shift(temperature_K)

    has_optics = use_optics if use_optics is not None else (
        hasattr(nv_system, "GSp") and nv_system.GSp is not None
    )
    if has_optics:
        # Optical model: returns (H_GS, H_ES)
        H_GS, H_ES = result
        H_GS = H_GS + delta_D_rad * (nv_system.Sz * nv_system.Sz)
        H_GS = add_transverse_field(nv_system, H_GS, b_perp_T)
        return H_GS, H_ES
    else:
        H = result + delta_D_rad * (nv_system.Sz * nv_system.Sz)
        H = add_transverse_field(nv_system, H, b_perp_T)
        return (H,)


def add_transverse_field(nv_system: NV.NVSystem, H, b_perp_T: float):
    """Add transverse B_perp as off-diagonal Zeeman terms.

    Injects B_perp along x-axis as Sx coupling, producing mixing of
    spin states and Fano-like asymmetric ODMR profiles.

    Parameters
    ----------
    nv_system : NV.NVSystem
        SimOS NV system instance.
    H : Qobj
        Hamiltonian to modify.
    b_perp_T : float
        Transverse field magnitude in Tesla.

    Returns
    -------
    Qobj
        Modified Hamiltonian.
    """
    if b_perp_T == 0.0:
        return H
    return H + _GAMMA_NV * b_perp_T * nv_system.Sx
