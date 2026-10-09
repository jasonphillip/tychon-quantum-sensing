#!/usr/bin/env python3
"""Benchmark per-spectrum generation time for both generation paths.

Measures:
1. corrupt_spectrum() path (current pipeline) — 10 spectra with varying params
2. CoupledNoiseInjector path (OU stochastic) — single spectrum

Reports mean/min/max and projects time for 50,000 spectra.
"""

from __future__ import annotations

import time

import numpy as np

# --------------------------------------------------------------------------- #
# Path 1: corrupt_spectrum (current pipeline path)
# --------------------------------------------------------------------------- #


def benchmark_corrupt_spectrum(n_spectra: int = 10) -> list[float]:
    """Time n_spectra calls to corrupt_spectrum with varying parameters."""
    from tychon_nv_sim.adapters.simos_adapter import SimOSAdapter
    from tychon_nv_sim.config import SimulationConfig
    from tychon_nv_sim.physics.lineshape import corrupt_spectrum

    rng = np.random.default_rng(42)

    # Match production sweep ranges
    p1_values = rng.uniform(1.0, 300.0, n_spectra)
    temp_values = rng.uniform(280.0, 320.0, n_spectra)
    b1_grad_values = rng.uniform(0.05, 0.30, n_spectra)
    b_perp_values = rng.uniform(0.0, 50e-6, n_spectra)
    bz_values = rng.uniform(0.005, 0.015, n_spectra)

    timings = []

    for i in range(n_spectra):
        config = SimulationConfig(
            B_field_T=np.array([0.0, 0.0, bz_values[i]]),
            temperature_K=temp_values[i],
            n_freq_points=2000,  # production resolution
            mw_freq_range_Hz=(2.82e9, 2.92e9),
            p1_concentration_ppm=p1_values[i],
        )
        adapter = SimOSAdapter(config)

        t0 = time.perf_counter()
        corrupt_spectrum(
            adapter,
            config,
            b1_gradient_frac=b1_grad_values[i],
            b_perp_T=b_perp_values[i],
            p1_ppm=p1_values[i],
        )
        elapsed = time.perf_counter() - t0
        timings.append(elapsed)

        print(f"  spectrum {i + 1}/{n_spectra}: {elapsed:.4f}s "
              f"(P1={p1_values[i]:.0f}ppm, T={temp_values[i]:.0f}K, "
              f"Bz={bz_values[i]*1e3:.1f}mT)")

    return timings


# --------------------------------------------------------------------------- #
# Path 2: CoupledNoiseInjector (OU stochastic path)
# --------------------------------------------------------------------------- #


def benchmark_ou_injector() -> float | None:
    """Time a single CoupledNoiseInjector.inject_coupled_noise() call."""
    import simos
    from simos.systems import NV

    from tychon_nv_sim.config import NoiseConfig
    from tychon_nv_sim.physics.noise_injection import CoupledNoiseInjector
    from tychon_nv_sim.physics.parameters import OUProcessParams

    # Spin-only system for speed (matches integration test pattern)
    nv = NV.NVSystem(optics=False, nitrogen=False, method="qutip")
    H_spin = nv.field_hamiltonian(Bvec=np.array([0, 0, 0.01]))
    evals, evecs = H_spin.eigenstates()
    rho0 = simos.ket2dm(evecs[0])

    noise_config = NoiseConfig(enable_thermal_noise=True, enable_mw_noise=True)
    ou_params = OUProcessParams(mu_T=300.0, sigma_T=0.5, theta_T=0.1)
    injector = CoupledNoiseInjector(noise_config, ou_params)

    def H_func(temperature=300.0, b1_amplitude=1.0, **kwargs):
        delta_D_rad = 2 * np.pi * (-74.2e3) * (temperature - 300.0)
        return H_spin + delta_D_rad * (nv.Sz * nv.Sz)

    try:
        t0 = time.perf_counter()
        result = injector.inject_coupled_noise(
            H_func=H_func, nv_system=nv, rho0=rho0, t=1e-6, seed=42,
        )
        elapsed = time.perf_counter() - t0
        return elapsed
    except (NotImplementedError, AttributeError) as e:
        print(f"  OU path not available: {e}")
        return None
    except Exception as e:
        print(f"  OU path failed: {e}")
        return None


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    N = 10

    print("=" * 65)
    print("TYCHON NV-SIM — SPECTRUM GENERATION BENCHMARK")
    print("=" * 65)

    # --- Path 1: corrupt_spectrum ---
    print(f"\n[1] corrupt_spectrum() — {N} spectra, 2000 freq points each")
    print("-" * 65)
    timings = benchmark_corrupt_spectrum(n_spectra=N)

    mean_t = np.mean(timings)
    min_t = np.min(timings)
    max_t = np.max(timings)
    std_t = np.std(timings)

    print(f"\n  Results ({N} spectra):")
    print(f"    Mean:  {mean_t:.4f}s")
    print(f"    Min:   {min_t:.4f}s")
    print(f"    Max:   {max_t:.4f}s")
    print(f"    Stdev: {std_t:.4f}s")

    # Projection
    n_target = 50_000
    proj_sec = mean_t * n_target
    proj_min = proj_sec / 60
    proj_hr = proj_min / 60

    print(f"\n  Projection for {n_target:,} spectra:")
    print(f"    {proj_sec:,.0f}s = {proj_min:,.1f}min = {proj_hr:,.2f}hr")
    print(f"    Rate: {1/mean_t:.1f} spectra/s")

    # --- Path 2: OU noise injector ---
    print(f"\n[2] CoupledNoiseInjector — single stochastic evolution")
    print("-" * 65)
    ou_time = benchmark_ou_injector()
    if ou_time is not None:
        print(f"  OU single-shot: {ou_time:.4f}s")
        ratio = ou_time / mean_t if mean_t > 0 else float("inf")
        print(f"  Ratio vs corrupt_spectrum: {ratio:.1f}x")
        ou_proj = ou_time * n_target
        print(f"  Projection for {n_target:,} spectra: "
              f"{ou_proj:,.0f}s = {ou_proj/3600:,.2f}hr")
    else:
        print("  OU path could not be timed (see error above)")

    print("\n" + "=" * 65)
    print("DONE")
    print("=" * 65)
