"""Vendored NV crystal geometry + first-order ODMR resonance physics constants.

These are **fixed crystal/physics constants** — not simulator output. They are the
diamond-lattice ``⟨111⟩`` NV-axis directions, the 8×3 projection matrix the downstream
BLUE inversion uses, the electron gyromagnetic ratio, the zero-field splitting, and the
published linewidth scaling law.

They are vendored here (with a parity test) so this repo's consumer-side code — the
synthetic-fixture generator, the classical baseline, the metrics, and the learned-tracker
geometry decoder — has the geometry without importing ``nv_sensor_sim``. The single source
of truth lives upstream.

TODO(nv-sensor-sim dep): once ``nv_sensor_sim`` is wired as a dependency, replace
``NV_AXES_UNIT`` / :func:`nv_geometry_matrix` with imports of
``nv_sensor_sim.physics.lineshape.{NV_AXES_UNIT, nv_geometry_matrix}`` and
``nv_sensor_sim.physics.parameters.compute_linewidth``. The parity test
``tests/unit/test_geometry.py::test_geometry_matches_nv_sensor_sim`` guards equivalence and
will flip from skip to active once the import resolves.

Sources (read 2026-06-29):
- ``nv-sensor-sim/src/nv_sensor_sim/physics/lineshape.py`` — ``NV_AXES_UNIT``,
  ``nv_geometry_matrix``, ``project_field_onto_axes``.
- ``nv-sensor-sim/src/nv_sensor_sim/physics/hamiltonian.py`` / SimOS ``NV.py`` — gyromagnetic
  ratio and zero-field splitting.
- ``nv-sensor-sim/src/nv_sensor_sim/physics/parameters.py`` — ``compute_linewidth``.
"""

from __future__ import annotations

import numpy as np

# --- Crystal geometry -------------------------------------------------------------------

# Four NV crystallographic axes in the cubic-diamond lattice, as unit vectors in the lab
# frame. Matches ``nv_sensor_sim.physics.lineshape.NV_AXES_UNIT``; the parity test enforces
# equivalence.
NV_AXES_UNIT: np.ndarray = np.array(
    [
        [+1.0, +1.0, +1.0],
        [+1.0, -1.0, -1.0],
        [-1.0, +1.0, -1.0],
        [-1.0, -1.0, +1.0],
    ],
    dtype=np.float64,
) / np.sqrt(3.0)

N_AXES: int = 4
N_LINES_ELECTRONIC: int = 8  # 4 axes × 2 transitions (no hyperfine)

# Per-resonance label arrays for the canonical 8-line ordering (row r of the geometry
# matrix). Row 2i is the +n_i transition (ms0→+1), row 2i+1 is the −n_i transition
# (ms0→−1). These are the association/transition ground-truth conventions the v1 data
# contract uses (``line_axis`` ∈ {0..3}, ``line_transition`` 0=ms0→−1, 1=ms0→+1).
LINE_AXIS_8: np.ndarray = np.array([0, 0, 1, 1, 2, 2, 3, 3], dtype=np.int8)
LINE_SIGN_8: np.ndarray = np.array([+1, -1, +1, -1, +1, -1, +1, -1], dtype=np.int8)
LINE_TRANSITION_8: np.ndarray = np.array([1, 0, 1, 0, 1, 0, 1, 0], dtype=np.int8)


def nv_geometry_matrix() -> np.ndarray:
    """Return the 8×3 NV-axis projection matrix ``A`` used by the BLUE inversion.

    Row ``2i`` is ``+n_i`` and row ``2i+1`` is ``-n_i`` for the four NV axes ``n_i``. The
    first-order frequency shift of resonance ``(i, s)`` under lab field ``B`` is
    ``s · γ_e · (B · n_i)``, so stacking the eight shifts gives ``δ = γ_e · (A @ B)`` and
    least-squares inversion recovers the lab vector.

    Returns
    -------
    np.ndarray
        Shape ``(8, 3)`` projection matrix in the lab frame, dtype float64.
    """
    A = np.zeros((8, 3), dtype=np.float64)
    for i, n in enumerate(NV_AXES_UNIT):
        A[2 * i] = n
        A[2 * i + 1] = -n
    return A


