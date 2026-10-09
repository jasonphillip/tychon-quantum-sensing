"""SimOS adapter — primary physics backend for NV-diamond ODMR simulation.

Wraps SimOS v0.2.3 (ETH Zürich Degen group) to provide:
- NV system construction with 7-level photophysics
- Ground/excited state Hamiltonians with Zeeman, ZFS, hyperfine
- CW-ODMR spectrum generation via Hamiltonian EIGENVALUE diagonalization
  plus a phenomenological Lorentzian lineshape (base_contrast=0.03) — this
  is the PRODUCTION spectrum path (``generate_odmr_spectrum``); it does NOT
  solve the Lindblad master equation or a steady-state optical-pumping model
- A time-domain Lindblad collapse-operator path (``get_collapse_operators``)
  that exists but is NOT used by the production spectrum path
- Stochastic-Liouville parameter plumbing for coupled noise injection

References
----------
SimOS: https://www.sciencedirect.com/science/article/pii/S0010465525004205
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, overload

import numpy as np

import simos
from simos.systems import NV

from nv_sensor_sim.physics.hamiltonian import (
    add_transverse_field as _add_transverse_field,
    build_nv_hamiltonian,
)

if TYPE_CHECKING:
    from nv_sensor_sim.config import SimulationConfig


class SimOSAdapter:
    """Adapter wrapping SimOS for NV-diamond ODMR simulation.

    Parameters
    ----------
    config : SimulationConfig
        Simulation configuration with B-field, temperature, frequency range, etc.
    """

    def __init__(self, config: SimulationConfig) -> None:
        self.config = config
        self._nv_system: NV.NVSystem | None = None

    @property
    def nv_system(self) -> NV.NVSystem:
        """Lazy-initialized NV system."""
        if self._nv_system is None:
            self._nv_system = self._build_system()
        return self._nv_system

    def _build_system(self) -> NV.NVSystem:
        """Create the SimOS NVSystem with configured options.

        Returns an NVSystem with the 7-level photophysics model
        (GS triplet + ES triplet + SS singlet) and optional nitrogen hyperfine.
        """
        return NV.NVSystem(
            optics=self.config.use_optics,
            nitrogen=self.config.include_nitrogen,
            method="qutip",
        )

    def build_hamiltonian(
        self,
        B_field: np.ndarray,
        temperature_K: float,
    ) -> tuple:
        """Build the NV Hamiltonian for given B-field and temperature.

        Delegates to :func:`~nv_sensor_sim.physics.hamiltonian.build_nv_hamiltonian`
        for the canonical physics implementation.

        Parameters
        ----------
        B_field : np.ndarray
            Magnetic field 3-vector [Bx, By, Bz] in Tesla.
        temperature_K : float
            Sample temperature in Kelvin.

        Returns
        -------
        tuple
            If optics=True: (H_GS, H_ES) ground and excited state Hamiltonians.
            If optics=False: single Hamiltonian H.
        """
        result = build_nv_hamiltonian(
            self.nv_system, B_field, temperature_K,
            b_perp_T=0.0,
            use_optics=self.config.use_optics,
        )
        # Preserve public API: bare Qobj for optics=False
        if self.config.use_optics:
            return result  # (H_GS, H_ES)
        else:
            return result[0]  # bare H

    def add_transverse_field(self, H, b_perp_T: float):
        """Add transverse B_perp as off-diagonal Zeeman terms.

        Delegates to :func:`~nv_sensor_sim.physics.hamiltonian.add_transverse_field`.

        Parameters
        ----------
        H : Qobj
            Base Hamiltonian to modify.
        b_perp_T : float
            Transverse field magnitude in Tesla.

        Returns
        -------
        Qobj
            Modified Hamiltonian with transverse Zeeman terms.
        """
        return _add_transverse_field(self.nv_system, H, b_perp_T)

    def get_collapse_operators(
        self,
        temperature_K: float = 298.0,
        beta: float = 0.2,
        B_field: np.ndarray | None = None,
    ) -> tuple[list, list]:
        """Get Lindblad collapse operators for laser on/off.

        Parameters
        ----------
        temperature_K : float
            Sample temperature in Kelvin.
        beta : float
            Laser power parameter (0 = off, 1 = saturation).
        B_field : np.ndarray, optional
            Magnetic field 3-vector. Defaults to config B_field.

        Returns
        -------
        tuple[list, list]
            (c_ops_laser_on, c_ops_laser_off) collapse operator lists.
        """
        nv = self.nv_system
        if B_field is None:
            B_field = self.config.B_field_T

        return nv.transition_operators(T=temperature_K, beta=beta, Bvec=B_field)

    @overload
    def generate_odmr_spectrum(
        self,
        B_field: np.ndarray | None = ...,
        freq_range: tuple[float, float] | None = ...,
        n_points: int | None = ...,
        temperature_K: float | None = ...,
        p1_ppm: float | None = ...,
        mw_scale: float = ...,
        center_offset_hz: float = ...,
        *,
        return_line_centers: Literal[True],
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]: ...

    @overload
    def generate_odmr_spectrum(
        self,
        B_field: np.ndarray | None = ...,
        freq_range: tuple[float, float] | None = ...,
        n_points: int | None = ...,
        temperature_K: float | None = ...,
        p1_ppm: float | None = ...,
        mw_scale: float = ...,
        center_offset_hz: float = ...,
        return_line_centers: Literal[False] = ...,
    ) -> tuple[np.ndarray, np.ndarray]: ...

    def generate_odmr_spectrum(
        self,
        B_field: np.ndarray | None = None,
        freq_range: tuple[float, float] | None = None,
        n_points: int | None = None,
        temperature_K: float | None = None,
        p1_ppm: float | None = None,
        mw_scale: float = 1.0,
        center_offset_hz: float = 0.0,
        return_line_centers: bool = False,
    ) -> tuple[np.ndarray, np.ndarray] | tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate a CW ODMR spectrum via eigenvalue analysis + Lorentzian lineshape.

        For CW ODMR, the spectrum is determined by:
        1. Transition frequencies between spin eigenstates (from Hamiltonian eigenvalues)
        2. Transition dipole moments |<j|Sx|ms=0>|^2 (MW coupling strength)
        3. Lorentzian lineshape broadened by T2* dephasing (from P1 concentration)
        4. Power broadening and saturation from MW drive strength

        This eigenvalue approach is physically appropriate for CW ODMR (frequency-domain
        measurement) and is orders of magnitude faster than time-domain Lindblad evolution.

        Parameters
        ----------
        B_field : np.ndarray, optional
            Magnetic field 3-vector in Tesla. Defaults to config value.
        freq_range : tuple[float, float], optional
            MW frequency sweep (start, stop) in Hz. Defaults to config value.
        n_points : int, optional
            Number of frequency points. Defaults to config value.
        temperature_K : float, optional
            Temperature in Kelvin. Defaults to config value.
        p1_ppm : float, optional
            P1 concentration in ppm. Determines intrinsic linewidth via T2*.
            Defaults to config value.
        mw_scale : float
            MW drive amplitude scaling factor (1.0 = nominal). Controls
            power broadening and saturation contrast.
        center_offset_hz : float
            Static common-mode shift (Hz) added to every allowed transition
            frequency, modelling a per-orientation axial strain / E-field
            offset of the zero-field splitting D (both ms0->+/-1 transitions
            move together, so the line center shifts but the split is
            unchanged). Default 0.0 is a no-op (byte-identical output).
        return_line_centers : bool
            When True, also return the allowed transition center frequencies (Hz)
            from the diagonalization, ascending. These are the true dip positions
            (they include second-order transverse-field shifts), used as resonance
            ground truth by the time-series generator. Default False.

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            (frequencies, pl_signal) where frequencies is in Hz and
            pl_signal is the normalized photoluminescence (1 = off-resonance).
            When ``return_line_centers`` is True, a third element ``line_centers``
            (ascending allowed transition frequencies in Hz) is appended.
        """
        from nv_sensor_sim.physics.parameters import compute_linewidth

        if B_field is None:
            B_field = self.config.B_field_T
        if freq_range is None:
            freq_range = self.config.mw_freq_range_Hz
        if n_points is None:
            n_points = self.config.n_freq_points
        if temperature_K is None:
            temperature_K = self.config.temperature_K
        if p1_ppm is None:
            p1_ppm = self.config.p1_concentration_ppm

        frequencies = np.linspace(freq_range[0], freq_range[1], n_points)

        # Use spin-only Hamiltonian for eigenvalue analysis
        # (optical levels don't affect spin transition frequencies)
        spin_nv = NV.NVSystem(
            optics=False,
            nitrogen=self.config.include_nitrogen,
            method="qutip",
        )
        H_result = build_nv_hamiltonian(
            spin_nv, B_field, temperature_K,
            b_perp_T=self.config.b_perp_T,
            use_optics=False,
        )
        H_spin = H_result[0]

        # Diagonalize to get eigenstates and energies
        evals, evecs = H_spin.eigenstates()

        # Find ms=0 state (highest overlap with Sp[0] projector)
        ms0_idx = None
        ms0_overlap = 0.0
        for i, psi in enumerate(evecs):
            overlap = abs(simos.expect(spin_nv.Sp[0], simos.ket2dm(psi)))
            if overlap > ms0_overlap:
                ms0_overlap = overlap
                ms0_idx = i

        # Compute transition frequencies and dipole moments from ms=0
        Sx_data = simos.data(spin_nv.Sx)
        transitions = []
        for j in range(len(evals)):
            if j == ms0_idx:
                continue
            trans_freq_hz = abs(evals[j] - evals[ms0_idx]) / (2 * np.pi)
            # Transition dipole moment in eigenbasis
            evec_j = simos.data(evecs[j]).flatten()
            evec_0 = simos.data(evecs[ms0_idx]).flatten()
            dipole = abs(np.conj(evec_j) @ Sx_data @ evec_0) ** 2
            if dipole > 1e-6:  # Only include allowed transitions
                transitions.append((trans_freq_hz, dipole))

        # Per-orientation static strain / E-field offset: a common-mode ZFS
        # shift moving every allowed transition of this axis by center_offset_hz
        # (shifts the line center, preserves the split). Off (0.0) is a no-op.
        if center_offset_hz:
            transitions = [(tf + center_offset_hz, dip) for tf, dip in transitions]

        # Compute physical linewidth from P1 concentration + inhomogeneous broadening
        inhomog_hz = getattr(self.config, "inhomogeneous_fwhm_hz", 0.0)
        intrinsic_linewidth = compute_linewidth(p1_ppm, inhomogeneous_fwhm_hz=inhomog_hz)

        # Power broadening: Γ_eff = Γ_intrinsic × √(1 + s)
        # where s = s0 × mw_scale² is the saturation parameter
        s0 = getattr(self.config, "base_saturation_s0", 0.1)
        s = s0 * (mw_scale**2)
        linewidth_hz = intrinsic_linewidth * np.sqrt(1.0 + s)
        gamma = linewidth_hz / 2.0  # HWHM for Lorentzian

        # Numerical safeguard against grid aliasing
        import warnings

        freq_step = (frequencies[-1] - frequencies[0]) / max(1, len(frequencies) - 1)
        if freq_step > (linewidth_hz / 3.0):
            warnings.warn(
                f"Grid aliasing risk: Frequency step ({freq_step/1e6:.3f} MHz) is too coarse "
                f"to resolve the {linewidth_hz/1e6:.3f} MHz FWHM lineshape. "
                f"Dip may be under-resolved.",
                UserWarning,
            )

        # Contrast scales with saturation: C ∝ s / (1 + s)
        base_contrast = 0.03
        # Normalize so contrast = base_contrast at nominal mw_scale=1.0
        contrast = base_contrast * (s / (1.0 + s)) / (s0 / (1.0 + s0))

        # Build ODMR spectrum from Lorentzian lineshapes
        # PL = 1 - contrast * sum(Lorentzian dips)
        pl_signal = np.ones(n_points)

        for trans_freq, dipole in transitions:
            # Lorentzian: L(f) = gamma^2 / ((f - f0)^2 + gamma^2)
            lorentz = gamma**2 / ((frequencies - trans_freq) ** 2 + gamma**2)
            # Weight by transition dipole moment and contrast
            pl_signal -= contrast * dipole * lorentz

        if return_line_centers:
            line_centers = np.array(sorted(t[0] for t in transitions))
            return frequencies, pl_signal, line_centers
        return frequencies, pl_signal
