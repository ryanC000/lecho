"""DTW alignment of a user take onto the native timeline (worker_plan.md §4 step 6).

Hand-rolled rather than dtw-python: a few hundred to ~1500 frames per side is
trivial for an O(n*m) numpy matrix, and hand-rolling avoids another native/C
extension dependency.
"""
from dataclasses import dataclass

import numpy as np

from .constants import (
    DTW_DIAG_PULL,
    DTW_ENERGY_LAMBDA,
    DTW_STEP_PENALTY,
    FRAME_HOP_S,
    MAX_LENGTH_RATIO,
    SAKOE_CHIBA_BAND_FRAC,
    SLOPE_TAG_WINDOW_S,
    SLOPE_WINDOW_S,
)
from .errors import LengthRatioError
from .features import ProsodyFeatures

@dataclass
class Aligned:
    """Native clip's own features plus the user's features re-expressed on
    the native timeline by averaging whichever user frames the DTW path
    matched to each native frame. Everything downstream (scoring, segments,
    the archive) reads off this one native-indexed timeline.

    dsp-2 additions: `user` (the trimmed user features on their own timeline,
    needed to detect extra pauses that DTW would squeeze onto a couple of
    native frames) and `local_slope` (the warping path's tempo-normalized
    local slope per native frame — the rhythm signal, PRD 8.6).
    """
    native: ProsodyFeatures
    user: ProsodyFeatures
    path: list  # list[(native_idx, user_idx)], monotonic
    local_slope: np.ndarray  # per native frame; 1.0 = on the native's rhythm (SLOPE_WINDOW_S, scoring)
    tag_slope: np.ndarray  # same signal at SLOPE_TAG_WINDOW_S, for segment tagging
    user_f0_hz: np.ndarray
    user_voiced: np.ndarray
    user_f0_semitone: np.ndarray
    user_rms: np.ndarray
    user_rms_z: np.ndarray

# ------------------------------------------------------------------------
# 4. DTW alignment (hand-rolled — see worker_plan.md §1 for the justification
#    over dtw-python: this problem is a few hundred to ~1500 frames per side,
#    trivial for an O(n*m) numpy matrix, and hand-rolling avoids adding
#    another native/C-extension dependency).
# ------------------------------------------------------------------------

def align(
    native: ProsodyFeatures,
    user: ProsodyFeatures,
    *,
    energy_lambda: float = DTW_ENERGY_LAMBDA,
) -> Aligned:
    """DTW-align on a joint pitch+energy cost; one path for everything.

    dsp-1 aligned on pitch alone, which made pauses invisible: unvoiced gaps
    are pitch-interpolated (a fabricated straight line), so the path could
    glide through a native pause at ~zero cost. The joint frame cost
    |Δsemitone| + DTW_ENERGY_LAMBDA·|Δrms_z| makes silences anchor the
    alignment — matching a native pause frame to a user loud frame is now
    expensive (PRD 8.6.3). Still a single warping path, so "you diverged at
    time T" remains a coherent story (§4 step 6).
    """
    len_n, len_u = len(native), len(user)
    ratio = max(len_n, len_u) / max(1, min(len_n, len_u))
    if ratio > MAX_LENGTH_RATIO:
        raise LengthRatioError(
            f"Trimmed length ratio {ratio:.2f} exceeds {MAX_LENGTH_RATIO}:1 "
            f"(native={len_n} frames, user={len_u} frames)."
        )

    # The DTW energy feature is PEAK-normalized RMS (0..1), not rms_z: z-scoring
    # divides by the clip's RMS std, which explodes measurement noise into full
    # ±σ swings on low-dynamic clips and lets noise outshout the pitch signal.
    # Peak normalization keeps the property that matters for alignment —
    # silence (~0) vs. speech (>0.2) anchors pauses — without the blow-up.
    # rms_z remains the energy feature for *scoring*, where cross-clip
    # comparability of contour shape is the point.
    native_rms_n = native.rms / max(np.max(native.rms), 1e-12)
    user_rms_n = user.rms / max(np.max(user.rms), 1e-12)
    path = _dtw_path(native.f0_semitone, native_rms_n, user.f0_semitone, user_rms_n, energy_lambda)
    local_slope = _path_local_slope(path, len_n, len_u, SLOPE_WINDOW_S)
    tag_slope = _path_local_slope(path, len_n, len_u, SLOPE_TAG_WINDOW_S)

    user_f0_hz = _apply_path_mean(path, len_n, user.f0_hz)
    user_f0_semitone = _apply_path_mean(path, len_n, user.f0_semitone)
    user_rms = _apply_path_mean(path, len_n, user.rms)
    user_rms_z = _apply_path_mean(path, len_n, user.rms_z)
    user_voiced = _apply_path_any(path, len_n, user.voiced)

    return Aligned(
        native=native,
        user=user,
        path=path,
        local_slope=local_slope,
        tag_slope=tag_slope,
        user_f0_hz=user_f0_hz,
        user_voiced=user_voiced,
        user_f0_semitone=user_f0_semitone,
        user_rms=user_rms,
        user_rms_z=user_rms_z,
    )