def project_field_onto_axes(
    B_lab_T: np.ndarray,
    nv_axes: np.ndarray = NV_AXES_UNIT,
) -> tuple[np.ndarray, np.ndarray]:
    """Decompose a lab-frame B-field into per-axis parallel/perpendicular parts.

    Parameters
    ----------
    B_lab_T : np.ndarray
        Lab-frame magnetic field 3-vector in Tesla.
    nv_axes : np.ndarray
        Unit vectors for the NV axes, shape ``(4, 3)``. Defaults to :data:`NV_AXES_UNIT`.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(B_par, B_perp_mag)`` arrays of length 4. ``B_par[i]`` is the signed scalar
        projection ``B_lab · n_i`` in Tesla; ``B_perp_mag[i]`` is the transverse magnitude
        for axis ``i`` in Tesla.
    """
    B_lab = np.asarray(B_lab_T, dtype=np.float64).reshape(3)
    B_par = nv_axes @ B_lab
    B_perp_vecs = B_lab[None, :] - B_par[:, None] * nv_axes
    B_perp_mag = np.linalg.norm(B_perp_vecs, axis=1)
    return B_par, B_perp_mag


# --- First-order ODMR physics constants -------------------------------------------------

# Electron gyromagnetic ratio for the NV center, Hz/T. γ ≈ 28 kHz/µT = 28 GHz/T. From SimOS
# ``yNV = ye·(1 + 357e-6)`` with ``ye = -1.76085963023e11`` rad/(s·T): |yNV| / (2π) ≈ 2.8035e10
# Hz/T, matching the upstream v1 contract (``nv-sensor-sim/docs/dataset-contract.md``). The
# real generator's *effective* splitting slope is ≈28.03 GHz/T with ~0.08% per-axis scatter —
# higher-order diagonalization residual a linear BLUE cannot capture (it is part of the honest
# physics that motivates the learned tracker), negligible vs. loss-of-lock error at a crossing.
GAMMA_E_HZ_PER_T: float = 2.8035e10

# Zero-field splitting D, Hz (SimOS value; used by the common-mode shift below). Note: D and the
# absolute center cancel in the per-axis *splitting*, which is what the BLUE inverts.
ZFS_D_HZ: float = 2.871e9

# Temperature coefficient of D, Hz/K (Acosta; nv-sensor-sim hamiltonian.py).
DD_DT_HZ_PER_K: float = -74.2e3


def resonance_frequencies(
    B_lab_T: np.ndarray,
    zfs_hz: float = ZFS_D_HZ,
    gamma_hz_per_t: float = GAMMA_E_HZ_PER_T,
) -> np.ndarray:
    """First-order (linear-Zeeman) 8-line ODMR resonance frequencies for a lab-frame field.

    Returns the eight centers in canonical row order (axis ``r // 2``, sign ``+`` for even ``r``)
    using the signed convention ``f[r] = D + sign[r] · γ_e · (n_{r//2} · B)`` that matches
    :func:`nv_geometry_matrix`. This is a building block; the **real upstream** ``resonance_freqs``
    are *diagonalized* centers (see :func:`resonance_frequencies_diagonalized`) that add a
    second-order common-mode shift. The per-axis *splitting* is identical for both
    (``(f₊ − f₋)/2 = γ_e·(B·n_i)``, common-mode cancels), which is why the BLUE inverts the
    splitting — see :func:`axis_projections_from_resonances`.

    Returns
    -------
    np.ndarray
        Shape ``(8,)`` resonance frequencies in Hz, dtype float64.
    """
    B_par, _ = project_field_onto_axes(B_lab_T)
    shifts = gamma_hz_per_t * LINE_SIGN_8.astype(np.float64) * B_par[LINE_AXIS_8]
    return zfs_hz + shifts


