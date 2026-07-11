"""Pure DSP core for prosody scoring (worker_plan.md Part 1.2).

Every function here is stateless: inputs are paths/arrays, outputs are
arrays/scores/dicts. No SQLAlchemy, no `storage.py` calls, no FastAPI. This
is what makes it directly unit-testable with synthetic audio, and what lets
`worker/main.py` (the future SQS entrypoint) import the exact same module
the in-process orchestrator (`backend/main.py::worker_task`) uses — the
Phase 3 split becomes a transport swap, not an algorithm rewrite.

Pipeline (see worker_plan.md §4 for the full rationale):
    load_mono_16k -> extract_features -> trim_silence -> align -> score /
    make_segments / build_archive
"""
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import parselmouth

# --- Tunable constants -------------------------------------------------
# All named here (not buried in function bodies) so the scoring-calibration
# harness (worker_plan.md §5) has one place to adjust when real recordings
# are available to tune against.

FRAME_HOP_S = 0.01          # 10ms frame grid shared by F0 and RMS
TARGET_SR = 16000           # standard speech-processing rate; also cheap
PITCH_FLOOR_HZ = 75.0       # speech F0 range (worker_plan.md §9 open question, resolved here)
PITCH_CEILING_HZ = 500.0
RMS_WINDOW_S = 0.025        # ~25ms RMS window, centered on each F0 frame time

PITCH_WEIGHT = 0.55
TIMING_WEIGHT = 0.25
ENERGY_WEIGHT = 0.20

DTW_ENERGY_LAMBDA = 0.5     # weight of |Δrms_z| in the joint DTW frame cost (PRD 8.6.3)
# Path regularization (dsp-2). Without it the timing score is unusable:
# on gently-varying contours many paths cost within pitch-tracker noise
# (~0.02 st) of each other, so the "optimal" path zig-zags randomly and the
# slope reads noise as rhythm error.
# - STEP_PENALTY: extra cost per non-diagonal step. Kills gratuitous
#   insert/delete zig-zags (noise-scale payoff) while leaving genuine warps
#   intact — following a real 2x syllable stretch pays semitone-scale costs,
#   10-100x larger than the penalty it incurs.
# - DIAG_PULL: tiny attraction toward the scaled diagonal so the mandatory
#   |n-m| insertions spread evenly through flat-cost regions instead of
#   clumping wherever the backtracker happens to walk.
#   Values swept empirically (see master_implementation_plan.md appendix, Phase 1.5): larger
#   STEP_PENALTY (0.05+) makes the path under-warp genuine 2x syllable
#   stretches on gently-sloped contours; 0.02 keeps real warps sharp while
#   still suppressing noise zig-zag.
DTW_STEP_PENALTY = 0.02
DTW_DIAG_PULL = 0.002

MAX_LENGTH_RATIO = 3.0      # PRD §6 abort: longer/shorter trimmed duration
SAKOE_CHIBA_BAND_FRAC = 0.15  # DTW band width as a fraction of the longer sequence
SILENCE_RMS_FRAC = 0.1      # frames below this fraction of peak RMS are "silence"

# Placeholder until the good/bad calibration harness (§5) fixes real values.
# Larger K => score falls off more slowly with distance.
SCORE_K_PITCH_SEMITONES = 4.0
SCORE_K_ENERGY_Z = 1.5
SCORE_K_TIMING = 0.4        # timing: rmse of log2(tempo-normalized path slope)

SLOPE_WINDOW_S = 0.15       # window over which the local warping-path slope is measured
SLOPE_STRETCH_RATIO = 1.5   # |log2(slope)| beyond log2(this) tags SYLLABLE_STRETCH
PAUSE_MIN_S = 0.15          # minimum silent run to count as a pause (PRD 8.6.3)

SEGMENT_PITCH_THRESHOLD_SEMITONES = 2.0
SEGMENT_ENERGY_THRESHOLD_Z = 1.0
SEGMENT_MIN_FRAMES = 3


class DspError(Exception):
    """Base class for errors the worker orchestrator should map to FAILED."""


class NoSpeechDetectedError(DspError):
    """Raised when a clip has no voiced frames after silence trimming."""


