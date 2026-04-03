"""Physics-informed feature extraction from ODMR spectra.

Extracts 5 scalar features that capture the physical drivers of PID
frequency-lock error: dip contrast, lineshape asymmetry, linewidth,
spectral spread (second moment), and lock-point position.

All functions are pure numpy — no torch dependency — so the same logic
can be ported to embedded C for on-device preprocessing.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

FEATURE_NAMES: tuple[str, ...] = (
    "contrast",
    "asymmetry",
    "linewidth",
    "second_moment",
    "lock_position",
)

# Default half-window for asymmetry computation (bins on each side of lock)
_ASYM_HALF_WINDOW: int = 15


def extract_features(
    spectrum: np.ndarray,
    lock_bin: int,
    *,
    asym_half_window: int = _ASYM_HALF_WINDOW,
) -> np.ndarray:
    """Extract 5 physics-informed features from a single ODMR spectrum.

    Parameters
    ----------
    spectrum : np.ndarray
        Shape (n_freq,). Raw PL signal (not normalized).
    lock_bin : int
        PID lock-point bin index.
    asym_half_window : int
        Number of bins on each side of lock_bin for asymmetry.

    Returns
    -------
    np.ndarray
        Shape (5,) feature vector: [contrast, asymmetry, linewidth,
        second_moment, lock_position].
    """
    n_freq = len(spectrum)
    s_max = spectrum.max()
    s_min = spectrum.min()

    # 1. Contrast: fractional dip depth
    contrast = (s_max - s_min) / s_max if s_max != 0 else 0.0

    # 2. Asymmetry: normalized area difference around lock_bin
    left_start = max(0, lock_bin - asym_half_window)
    right_end = min(n_freq, lock_bin + asym_half_window + 1)
    left_area = spectrum[left_start:lock_bin].sum()
    right_area = spectrum[lock_bin + 1:right_end].sum()
    denom = left_area + right_area
    asymmetry = (left_area - right_area) / denom if denom != 0 else 0.0

    # 3. Linewidth: count of bins below half-maximum depth (FWHM proxy)
    half_level = (s_max + s_min) / 2.0
    linewidth = float(np.sum(spectrum < half_level))

    # 4. Second moment: variance of dip weight around lock_bin
    bins = np.arange(n_freq, dtype=np.float64)
    dip_weight = s_max - spectrum
    w_sum = dip_weight.sum()
    if w_sum > 0:
        second_moment = float(
            np.sum((bins - lock_bin) ** 2 * dip_weight) / w_sum
        )
    else:
        second_moment = 0.0

    # 5. Lock position: normalized bin index
    lock_position = lock_bin / (n_freq - 1) if n_freq > 1 else 0.5

    return np.array(
        [contrast, asymmetry, linewidth, second_moment, lock_position],
        dtype=np.float64,
    )


def extract_features_batch(
    spectra: np.ndarray,
    lock_bins: np.ndarray,
    *,
    asym_half_window: int = _ASYM_HALF_WINDOW,
) -> np.ndarray:
    """Vectorized feature extraction for a batch of spectra.

    Parameters
    ----------
    spectra : np.ndarray
        Shape (N, n_freq). Raw PL signals.
    lock_bins : np.ndarray
        Shape (N,). PID lock-point bin indices.
    asym_half_window : int
        Number of bins on each side for asymmetry.

    Returns
    -------
    np.ndarray
        Shape (N, 5) feature matrix.
    """
    N, n_freq = spectra.shape
    features = np.zeros((N, 5), dtype=np.float64)

    s_max = spectra.max(axis=1)  # (N,)
    s_min = spectra.min(axis=1)  # (N,)

    # 1. Contrast
    safe_max = np.where(s_max == 0, 1.0, s_max)
    features[:, 0] = (s_max - s_min) / safe_max

    # 2. Asymmetry — loop over unique lock_bin values (typically 2-3)
    for lb in np.unique(lock_bins):
        mask = lock_bins == lb
        left_start = max(0, int(lb) - asym_half_window)
        right_end = min(n_freq, int(lb) + asym_half_window + 1)
        left_area = spectra[mask, left_start:int(lb)].sum(axis=1)
        right_area = spectra[mask, int(lb) + 1:right_end].sum(axis=1)
        denom = left_area + right_area
        safe_denom = np.where(denom == 0, 1.0, denom)
        features[mask, 1] = (left_area - right_area) / safe_denom

    # 3. Linewidth
    half_level = ((s_max + s_min) / 2.0)[:, None]  # (N, 1)
    features[:, 2] = (spectra < half_level).sum(axis=1).astype(np.float64)

    # 4. Second moment
    bins = np.arange(n_freq, dtype=np.float64)[None, :]  # (1, n_freq)
    dip_weight = s_max[:, None] - spectra  # (N, n_freq)
    w_sum = dip_weight.sum(axis=1)  # (N,)
    safe_w_sum = np.where(w_sum == 0, 1.0, w_sum)
    dist_sq = (bins - lock_bins[:, None].astype(np.float64)) ** 2  # (N, n_freq)
    features[:, 3] = (dist_sq * dip_weight).sum(axis=1) / safe_w_sum

    # 5. Lock position
    features[:, 4] = lock_bins.astype(np.float64) / (n_freq - 1)

    return features


class FeatureNormalizer:
    """Z-score normalizer for spectral features.

    Fit on training data, apply to val/test/sweep. Stores mean and std
    for deployment preprocessing.
    """

    def __init__(self) -> None:
        self.mean_: np.ndarray | None = None
        self.std_: np.ndarray | None = None

    def fit(self, features: np.ndarray) -> FeatureNormalizer:
        """Compute per-feature mean and std from training data.

        Parameters
        ----------
        features : np.ndarray
            Shape (N, 5) training features.
        """
        self.mean_ = features.mean(axis=0)
        std = features.std(axis=0)
        self.std_ = np.where(std == 0, 1.0, std)
        return self

    def transform(self, features: np.ndarray) -> np.ndarray:
        """Z-score normalize features.

        Parameters
        ----------
        features : np.ndarray
            Shape (N, 5) or (5,).

        Returns
        -------
        np.ndarray
            Normalized features, same shape.
        """
        assert self.mean_ is not None, "Must call fit() before transform()"
        return (features - self.mean_) / self.std_

    def fit_transform(self, features: np.ndarray) -> np.ndarray:
        """Fit and transform in one call."""
        return self.fit(features).transform(features)

    def save(self, path: Path) -> None:
        """Save normalizer stats for deployment."""
        assert self.mean_ is not None and self.std_ is not None, (
            "Must call fit() before save()"
        )
        np.savez(path, mean=self.mean_, std=self.std_)

    @classmethod
    def load(cls, path: Path) -> FeatureNormalizer:
        """Load normalizer from saved stats."""
        norm = cls()
        d = np.load(path)
        norm.mean_ = d["mean"]
        norm.std_ = d["std"]
        return norm
