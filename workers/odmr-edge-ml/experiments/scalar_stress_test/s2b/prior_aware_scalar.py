"""Declared-prior scalar baseline; not an exact field-magnitude measurement.

For B~Uniform(lower, upper), isotropic direction, and ideal z=|B cos(theta)|,
p(B|z) is proportional to 1/B on [max(lower,z), upper]. Its absolute-error
optimal estimate is sqrt(upper*max(lower,z)). The noisy fitted/PID projection
is plugged into that ideal formula. This is a baseline, not a calibrated
posterior for a noisy, temperature-shifted spectrum.
"""
from __future__ import annotations

from functools import lru_cache
import importlib.util
from pathlib import Path
import sys
import time
import numpy as np


@lru_cache(maxsize=4)
def _load_sources(repo_string):
    """Load the existing implementations, without modifying the source repository."""
    repo = Path(repo_string).resolve()
    modules = []
    for name, relative in [('_prior_scalar_fit', 'experiments/scalar_fit_baseline.py'),
                           ('_prior_scalar_pid', 'src/odmr_edge_ml/evaluation/pid_proxy.py')]:
        path = repo / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        modules.append(module)
    return modules[0].fit_field_magnitude, modules[1].DerivativeZeroCrossingPID


def magnitude_from_projection(projection_uT, *, lower_uT=20., upper_uT=70.):
    """Return prior median and an explicit raw-projection support-violation mask."""
    if not (np.isfinite([lower_uT, upper_uT]).all() and 0 < lower_uT < upper_uT):
        raise ValueError('prior bounds must be finite with 0 < lower < upper')
    z = np.asarray(projection_uT, dtype=float)
    finite = np.isfinite(z)
    outside = finite & ((z < 0) | (z > upper_uT))
    estimate = np.sqrt(upper_uT * np.maximum(lower_uT, np.clip(z, 0, upper_uT)))
    return np.where(finite, estimate, np.nan), outside


def fit_batch(spectra, frequencies_hz, *, scalar_repo, backend='two_line',
              lower_uT=20., upper_uT=70.):
    """Return raw_projection_uT, magnitude_uT, failed, and diagnostics as arrays.

    backend='two_line' reuses the existing bounded Lorentzian fit. backend='pid'
    reuses the existing derivative-zero-crossing proxy without changing constants.
    No labels, manifest nuisance parameters, or true centers enter this API.
    Failed rows retain NaN; the caller must apply its frozen fallback and count them.
    Out-of-support but finite projections are clipped [0,upper] and counted separately.
    """
    y = np.asarray(spectra, dtype=float)
    f = np.asarray(frequencies_hz, dtype=float)
    if y.ndim != 2 or f.ndim != 1 or y.shape[1] != f.size or f.size < 8:
        raise ValueError('spectra must be (N,F) and frequencies_hz must be (F,), F>=8')
    if not np.isfinite(f).all() or np.any(np.diff(f) <= 0):
        raise ValueError('frequency grid must be finite and increasing')
    if backend not in ('two_line', 'pid'):
        raise ValueError('backend must be two_line or pid')
    magnitude_from_projection([0.], lower_uT=lower_uT, upper_uT=upper_uT)
    fit, pid_class = _load_sources(str(Path(scalar_repo).resolve()))
    pid = pid_class(f)
    projection = np.full(len(y), np.nan)
    failed = np.zeros(len(y), dtype=bool)
    elapsed = np.zeros(len(y))
    diagnostics = []
    for i, row in enumerate(y):
        start = time.perf_counter()
        note = {'row': i, 'backend': backend}
        try:
            if not np.isfinite(row).all():
                raise ValueError('nonfinite spectrum')
            if np.ptp(row) <= 1e-12 * max(1., float(np.max(abs(row)))):
                raise ValueError('flat spectrum has no identifiable resonance')
            if backend == 'two_line':
                value, residual = fit(row, f)
                note['fit_residual'] = float(residual)
            else:
                result = pid.estimate(row)
                value = result.b_mag_uT
                note.update(n_dips=int(result.n_dips), lock_bin=int(result.lock_bin))
            if not np.isfinite(value):
                raise ValueError('nonfinite projection estimate')
            projection[i] = value
        except (ValueError, RuntimeError, FloatingPointError) as error:
            failed[i] = True
            note['failure'] = str(error)
        # Timing includes the per-row posterior transform, validation, and failure path.
        estimate, outside = magnitude_from_projection(projection[i], lower_uT=lower_uT, upper_uT=upper_uT)
        note['out_of_support'] = bool(outside)
        note['magnitude_uT'] = float(estimate)
        elapsed[i] = time.perf_counter()-start
        diagnostics.append(note)
    magnitude, outside = magnitude_from_projection(projection, lower_uT=lower_uT, upper_uT=upper_uT)
    return dict(raw_projection_uT=projection, magnitude_uT=magnitude, failed=failed,
                out_of_support=outside, latency_seconds=elapsed, diagnostics=diagnostics,
                prior=dict(magnitude_distribution='uniform', lower_uT=lower_uT,
                           upper_uT=upper_uT, direction='isotropic', loss='absolute error'),
                interpretation='plug-in declared-prior inference; not an exact magnitude measurement')