def common_mode_shift(
    b_perp_mag_T: np.ndarray | float,
    gamma_hz_per_t: float = GAMMA_E_HZ_PER_T,
    zfs_hz: float = ZFS_D_HZ,
) -> np.ndarray:
    """Second-order transverse-field common-mode center shift, ``Δf ≈ 1.5·(γ·B⊥)²/D`` (Hz).

    Applied identically to *both* transitions of an axis (so it cancels in the splitting). At
    the few-mT honest-regime this is 3–16 linewidths — not negligible — which is why first-order
    centers do not sit on the real dips. Verified against the upstream sequence dataset.
    """
    b_perp = np.asarray(b_perp_mag_T, dtype=np.float64)
    return 1.5 * (gamma_hz_per_t * b_perp) ** 2 / zfs_hz


def resonance_frequencies_diagonalized(
    B_lab_T: np.ndarray,
    zfs_hz: float = ZFS_D_HZ,
    gamma_hz_per_t: float = GAMMA_E_HZ_PER_T,
) -> np.ndarray:
    """8-line centers with the second-order common-mode shift (matches upstream diagonalization).

    ``f[r] = D + sign[r]·γ_e·(B·n_i) + Δf_common(i)``. The synthetic fixtures use this so their
    line centers are realistic; the splitting still equals ``γ_e·(B·n_i)`` exactly.
    """
    B_par, B_perp = project_field_onto_axes(B_lab_T)
    first_order = gamma_hz_per_t * LINE_SIGN_8.astype(np.float64) * B_par[LINE_AXIS_8]
    cm = common_mode_shift(B_perp, gamma_hz_per_t, zfs_hz)[LINE_AXIS_8]
    return zfs_hz + first_order + cm


def axis_projections_from_resonances(
    resonance_freqs_8: np.ndarray,
    gamma_hz_per_t: float = GAMMA_E_HZ_PER_T,
) -> np.ndarray:
    """Recover the 4 signed axis projections ``B·n_i`` from 8 canonical-order centers.

    Uses the **splitting** ``(f_{2i} − f_{2i+1}) / 2 = γ_e·(B·n_i)`` — exact and unaffected by the
    common-mode shift, so it works on both first-order and diagonalized centers. This is the
    common-mode-robust input to the BLUE inversion (do **not** use ``f − D`` of single lines).

    Parameters
    ----------
    resonance_freqs_8 : np.ndarray
        Length-8 centers (Hz) in canonical ``(axis, sign)`` row order.

    Returns
    -------
    np.ndarray
        Length-4 signed projections ``B·n_i`` (Tesla).
    """
    f = np.asarray(resonance_freqs_8, dtype=np.float64).reshape(-1)
    if f.shape != (8,):
        raise ValueError(f"expected 8 resonance freqs, got {f.shape}")
    splitting = (f[0::2] - f[1::2]) / 2.0  # rows (2i) − (2i+1)
    return splitting / gamma_hz_per_t


def compute_linewidth(p1_ppm: float, inhomogeneous_fwhm_hz: float = 0.0) -> float:
    """Total FWHM linewidth (Hz) from published dephasing scaling laws.

    Vendored verbatim from ``nv_sensor_sim.physics.parameters.compute_linewidth``: a
    ¹³C natural-abundance T2* floor plus a P1 (nitrogen) spin-bath term, combined in
    quadrature with an optional inhomogeneous contribution (Voigt approximation).

    Parameters
    ----------
    p1_ppm : float
        P1 concentration in ppm.
    inhomogeneous_fwhm_hz : float
        Sample-specific inhomogeneous broadening FWHM in Hz.

    Returns
    -------
    float
        Total linewidth (FWHM) in Hz.
    """
    p1_eff = max(p1_ppm, 1e-6)
    rate_13c = 1.0 / 1.48e-6  # ¹³C natural-abundance floor
    rate_n = p1_eff / 9.9e-6  # P1 nitrogen spin bath (CCE arXiv:2503.05404)
    t2_star_s = 1.0 / (rate_13c + rate_n)
    homogeneous_fwhm = 1.0 / (np.pi * t2_star_s)
    return float(np.sqrt(homogeneous_fwhm**2 + inhomogeneous_fwhm_hz**2))