def _dtw_path(
    native_pitch: np.ndarray,
    native_energy: np.ndarray,
    user_pitch: np.ndarray,
    user_energy: np.ndarray,
    energy_lambda: float = DTW_ENERGY_LAMBDA,
) -> list:
    """Sakoe-Chiba-banded DTW on the joint pitch+energy frame cost.
    Returns the warping path as (i, j) index pairs, i in [0, n), j in [0, m).
    """
    n, m = len(native_pitch), len(user_pitch)
    band = max(1, int(SAKOE_CHIBA_BAND_FRAC * max(n, m)))

    INF = np.inf
    cost = np.full((n + 1, m + 1), INF, dtype=np.float64)
    cost[0, 0] = 0.0

    # Scale factor so the band follows the diagonal even when n != m.
    scale = m / n if n > 0 else 1.0

    for i in range(1, n + 1):
        center = i * scale
        j_lo = max(1, int(center - band))
        j_hi = min(m, int(center + band))
        for j in range(j_lo, j_hi + 1):
            d = (
                abs(native_pitch[i - 1] - user_pitch[j - 1])
                + energy_lambda * abs(native_energy[i - 1] - user_energy[j - 1])
                + DTW_DIAG_PULL * abs(j - center)
            )
            best_prev = min(
                cost[i - 1, j] + DTW_STEP_PENALTY,
                cost[i, j - 1] + DTW_STEP_PENALTY,
                cost[i - 1, j - 1],
            )
            cost[i, j] = d + best_prev

    # Backtrack from (n, m) to (0, 0).
    path = []
    i, j = n, m
    while i > 0 or j > 0:
        path.append((i - 1, j - 1))
        if i == 0:
            j -= 1
        elif j == 0:
            i -= 1
        else:
            diag = cost[i - 1, j - 1]
            up = cost[i - 1, j] + DTW_STEP_PENALTY
            left = cost[i, j - 1] + DTW_STEP_PENALTY
            step = min(diag, up, left)
            if step == diag:
                i, j = i - 1, j - 1
            elif step == up:
                i -= 1
            else:
                j -= 1
    path.reverse()
    return path


def _apply_path_mean(path: list, len_n: int, source: np.ndarray) -> np.ndarray:
    """For each native frame index, average whichever source[j] values the
    DTW path matched to it (a native frame can match multiple user frames).
    """
    sums = np.zeros(len_n, dtype=np.float64)
    counts = np.zeros(len_n, dtype=np.int64)
    for i, j in path:
        sums[i] += source[j]
        counts[i] += 1
    counts = np.where(counts == 0, 1, counts)  # guard: every i should be hit at least once
    return sums / counts


def _apply_path_any(path: list, len_n: int, source: np.ndarray) -> np.ndarray:
    """Boolean variant of _apply_path_mean: True if any matched user frame was True."""
    result = np.zeros(len_n, dtype=bool)
    for i, j in path:
        if source[j]:
            result[i] = True
    return result


def _path_local_slope(path: list, len_n: int, len_u: int, window_s: float) -> np.ndarray:
    """Tempo-normalized local slope of the warping path, per native frame.

    j_mean[i] is the mean user index the path matched to native frame i; its
    slope over a ~SLOPE_WINDOW_S window is how many user frames the user
    "spent" per native frame locally. Dividing by the median raw slope makes
    1.0 mean "on the native's rhythm once overall speed is factored out" — a
    uniformly slower read is a tempo choice, not a rhythm error (PRD 8.6.1).
    This is the signal DTW's warping would otherwise erase from the
    pitch/energy RMSE.

    The tempo estimate is the MEDIAN raw slope, not len_u/len_n: energy-based
    trimming always leaves a few near-silent frames past the true speech
    boundary (the RMS window smears energy outward), and a length ratio lets
    those junk edge frames impose a constant spurious deviation across the
    whole clip. The median is dominated by the path's interior, so edge junk
    only costs at the edges.
    """
    j_mean = _apply_path_mean(path, len_n, np.arange(len_u, dtype=np.float64))
    half_w = max(1, int(round((window_s / FRAME_HOP_S) / 2)))
    raw = np.empty(len_n, dtype=np.float64)
    for i in range(len_n):
        lo = max(0, i - half_w)
        hi = min(len_n - 1, i + half_w)
        raw[i] = (j_mean[hi] - j_mean[lo]) / max(1, hi - lo)
    tempo = float(np.median(raw))
    if tempo <= 0:
        tempo = len_u / max(1, len_n)  # degenerate path: fall back to length ratio
    slope = raw / tempo
    # Clamp so log2() stays finite when the path locally flatlines.
    return np.clip(slope, 0.05, 20.0)

