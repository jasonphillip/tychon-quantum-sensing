"""One deterministic fit per channel; all failures retained, never reused."""
import io
import warnings
import numpy as np
from scipy.optimize import OptimizeWarning, curve_fit
from .metadata import read_raw_header

# Ascending selected APD channels, then the author's explicit parameter reorder.
APD_ASCENDING = (1, 3, 4, 6, 7, 11, 13, 15)
PARAMETER_REORDER = (7, 3, 5, 2, 6, 4, 1, 0)
MODEL_CHANNELS = tuple(APD_ASCENDING[i] for i in PARAMETER_REORDER)


def gaussian_pair(x, amplitude, center, width, amplitude2, center2, offset):
    return (-amplitude * np.exp(-(x-center)**2 / (2*width**2))
            - amplitude2 * np.exp(-(x-center2)**2 / (2*width**2)) + offset)


def source_moving_average(values):
    """Preserve author's 51 -> 48 convention, including omitted final window."""
    return np.asarray([np.mean(values[i:i+3]) for i in range(len(values)-3)])


def load_raw(payload):
    read_raw_header(io.BytesIO(payload), len(payload))
    values = np.load(io.BytesIO(payload), allow_pickle=False)
    if not np.isfinite(values).all():
        raise ValueError("nonfinite raw counts")
    return values


def fit_raw(raw, fitter=curve_fit):
    if raw.ndim != 3 or raw.shape[1:] != (16, 51) or not np.isfinite(raw).all():
        raise ValueError("invalid raw shape/values")
    axis = source_moving_average(np.linspace(2.77, 2.97, 51))
    parameters = np.full((8, 6), np.nan)
    deviations = np.full((8, 6), np.nan)
    flags = []
    averaged = np.average(raw, axis=0)
    for out_index, apd_channel in enumerate(MODEL_CHANNELS):
        flag = {"channel": apd_channel, "valid": False, "reason": None}
        try:
            spectrum = source_moving_average(averaged[apd_channel-1])
            low_center = axis[np.argmin(spectrum)]
            depth = np.max(spectrum)-np.min(spectrum)
            initial = [depth, low_center, 0.02, depth*1.2, 2.87*2-low_center, np.average(spectrum)]
            bounds = ([0, 2.79, 0.005, 0, 2.79, 0], [np.inf, 2.95, 0.05, np.inf, 2.95, np.inf])
            with warnings.catch_warnings():
                warnings.simplefilter("error", OptimizeWarning)
                coeff, covariance = fitter(gaussian_pair, axis, spectrum, p0=initial,
                                          bounds=bounds, maxfev=100000, method="trf")
            coeff = np.asarray(coeff)
            covariance = np.asarray(covariance)
            if coeff.shape != (6,) or covariance.shape != (6, 6):
                raise ValueError("fit output shape")
            diagonal = np.diag(covariance)
            if not np.isfinite(coeff).all() or not np.isfinite(covariance).all() or (diagonal < 0).any():
                raise ValueError("invalid fit covariance or parameters")
            std = np.sqrt(diagonal)
            features = np.array([abs(coeff[1]-coeff[4]), std[1], std[4]])
            if (features <= 0).any():
                raise ValueError("nonpositive splitting or center uncertainty")
            parameters[out_index], deviations[out_index] = coeff, std
            flag["valid"] = True
        except (ValueError, RuntimeError, FloatingPointError, OptimizeWarning) as exc:
            flag["reason"] = type(exc).__name__ + ": " + str(exc)
        flags.append(flag)
    features = np.stack((np.abs(parameters[:, 1]-parameters[:, 4]),
                         deviations[:, 1], deviations[:, 4]), axis=1).reshape(24) * 1000.0
    return parameters, deviations, features, flags


def compare_features(actual, expected, tolerances):
    actual, expected = np.asarray(actual), np.asarray(expected)
    if actual.shape != expected.shape or actual.ndim != 2 or actual.shape[1] != 24:
        raise ValueError("paired [N,24] features required")
    absolute = np.tile([tolerances["splitting_atol_MHz"],
                        tolerances["standard_error_atol_MHz"],
                        tolerances["standard_error_atol_MHz"]], 8)
    relative = np.tile([tolerances["splitting_rtol"],
                        tolerances["standard_error_rtol"],
                        tolerances["standard_error_rtol"]], 8)
    valid = np.isfinite(actual) & np.isfinite(expected) & (actual > 0) & (expected > 0)
    error = np.abs(actual-expected)
    limits = absolute + relative*np.abs(expected)
    passed = valid & (error <= limits)
    return {"all_features_match": bool(passed.all()),
            "splittings_match": bool(passed[:, ::3].all()),
            "standard_errors_match": bool(passed.reshape(-1,8,3)[:,:,1:].all()),
            "passed_elements": int(passed.sum()), "total_elements": int(passed.size),
            "failed_elements": np.argwhere(~passed).tolist()}


def extract_payload(payload, fitter=curve_fit):
    """Keep invalid raw samples in outputs instead of silently dropping a row."""
    try:
        return fit_raw(load_raw(payload), fitter)
    except ValueError as exc:
        flags = [{"channel":channel,"valid":False,"reason":"raw_invalid: "+str(exc)}
                 for channel in MODEL_CHANNELS]
        return np.full((8,6),np.nan), np.full((8,6),np.nan), np.full(24,np.nan), flags
