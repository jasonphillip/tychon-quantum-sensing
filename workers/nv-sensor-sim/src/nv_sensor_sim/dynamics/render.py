"""Per-frame and per-sequence ODMR rendering for the time-series generator.

Reuses the static multi-axis lineshape path (each NV axis rendered separately by
SimOS diagonalization, then ensemble-averaged) and, in the same per-axis loop,
captures the diagonalized line centers so the resonance labels sit exactly on the
rendered dips. The averaged spectrum is identical to
``lineshape.generate_multi_axis_spectrum`` for the same field.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from nv_sensor_sim.dynamics.resonances import (
    associate_axis_centers,
    axis_transition_labels,
    collision_labels,
)
from nv_sensor_sim.physics.cross_relaxation import add_cross_relaxation
from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT, project_field_onto_axes
from nv_sensor_sim.physics.parameters import compute_linewidth

if TYPE_CHECKING:
    from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter


def render_multi_axis_frame(
    adapter: SimOSAdapter,
    B_lab_T: np.ndarray,
    p1_ppm: float | None = None,
    mw_scale: float = 1.0,
    extra_b_perp_T: float = 0.0,
    nv_axes: np.ndarray = NV_AXES_UNIT,
    freq_range: tuple[float, float] | None = None,
    n_points: int | None = None,
    axis_mw_scales: np.ndarray | None = None,
    axis_offsets_hz: np.ndarray | None = None,
    nv_density_ppm: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Render one multi-axis ODMR frame and its associated line centers.

    Mirrors ``lineshape.generate_multi_axis_spectrum`` (same per-axis effective
    field ``(0, 0, |B . n_i|)`` + transverse projection, equal-weight average) but
    also returns the per-line resonance centers with axis/transition identity.

    Parameters
    ----------
    adapter : SimOSAdapter
        Adapter whose ``generate_odmr_spectrum`` is invoked per axis.
    B_lab_T : np.ndarray
        Lab-frame field 3-vector (bias + sweep) in Tesla.
    p1_ppm : float, optional
        P1 concentration. Defaults to adapter config value.
    mw_scale : float
        MW Rabi-amplitude scaling applied uniformly across axes.
    extra_b_perp_T : float
        Additional stray transverse field beyond the geometric per-axis projection.
    nv_axes : np.ndarray
        Unit vectors of the NV axes, shape (n_axes, 3). Defaults to NV_AXES_UNIT.
    freq_range : tuple[float, float], optional
        MW sweep range (start, stop) in Hz. Defaults to adapter config value.
    n_points : int, optional
        Number of frequency points. Defaults to adapter config value.
    axis_mw_scales : np.ndarray, optional
        Per-axis MW Rabi-amplitude factors (length ``n_axes``), multiplied onto
        ``mw_scale``. Models the MW polarization projecting differently onto
        each NV axis, so per-axis contrast (via saturation) and rendered
        broadening differ. None (default) drives all axes uniformly.
    axis_offsets_hz : np.ndarray, optional
        Per-axis static strain / E-field ZFS offsets (length ``n_axes``, Hz):
        a common-mode shift applied to both transitions of each axis, so the
        per-axis line center moves by ``axis_offsets_hz[i]`` while the split is
        preserved. Flows into ``resonance_freqs`` automatically. None (default)
        is a no-op (byte-identical output). See docs/dataset-contract.md.
    nv_density_ppm : float
        NV(-) concentration in ppm for the NV-NV cross-relaxation PL feature: at
        inter-orientation degeneracy (``|B.n_i| = |B.n_j|``) an extra Lorentzian
        PL dip is subtracted from the averaged spectrum (density-conditional,
        Dhungel/Espinos calibration). Modifies the spectrum only, never
        ``resonance_freqs``. 0.0 (default) is a no-op (byte-identical output).
        See ``physics.cross_relaxation`` and docs/dataset-contract.md.

    Returns
    -------
    tuple[np.ndarray, np.ndarray, np.ndarray]
        ``(frequencies, averaged_spectrum, resonance_freqs)``. ``resonance_freqs``
        has length ``L = 2 * n_axes`` in geometry-matrix order (Hz).
    """
    B_par, B_perp_mag = project_field_onto_axes(B_lab_T, nv_axes=nv_axes)
    if axis_mw_scales is not None:
        axis_mw_scales = np.asarray(axis_mw_scales, dtype=float).reshape(len(nv_axes))
    if axis_offsets_hz is not None:
        axis_offsets_hz = np.asarray(axis_offsets_hz, dtype=float).reshape(len(nv_axes))

    spectra: list[np.ndarray] = []
    per_axis_centers: list[np.ndarray] = []
    frequencies: np.ndarray | None = None
    original_b_perp = adapter.config.b_perp_T

    try:
        for i in range(len(nv_axes)):
            B_eff = np.array([0.0, 0.0, abs(float(B_par[i]))])
            adapter.config.b_perp_T = float(B_perp_mag[i]) + extra_b_perp_T
            scale_i = mw_scale if axis_mw_scales is None else mw_scale * float(axis_mw_scales[i])
            offset_i = 0.0 if axis_offsets_hz is None else float(axis_offsets_hz[i])
            freqs_i, signal_i, centers_i = adapter.generate_odmr_spectrum(
                B_field=B_eff,
                freq_range=freq_range,
                n_points=n_points,
                p1_ppm=p1_ppm,
                mw_scale=scale_i,
                center_offset_hz=offset_i,
                return_line_centers=True,
            )
            if frequencies is None:
                frequencies = freqs_i
            spectra.append(signal_i)
            per_axis_centers.append(centers_i)
    finally:
        adapter.config.b_perp_T = original_b_perp

    assert frequencies is not None  # guaranteed by len(nv_axes) >= 1
    averaged = np.mean(np.stack(spectra, axis=0), axis=0)
    resonance_freqs = associate_axis_centers(per_axis_centers, B_par)

    # NV-NV cross-relaxation PL feature (density-conditional merge marker). Uses
    # the full-field per-axis projections and the L=8 centers; adds dips to the
    # averaged spectrum only, never to resonance_freqs. Off (0.0) is a no-op.
    if nv_density_ppm > 0.0:
        p1_for_gamma = p1_ppm if p1_ppm is not None else adapter.config.p1_concentration_ppm
        gamma_fwhm_hz = compute_linewidth(p1_for_gamma)
        averaged = add_cross_relaxation(
            frequencies,
            averaged,
            resonance_freqs,
            B_par,
            nv_density_ppm,
            gamma_fwhm_hz,
            nv_axes=nv_axes,
        )

    return frequencies, averaged, resonance_freqs


