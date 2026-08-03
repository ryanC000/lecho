"""Bleed detection for shadow mode (PRD 8.7 / Edge Case 3).

Runs on the RAW signals, before any feature extraction, so leakage cannot hide
behind trimming or normalization.
"""
import numpy as np

from .constants import BLEED_MAX_LAG_S

def detect_bleed(native_samples: np.ndarray, user_samples: np.ndarray, sr: float) -> float:
    """Peak normalized cross-correlation between the raw native and user
    signals over lags 0..BLEED_MAX_LAG_S (native playback can only appear at
    or after the start of a shadow recording). The orchestrator compares the
    returned peak against NCC_BLEED_THRESHOLD.

    Numpy only: cross-correlation via FFT, then
    each lag's correlation normalized by the L2 norms of the two overlapping
    windows, computed from cumulative sums of squares — O(n log n) total.
    The peak is taken on |NCC| so polarity-inverted playback still registers.
    """
    n = np.asarray(native_samples, dtype=np.float64)
    u = np.asarray(user_samples, dtype=np.float64)
    if len(n) == 0 or len(u) == 0:
        return 0.0
    n = n - n.mean()
    u = u - u.mean()

    max_lag = min(int(BLEED_MAX_LAG_S * sr), len(u) - 1)
    # corr[k] = sum_i u[i+k] * n[i]; zero-pad past len(u)+len(n)-1 to avoid
    # circular aliasing, rounded up to a power of two for the FFT.
    size = len(u) + len(n) - 1
    nfft = 1 << (size - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(u, nfft) * np.conj(np.fft.rfft(n, nfft)), nfft)

    lags = np.arange(max_lag + 1)
    overlap = np.minimum(len(n), len(u) - lags)  # samples both windows share at each lag
    cumsq_n = np.concatenate([[0.0], np.cumsum(n * n)])
    cumsq_u = np.concatenate([[0.0], np.cumsum(u * u)])
    norm_n = np.sqrt(cumsq_n[overlap])                       # ||n[:overlap_k]||
    norm_u = np.sqrt(cumsq_u[lags + overlap] - cumsq_u[lags])  # ||u[k:k+overlap_k]||
    denom = norm_n * norm_u
    ncc = np.where(denom > 1e-12, corr[: max_lag + 1] / np.maximum(denom, 1e-12), 0.0)
    return float(np.max(np.abs(ncc)))