class LengthRatioError(DspError):
    """Raised when trimmed clip lengths differ by more than MAX_LENGTH_RATIO."""


@dataclass
class ProsodyFeatures:
    times: np.ndarray        # frame-center times, seconds
    f0_hz: np.ndarray        # gap-interpolated; 0 only if the whole clip is unvoiced
    voiced: np.ndarray       # bool mask, raw voiced/unvoiced per frame
    f0_semitone: np.ndarray  # 12*log2(f0 / median_voiced_f0), per-clip normalized
    rms: np.ndarray
    rms_z: np.ndarray        # (rms - mean) / std, per-clip normalized

    def __len__(self):
        return len(self.times)


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
    local_slope: np.ndarray  # per native frame; 1.0 = on the native's rhythm
    user_f0_hz: np.ndarray
    user_voiced: np.ndarray
    user_f0_semitone: np.ndarray
    user_rms: np.ndarray
    user_rms_z: np.ndarray


# ------------------------------------------------------------------------
# 1. Load & standardize
# ------------------------------------------------------------------------

def load_mono_16k(path: Path) -> parselmouth.Sound:
    """Load an audio file and standardize to mono, TARGET_SR.

    Defensive because the native reference may arrive stereo/44.1kHz from
    wherever it's sourced; the user clip is mono but typically 48kHz from the
    browser. Both are normalized to the same rate here so frame timing is
    directly comparable downstream.
    """
    snd = parselmouth.Sound(str(path))
    if snd.n_channels > 1:
        snd = snd.convert_to_mono()
    if snd.sampling_frequency != TARGET_SR:
        snd = snd.resample(TARGET_SR)
    return snd


# ------------------------------------------------------------------------
# 2. Feature extraction
# ------------------------------------------------------------------------

def extract_features(snd: parselmouth.Sound) -> ProsodyFeatures:
    """F0 (Praat autocorrelation) and RMS on the same 10ms frame grid.

    F0 frame times come from Praat's pitch object; RMS is computed with a
    window centered on those same times, so the two streams share a frame
    grid without a separate resampling step (worker_plan.md §4 step 2).
    """
    pitch = snd.to_pitch_ac(
        time_step=FRAME_HOP_S,
        pitch_floor=PITCH_FLOOR_HZ,
        pitch_ceiling=PITCH_CEILING_HZ,
    )
    times = pitch.xs()
    f0_raw = pitch.selected_array["frequency"]  # 0.0 where unvoiced
    voiced = f0_raw > 0

    f0_interp = _interpolate_gaps(times, f0_raw, voiced)

    samples = snd.values[0]
    sr = snd.sampling_frequency
    rms = _windowed_rms(samples, sr, times, RMS_WINDOW_S)

    f0_semitone = _to_semitone(f0_interp, voiced)
    rms_z = _zscore(rms)

    return ProsodyFeatures(
        times=times,
        f0_hz=f0_interp,
        voiced=voiced,
        f0_semitone=f0_semitone,
        rms=rms,
        rms_z=rms_z,
    )


def _interpolate_gaps(times: np.ndarray, f0_raw: np.ndarray, voiced: np.ndarray) -> np.ndarray:
    """Linearly interpolate F0 across unvoiced gaps (§4 step 4).

    Raw F0 has holes at consonants/pauses that would corrupt DTW distance
    calculations (a 0 Hz "silence" frame looks like a huge pitch drop). The
    voiced mask is kept separately on ProsodyFeatures for tagging, so nothing
    downstream mistakes an interpolated frame for a real voiced measurement.
    """
    if not voiced.any():
        return f0_raw.copy()
    if voiced.all():
        return f0_raw.copy()
    return np.interp(times, times[voiced], f0_raw[voiced])


def _windowed_rms(samples: np.ndarray, sr: float, times: np.ndarray, window_s: float) -> np.ndarray:
    half_window = int((window_s / 2) * sr)
    n = len(samples)
    rms = np.empty(len(times), dtype=np.float64)
    for i, t in enumerate(times):
        center = int(t * sr)
        start = max(0, center - half_window)
        end = min(n, center + half_window)
        window = samples[start:end]
        rms[i] = np.sqrt(np.mean(window ** 2)) if len(window) > 0 else 0.0
    return rms