def render_sequence(
    adapter: SimOSAdapter,
    B_traj_T3: np.ndarray,
    *,
    p1_ppm: float,
    gamma_fwhm_hz: float,
    k: float,
    extra_b_perp_T: float = 0.0,
    nv_axes: np.ndarray = NV_AXES_UNIT,
    freq_range: tuple[float, float] | None = None,
    n_points: int | None = None,
    axis_mw_scales: np.ndarray | None = None,
    axis_offsets_hz: np.ndarray | None = None,
    nv_density_ppm: float = 0.0,
) -> dict[str, np.ndarray]:
    """Render a full time-series for one field trajectory.

    Parameters
    ----------
    adapter : SimOSAdapter
        Adapter to render through (config drives freq range / n_points if unset).
    B_traj_T3 : np.ndarray
        Field trajectory of shape (T, 3) in Tesla.
    p1_ppm : float
        P1 concentration in ppm (fixed across the sequence).
    gamma_fwhm_hz : float
        Linewidth Gamma (FWHM) in Hz for collision labelling.
    k : float
        Collision threshold in linewidths.
    extra_b_perp_T : float
        Additional stray transverse field. Default 0.0.
    nv_axes : np.ndarray
        Unit vectors of the NV axes. Defaults to NV_AXES_UNIT.
    freq_range : tuple[float, float], optional
        MW sweep range (start, stop) in Hz. Defaults to adapter config value.
    n_points : int, optional
        Number of frequency points. Defaults to adapter config value.
    axis_mw_scales : np.ndarray, optional
        Per-axis MW Rabi-amplitude factors: shape (n_axes,) applied to every
        frame, or (T, n_axes) per frame (e.g. slow contrast drift). None
        (default) drives all axes uniformly.
    axis_offsets_hz : np.ndarray, optional
        Per-axis static strain / E-field ZFS offsets (length n_axes, Hz),
        applied to every frame. None (default) is a no-op (byte-identical).
    nv_density_ppm : float
        NV concentration in ppm for the NV-NV cross-relaxation PL feature,
        applied per frame. 0.0 (default) is a no-op (byte-identical).

    Returns
    -------
    dict[str, np.ndarray]
        Keys: ``spectra`` (T, F) f32, ``frequencies`` (F,) f32, ``B_true`` (T, 3)
        f32, ``resonance_freqs`` (T, L) f32, ``line_axis`` (T, L) i8,
        ``line_transition`` (T, L) i8, ``collision_mask`` (T,) bool,
        ``line_collision`` (T, L) bool.
    """
    B_traj = np.asarray(B_traj_T3, dtype=float).reshape(-1, 3)
    n_steps = B_traj.shape[0]
    line_axis_1d, line_transition_1d = axis_transition_labels(nv_axes)
    n_lines = line_axis_1d.shape[0]

    scales_per_frame: np.ndarray | None = None
    if axis_mw_scales is not None:
        scales = np.asarray(axis_mw_scales, dtype=float)
        if scales.ndim == 1:
            scales_per_frame = np.broadcast_to(scales, (n_steps, len(nv_axes)))
        elif scales.shape == (n_steps, len(nv_axes)):
            scales_per_frame = scales
        else:
            raise ValueError(
                f"axis_mw_scales must have shape ({len(nv_axes)},) or "
                f"({n_steps}, {len(nv_axes)}), got {scales.shape}"
            )

    spectra: np.ndarray | None = None
    frequencies: np.ndarray | None = None
    resonance = np.empty((n_steps, n_lines), dtype=float)

    for t in range(n_steps):
        freqs, spec, centers = render_multi_axis_frame(
            adapter,
            B_traj[t],
            p1_ppm=p1_ppm,
            extra_b_perp_T=extra_b_perp_T,
            nv_axes=nv_axes,
            freq_range=freq_range,
            n_points=n_points,
            axis_mw_scales=None if scales_per_frame is None else scales_per_frame[t],
            axis_offsets_hz=axis_offsets_hz,
            nv_density_ppm=nv_density_ppm,
        )
        if spectra is None:
            frequencies = freqs
            spectra = np.empty((n_steps, freqs.shape[0]), dtype=float)
        spectra[t] = spec
        resonance[t] = centers

    assert spectra is not None and frequencies is not None  # n_steps >= 1
    collision_mask, line_collision = collision_labels(resonance, gamma_fwhm_hz, k)

    return {
        "spectra": spectra.astype(np.float32),
        "frequencies": frequencies.astype(np.float32),
        "B_true": B_traj.astype(np.float32),
        "resonance_freqs": resonance.astype(np.float32),
        "line_axis": np.broadcast_to(line_axis_1d, (n_steps, n_lines)).astype(np.int8),
        "line_transition": np.broadcast_to(line_transition_1d, (n_steps, n_lines)).astype(np.int8),
        "collision_mask": collision_mask,
        "line_collision": line_collision,
    }
