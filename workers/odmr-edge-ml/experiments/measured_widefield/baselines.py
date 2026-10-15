"""Strong fixed classical spectrum predictors with explicit operational fallbacks."""
import time
import numpy as np
from scipy.optimize import least_squares
from scipy.signal import find_peaks, savgol_filter

METHODS = ("raw", "training_mean", "savgol_5", "savgol_11", "savgol_21",
           "ridge_0.001", "ridge_0.01", "ridge_0.1",
           "pca_wiener_4", "pca_wiener_8", "pca_wiener_16", "robust_lorentzian")


def curve_jacobian(parameters, frequency):
    """Shared FWHM Lorentzians; [offset,slope,FWHM,centers...,contrasts...]."""
    count = (len(parameters) - 3) // 2
    center = parameters[3:3 + count]
    contrast = parameters[3 + count:]
    width = parameters[2]
    delta = frequency[:, None] - center
    denominator = 4 * delta ** 2 + width ** 2
    line = width ** 2 / denominator
    x = (frequency - frequency.mean()) / np.ptp(frequency)
    prediction = parameters[0] + parameters[1] * x - line @ contrast
    jacobian = np.column_stack((np.ones(len(frequency)), x,
        -np.sum(contrast * 8 * width * delta ** 2 / denominator ** 2, axis=1),
        -contrast * 8 * width ** 2 * delta / denominator ** 2, -line))
    return prediction, jacobian


def robust_fit(values, frequency):
    smooth = savgol_filter(values, 11, 3)
    noise = max(float(np.median(np.abs(np.diff(values))) / 0.9538725524), 1e-4)
    peaks, properties = find_peaks(-smooth, distance=3, prominence=2 * noise)
    ranked = list(peaks[np.argsort(-properties["prominences"])])
    # Deterministic fill supplies missing starts, without any held-repeat information.
    for index in np.argsort(smooth):
        if all(abs(int(index) - int(j)) >= 3 for j in ranked):
            ranked.append(int(index))
        if len(ranked) >= 8:
            break
    for index in np.linspace(10, len(values) - 11, 8).astype(int):
        if int(index) not in ranked:
            ranked.append(int(index))
    x = (frequency - frequency.mean()) / np.ptp(frequency)
    design = np.column_stack((np.ones(len(values)), x))
    background = design @ np.linalg.lstsq(design, values, rcond=None)[0]
    error = background - values
    background_bic = len(values) * np.log(max(float(error @ error / len(values)), 1e-16)) + 2 * np.log(len(values))
    best = (float(background_bic), background, False, 0)
    successful_fits = 0
    for count in (1, 2, 4, 8):
        centers = np.sort(frequency[np.asarray(ranked[:count], dtype=int)])
        if len(centers) != count:
            continue
        for width in (8.0, 16.0):
            initial = np.r_[np.median(values), 0.0, width, centers, np.full(count, 0.01 / count)]
            lower = np.r_[0.5, -0.5, 1.5, np.full(count, frequency[0]), np.zeros(count)]
            upper = np.r_[1.5, 0.5, 60.0, np.full(count, frequency[-1]), np.full(count, 0.3)]
            try:
                fitted = least_squares(lambda p: (curve_jacobian(p, frequency)[0] - values) / noise,
                    np.clip(initial, lower + 1e-9, upper - 1e-9),
                    jac=lambda p: curve_jacobian(p, frequency)[1] / noise,
                    bounds=(lower, upper), loss="soft_l1", f_scale=1.0, max_nfev=80,
                    ftol=1e-7, xtol=1e-7, gtol=1e-7)
                prediction, jacobian = curve_jacobian(fitted.x, frequency)
                if not fitted.success or not np.isfinite(prediction).all():
                    continue
                successful_fits += 1
                residual = prediction - values
                # BIC is a fixed input-only complexity heuristic, not a noise likelihood claim.
                bic = len(values) * np.log(max(float(residual @ residual / len(values)), 1e-16)) + len(fitted.x) * np.log(len(values))
                singular = np.linalg.svd(jacobian, compute_uv=False)
                reliable = bool(np.all(fitted.active_mask == 0) and singular[-1] > singular[0] * 1e-8
                                and np.max(fitted.x[3 + count:]) > 3 * noise)
                if best is None or bic < best[0]:
                    best = (float(bic), prediction, reliable, count)
            except (ValueError, FloatingPointError, np.linalg.LinAlgError):
                continue
    if best is None:
        return smooth, True, False, 0
    return best[1], bool(len(peaks) and successful_fits == 0), best[2], best[3]


def fit_linear_models(inputs, targets, target_repeat_difference):
    mean_x, mean_y = inputs.mean(axis=0), targets.mean(axis=0)
    x, y = inputs - mean_x, targets - mean_y
    covariance = x.T @ x
    _, singular, vectors = np.linalg.svd(y, full_matrices=False)
    result = {"mean_x": mean_x, "mean_y": mean_y}
    for multiplier in (0.001, 0.01, 0.1):
        ridge = max(multiplier * float(np.trace(covariance)) / inputs.shape[1], 1e-8)
        result["ridge_" + str(multiplier)] = np.linalg.solve(
            covariance + ridge * np.eye(inputs.shape[1]), x.T @ y)
    for rank in (4, 8, 16):
        components = vectors[:rank]
        variance = singular[:rank] ** 2 / max(len(y) - 1, 1)
        noise = np.mean((target_repeat_difference @ components.T) ** 2, axis=0) / 2
        result["components_" + str(rank)] = components
        result["shrinkage_" + str(rank)] = np.maximum(variance - noise / 2, 0) / np.maximum(variance + noise / 2, 1e-12)
    # A fixed training-only shape diagnostic; not a mask of independently labelled resonances.
    edge_energy = np.mean(np.diff(targets, axis=1) ** 2, axis=0)
    result["shape_edges"] = np.sort(np.lexsort((np.arange(199), -edge_energy))[:50])
    result["shape_edge_training_energy"] = edge_energy
    return result


def predict(method, inputs, frequency, model):
    predictions, failures, reliability, seconds = [], [], [], []
    for values in inputs:
        start = time.perf_counter()
        failed, reliable = False, False
        if method == "raw":
            prediction = values.copy()
        elif method == "training_mean":
            prediction = model["mean_y"].copy()
        elif method in ("savgol_5", "savgol_11", "savgol_21"):
            prediction = savgol_filter(values, int(method.rsplit("_", 1)[1]), 3)
        elif method in ("ridge_0.001", "ridge_0.01", "ridge_0.1"):
            prediction = model["mean_y"] + (values - model["mean_x"]) @ model[method]
        elif method in ("pca_wiener_4", "pca_wiener_8", "pca_wiener_16"):
            rank = method.rsplit("_", 1)[1]
            components = model["components_" + rank]
            prediction = model["mean_y"] + (((values - model["mean_y"]) @ components.T) * model["shrinkage_" + rank]) @ components
        elif method == "robust_lorentzian":
            prediction, failed, reliable, _ = robust_fit(values, frequency)
        else:
            raise ValueError("Unregistered method")
        if not np.isfinite(prediction).all():
            prediction, failed, reliable = values.copy(), True, False
        seconds.append(time.perf_counter() - start)
        predictions.append(prediction)
        failures.append(failed)
        reliability.append(reliable)
    return np.asarray(predictions), np.asarray(failures), np.asarray(reliability), np.asarray(seconds)