def _to_semitone(f0_hz: np.ndarray, voiced: np.ndarray) -> np.ndarray:
    """semitone = 12*log2(f0 / median_voiced_f0), normalized per clip (§4 step 5).

    Reference is the clip's own median *voiced* F0 (not the gap-filled
    array), so normalization isn't skewed by interpolated silence regions.
    """
    if not voiced.any():
        return np.zeros_like(f0_hz)
    median_f0 = np.median(f0_hz[voiced])
    if median_f0 <= 0:
        return np.zeros_like(f0_hz)
    safe_f0 = np.where(f0_hz > 0, f0_hz, median_f0)
    return 12.0 * np.log2(safe_f0 / median_f0)


def _zscore(values: np.ndarray) -> np.ndarray:
    """Z-score with a relative std floor.

    A raw z-score divides by the clip's own std; on low-dynamic signals that
    amplifies measurement noise into full ±σ swings, which then reads as huge
    energy deviation. Flooring the std at 5% of the peak leaves real speech
    untouched (its RMS std is ~20-30% of peak) while keeping the scale sane
    on flat clips.
    """
    mean = np.mean(values)
    std = np.std(values)
    floor = 0.05 * np.max(np.abs(values)) if len(values) else 0.0
    std = max(std, floor)
    if std < 1e-9:
        return np.zeros_like(values)
    return (values - mean) / std


# ------------------------------------------------------------------------
# 3. Silence trimming
# ------------------------------------------------------------------------

def trim_silence(feat: ProsodyFeatures) -> ProsodyFeatures:
    """Trim leading/trailing frames below SILENCE_RMS_FRAC of peak RMS (§4 step 3).

    Dead air at the clip edges would otherwise dominate DTW alignment cost
    and pad the length-ratio check with frames that carry no signal.
    """
    peak = np.max(feat.rms) if len(feat.rms) else 0.0
    if peak <= 0:
        raise NoSpeechDetectedError("Clip is silent — no RMS energy detected.")

    threshold = peak * SILENCE_RMS_FRAC
    above = np.where(feat.rms > threshold)[0]
    if len(above) == 0:
        raise NoSpeechDetectedError("No frames exceed the silence threshold.")

    start, end = above[0], above[-1] + 1
    # f0_semitone and rms_z are RE-NORMALIZED over the trimmed region: the
    # pre-trim versions include the dead air in their median/mean/std, which
    # makes a clip with lead-in silence z-scale incomparably to one without
    # (an identical delivery would read as a large energy deviation).
    trimmed = ProsodyFeatures(
        times=feat.times[start:end],
        f0_hz=feat.f0_hz[start:end],
        voiced=feat.voiced[start:end],
        f0_semitone=_to_semitone(feat.f0_hz[start:end], feat.voiced[start:end]),
        rms=feat.rms[start:end],
        rms_z=_zscore(feat.rms[start:end]),
    )
    if not trimmed.voiced.any():
        raise NoSpeechDetectedError("No voiced frames remain after silence trim.")
    return trimmed


# ------------------------------------------------------------------------
# 4. DTW alignment (hand-rolled — see worker_plan.md §1 for the justification
#    over dtw-python: this problem is a few hundred to ~1500 frames per side,
#    trivial for an O(n*m) numpy matrix, and hand-rolling avoids adding
#    another native/C-extension dependency).
# ------------------------------------------------------------------------

def align(native: ProsodyFeatures, user: ProsodyFeatures) -> Aligned:
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
    path = _dtw_path(native.f0_semitone, native_rms_n, user.f0_semitone, user_rms_n)
    local_slope = _path_local_slope(path, len_n, len_u)

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
                + DTW_ENERGY_LAMBDA * abs(native_energy[i - 1] - user_energy[j - 1])
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


def _path_local_slope(path: list, len_n: int, len_u: int) -> np.ndarray:
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
    half_w = max(1, int(round((SLOPE_WINDOW_S / FRAME_HOP_S) / 2)))
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


# ------------------------------------------------------------------------
# 5. Scoring
# ------------------------------------------------------------------------

