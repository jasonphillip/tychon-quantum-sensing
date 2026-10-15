"""Classical primitives for a future approved replay; never use future samples."""
from __future__ import annotations
import math
import numpy as np
from scipy.signal import butter, iirnotch, sosfilt, tf2sos

class CausalFilter:
    """Stateful SOS filter. Start-up transient is flagged, not deleted from accounting."""
    def __init__(self, sample_rate_hz, *, highpass_hz=None, lowpass_hz=None, notch_hz=(), quality=30):
        if not math.isfinite(sample_rate_hz) or sample_rate_hz <= 0:
            raise ValueError("Positive sample rate required.")
        if quality <= 0:
            raise ValueError("Positive notch quality required.")
        sections = []
        if highpass_hz is not None and lowpass_hz is not None:
            if not 0 < highpass_hz < lowpass_hz < sample_rate_hz / 2:
                raise ValueError("Invalid filter band.")
            sections.extend(butter(2, [highpass_hz, lowpass_hz], btype="bandpass", fs=sample_rate_hz, output="sos"))
        elif highpass_hz is not None:
            sections.extend(butter(2, highpass_hz, btype="highpass", fs=sample_rate_hz, output="sos"))
        elif lowpass_hz is not None:
            sections.extend(butter(2, lowpass_hz, btype="lowpass", fs=sample_rate_hz, output="sos"))
        for frequency in notch_hz:
            if not 0 < frequency < sample_rate_hz / 2:
                raise ValueError("Notch must lie below Nyquist.")
            b, a = iirnotch(frequency, quality, fs=sample_rate_hz)
            sections.extend(tf2sos(b, a))
        self.sos = np.asarray(sections, dtype=float).reshape(-1, 6)
        self.state = np.zeros((len(sections), 2), dtype=float)

    def process(self, samples):
        x = np.asarray(samples, dtype=float)
        if x.ndim != 1 or not np.isfinite(x).all():
            raise ValueError("Finite one-dimensional samples required.")
        if not len(self.sos):
            return x.copy()
        out, self.state = sosfilt(self.sos, x, zi=self.state)
        return out

class CausalNLMS:
    """Noise-reference adaptive cancellation with previous weights predicting current output."""
    def __init__(self, taps=16, step=0.05, epsilon=1e-12):
        if not isinstance(taps, int) or taps < 1 or not 0 < step < 2 or epsilon <= 0:
            raise ValueError("Invalid NLMS configuration.")
        self.weights = np.zeros(taps)
        self.history = np.zeros(taps)
        self.step, self.epsilon = step, epsilon

    def process(self, primary, reference, *, adapt=True):
        x, r = np.asarray(primary, float), np.asarray(reference, float)
        if x.ndim != 1 or x.shape != r.shape or not np.isfinite(x).all() or not np.isfinite(r).all():
            raise ValueError("Finite aligned channels required.")
        output = np.empty_like(x)
        for i in range(len(x)):
            self.history[1:] = self.history[:-1]
            self.history[0] = r[i]
            output[i] = x[i] - np.dot(self.weights, self.history)
            if adapt:
                self.weights += self.step * output[i] * self.history / (self.epsilon + np.dot(self.history, self.history))
        return output

def frozen_reference_subtraction(primary, reference, gain):
    """Gain must be learned exclusively on development data, then frozen."""
    if not math.isfinite(gain):
        raise ValueError("Finite frozen gain required.")
    x, r = np.asarray(primary, float), np.asarray(reference, float)
    if x.shape != r.shape or x.ndim != 1 or not np.isfinite(x).all() or not np.isfinite(r).all():
        raise ValueError("Finite aligned channels required.")
    return x - gain * r

def aggregate_completed_beats(beats, *, method="mean", weights=None):
    """Post-beat aggregate. Latency includes completion of every supplied beat window."""
    x = np.asarray(beats, dtype=float)
    if x.ndim != 2 or len(x) == 0 or not np.isfinite(x).all():
        raise ValueError("Finite complete non-overlapping beats required.")
    if method == "mean":
        return np.mean(x, axis=0)
    if method == "median":
        return np.median(x, axis=0)
    if method == "trimmed_mean":
        trim = len(x) // 10
        ordered = np.sort(x, axis=0)
        return np.mean(ordered[trim:len(x)-trim], axis=0)
    if method == "quality_weighted":
        w = np.asarray(weights, dtype=float)
        if w.shape != (len(x),) or not np.isfinite(w).all() or np.any(w < 0) or np.sum(w) <= 0:
            raise ValueError("Nonnegative external per-beat quality weights required.")
        return np.average(x, axis=0, weights=w)
    raise ValueError("Unknown aggregation method.")