def score(aligned: Aligned) -> tuple:
    """Returns (overall, pitch_score, timing_score, energy_score), each 0-100.

    Timing (dsp-2, PRD 8.6.1) scores the warping path itself: RMSE of
    log2(tempo-normalized local slope), so 1.5x local stretch and 0.67x local
    rush are penalized symmetrically and a uniform tempo difference scores ~0
    deviation. Without this component the overall score is structurally blind
    to rhythm — DTW absorbs timing errors before the pitch/energy RMSE sees
    them.

    The RMSE -> percentage mapping (score = 100*exp(-rmse/K)) is a deliberate
    placeholder: K cannot be derived on paper and requires the good/bad
    calibration harness (worker_plan.md §5) to tune once real recordings
    exist. The SCORE_K_* constants are that placeholder.
    """
    pitch_rmse = _rmse(aligned.native.f0_semitone, aligned.user_f0_semitone)
    energy_rmse = _rmse(aligned.native.rms_z, aligned.user_rms_z)
    timing_rmse = float(np.sqrt(np.mean(np.log2(aligned.local_slope) ** 2)))

    pitch_score = 100.0 * np.exp(-pitch_rmse / SCORE_K_PITCH_SEMITONES)
    energy_score = 100.0 * np.exp(-energy_rmse / SCORE_K_ENERGY_Z)
    timing_score = 100.0 * np.exp(-timing_rmse / SCORE_K_TIMING)
    overall = (
        PITCH_WEIGHT * pitch_score
        + TIMING_WEIGHT * timing_score
        + ENERGY_WEIGHT * energy_score
    )

    return float(overall), float(pitch_score), float(timing_score), float(energy_score)


def _rmse(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(np.mean((a - b) ** 2)))


# ------------------------------------------------------------------------
# 6. Feedback segments (MVP subset — worker_plan.md §6)
# ------------------------------------------------------------------------

def make_segments(aligned: Aligned) -> list:
    """Contiguous-deviation runs on the aligned timeline, tagged and mapped
    back to native timestamps. Thresholds are guesses until real recordings
    exist (worker_plan.md §6/§9) — SEGMENT_* constants are the tuning knobs.
    """
    segments = []
    native = aligned.native

    pitch_dev = native.f0_semitone - aligned.user_f0_semitone  # + => user below native
    segments.extend(
        _tag_runs(
            native.times,
            pitch_dev > SEGMENT_PITCH_THRESHOLD_SEMITONES,
            tag="INTONATION_DROP",
            explanation="Your pitch dips below the native speaker's rise here.",
        )
    )

    energy_dev = native.rms_z - aligned.user_rms_z  # + => native louder than user
    for run_start, run_end in _find_runs(energy_dev > SEGMENT_ENERGY_THRESHOLD_Z):
        native_peak = native.rms_z[run_start:run_end]
        is_local_peak = native_peak.max() > (np.mean(native.rms_z) + SEGMENT_ENERGY_THRESHOLD_Z)
        tag = "EMPHASIS_MISSED" if is_local_peak else "ENERGY_FLAT"
        explanation = (
            "The native speaker emphasizes this word with more energy than your recording."
            if tag == "EMPHASIS_MISSED"
            else "Your energy is flatter than the native speaker's here."
        )
        segments.append(
            {
                "timestamp_start": float(native.times[run_start]),
                "timestamp_end": float(native.times[run_end - 1]),
                "feedback_tag": tag,
                "explanation": explanation,
            }
        )

    # SYLLABLE_STRETCH (dsp-2): runs where the tempo-normalized path slope
    # deviates beyond SLOPE_STRETCH_RATIO in either direction.
    log_slope = np.log2(aligned.local_slope)
    stretch_mask = np.abs(log_slope) > np.log2(SLOPE_STRETCH_RATIO)
    for run_start, run_end in _find_runs(stretch_mask):
        stretched = log_slope[run_start:run_end].mean() > 0
        segments.append(
            {
                "timestamp_start": float(native.times[run_start]),
                "timestamp_end": float(native.times[run_end - 1]),
                "feedback_tag": "SYLLABLE_STRETCH",
                "explanation": (
                    "You linger on this part longer than the native speaker."
                    if stretched
                    else "You rush through this part faster than the native speaker."
                ),
            }
        )

    # PAUSE_MISSED / PAUSE_EXTRA (dsp-2): energy-based pause runs. Pauses are
    # detected on raw RMS (fraction of each clip's own peak), not rms_z, so
    # the threshold is meaningful regardless of the clip's loudness spread.
    pause_min_frames = max(SEGMENT_MIN_FRAMES, int(round(PAUSE_MIN_S / FRAME_HOP_S)))
    native_pause = _pause_mask(native.rms)
    user_pause_aligned = _pause_mask(aligned.user_rms)
    for run_start, run_end in _find_runs(native_pause, min_frames=pause_min_frames):
        if user_pause_aligned[run_start:run_end].mean() < 0.3:
            segments.append(
                {
                    "timestamp_start": float(native.times[run_start]),
                    "timestamp_end": float(native.times[run_end - 1]),
                    "feedback_tag": "PAUSE_MISSED",
                    "explanation": "The native speaker pauses here, but you speak straight through.",
                }
            )

    # Extra pauses must be found on the USER's own timeline: DTW compresses a
    # user-only pause onto a couple of native frames, so it would vanish if we
    # only looked at the aligned arrays. Map each user pause run back to the
    # native timestamps its frames were matched to.
    user_pause = _pause_mask(aligned.user.rms)
    for run_start, run_end in _find_runs(user_pause, min_frames=pause_min_frames):
        nat_idx = [i for i, j in aligned.path if run_start <= j < run_end]
        if not nat_idx:
            continue
        lo, hi = min(nat_idx), max(nat_idx)
        if native_pause[lo : hi + 1].mean() > 0.7:
            continue  # the native pauses here too — not an extra pause
        segments.append(
            {
                "timestamp_start": float(native.times[lo]),
                "timestamp_end": float(native.times[hi]),
                "feedback_tag": "PAUSE_EXTRA",
                "explanation": "You pause here, but the native speaker continues without a break.",
            }
        )

    segments.sort(key=lambda s: s["timestamp_start"])
    return segments


def _pause_mask(rms: np.ndarray) -> np.ndarray:
    """Frames quieter than SILENCE_RMS_FRAC of the clip's peak RMS."""
    peak = np.max(rms) if len(rms) else 0.0
    if peak <= 0:
        return np.zeros(len(rms), dtype=bool)
    return rms < peak * SILENCE_RMS_FRAC


def _find_runs(mask: np.ndarray, min_frames: int = SEGMENT_MIN_FRAMES) -> list:
    """Contiguous True runs of at least min_frames, as (start, end) half-open indices."""
    runs = []
    start = None
    for i, val in enumerate(mask):
        if val and start is None:
            start = i
        elif not val and start is not None:
            if i - start >= min_frames:
                runs.append((start, i))
            start = None
    if start is not None and len(mask) - start >= min_frames:
        runs.append((start, len(mask)))
    return runs


def _tag_runs(times: np.ndarray, mask: np.ndarray, tag: str, explanation: str) -> list:
    return [
        {
            "timestamp_start": float(times[start]),
            "timestamp_end": float(times[end - 1]),
            "feedback_tag": tag,
            "explanation": explanation,
        }
        for start, end in _find_runs(mask)
    ]


# ------------------------------------------------------------------------
# 7. Archive (for the future pitch-overlay visualizer — §3 downstream gap)
# ------------------------------------------------------------------------

def build_archive(aligned: Aligned) -> dict:
    """JSON-serializable dict written to storage/analysis/{job_id}.json.

    Stores both Hz (the visualizer shows Hz) and the normalized arrays (for
    deviation coloring), per §4 step 9.
    """
    native = aligned.native
    return {
        "times": native.times.tolist(),
        "native_f0_hz": native.f0_hz.tolist(),
        "user_f0_hz_aligned": aligned.user_f0_hz.tolist(),
        "native_semitone": native.f0_semitone.tolist(),
        "user_semitone_aligned": aligned.user_f0_semitone.tolist(),
        "native_rms": native.rms.tolist(),
        "user_rms_aligned": aligned.user_rms.tolist(),
        "voiced_masks": {
            "native": native.voiced.tolist(),
            "user_aligned": aligned.user_voiced.tolist(),
        },
    }
