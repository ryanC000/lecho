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

PITCH_WEIGHT = 0.7
ENERGY_WEIGHT = 0.3

MAX_LENGTH_RATIO = 3.0      # PRD §6 abort: longer/shorter trimmed duration
SAKOE_CHIBA_BAND_FRAC = 0.15  # DTW band width as a fraction of the longer sequence
SILENCE_RMS_FRAC = 0.1      # frames below this fraction of peak RMS are "silence"

# Placeholder until the good/bad calibration harness (§5) fixes real values.
# Larger K => score falls off more slowly with distance.
SCORE_K_PITCH_SEMITONES = 4.0
SCORE_K_ENERGY_Z = 1.5

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
    """
    native: ProsodyFeatures
    path: list  # list[(native_idx, user_idx)], for archival/debugging
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
    mean = np.mean(values)
    std = np.std(values)
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
    trimmed = ProsodyFeatures(
        times=feat.times[start:end],
        f0_hz=feat.f0_hz[start:end],
        voiced=feat.voiced[start:end],
        f0_semitone=feat.f0_semitone[start:end],
        rms=feat.rms[start:end],
        rms_z=feat.rms_z[start:end],
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
    """DTW-align on the pitch (semitone) contour; apply the same path to RMS.

    Aligning pitch and energy independently would produce two different
    time-warps, making a coherent "you diverged at time T" story impossible
    (§4 step 6). Pitch is the reliable alignment cue; energy rides the same
    path the pitch alignment already found.
    """
    len_n, len_u = len(native), len(user)
    ratio = max(len_n, len_u) / max(1, min(len_n, len_u))
    if ratio > MAX_LENGTH_RATIO:
        raise LengthRatioError(
            f"Trimmed length ratio {ratio:.2f} exceeds {MAX_LENGTH_RATIO}:1 "
            f"(native={len_n} frames, user={len_u} frames)."
        )

    path = _dtw_path(native.f0_semitone, user.f0_semitone)

    user_f0_hz = _apply_path_mean(path, len_n, user.f0_hz)
    user_f0_semitone = _apply_path_mean(path, len_n, user.f0_semitone)
    user_rms = _apply_path_mean(path, len_n, user.rms)
    user_rms_z = _apply_path_mean(path, len_n, user.rms_z)
    user_voiced = _apply_path_any(path, len_n, user.voiced)

    return Aligned(
        native=native,
        path=path,
        user_f0_hz=user_f0_hz,
        user_voiced=user_voiced,
        user_f0_semitone=user_f0_semitone,
        user_rms=user_rms,
        user_rms_z=user_rms_z,
    )


def _dtw_path(native_seq: np.ndarray, user_seq: np.ndarray) -> list:
    """Sakoe-Chiba-banded DTW. Returns the warping path as (i, j) index pairs,
    i in [0, len(native_seq)), j in [0, len(user_seq)).
    """
    n, m = len(native_seq), len(user_seq)
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
            d = abs(native_seq[i - 1] - user_seq[j - 1])
            best_prev = min(cost[i - 1, j], cost[i, j - 1], cost[i - 1, j - 1])
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
            step = min(cost[i - 1, j], cost[i, j - 1], cost[i - 1, j - 1])
            if step == cost[i - 1, j - 1]:
                i, j = i - 1, j - 1
            elif step == cost[i - 1, j]:
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


# ------------------------------------------------------------------------
# 5. Scoring
# ------------------------------------------------------------------------

def score(aligned: Aligned) -> tuple:
    """Returns (overall, pitch_score, energy_score), each 0-100.

    The RMSE -> percentage mapping (score = 100*exp(-rmse/K)) is a deliberate
    placeholder: K cannot be derived on paper and requires the good/bad
    calibration harness (worker_plan.md §5) to tune once real recordings
    exist. SCORE_K_PITCH_SEMITONES / SCORE_K_ENERGY_Z are that placeholder.
    """
    pitch_rmse = _rmse(aligned.native.f0_semitone, aligned.user_f0_semitone)
    energy_rmse = _rmse(aligned.native.rms_z, aligned.user_rms_z)

    pitch_score = 100.0 * np.exp(-pitch_rmse / SCORE_K_PITCH_SEMITONES)
    energy_score = 100.0 * np.exp(-energy_rmse / SCORE_K_ENERGY_Z)
    overall = PITCH_WEIGHT * pitch_score + ENERGY_WEIGHT * energy_score

    return float(overall), float(pitch_score), float(energy_score)


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

    segments.sort(key=lambda s: s["timestamp_start"])
    return segments


def _find_runs(mask: np.ndarray) -> list:
    """Contiguous True runs of at least SEGMENT_MIN_FRAMES, as (start, end) half-open indices."""
    runs = []
    start = None
    for i, val in enumerate(mask):
        if val and start is None:
            start = i
        elif not val and start is not None:
            if i - start >= SEGMENT_MIN_FRAMES:
                runs.append((start, i))
            start = None
    if start is not None and len(mask) - start >= SEGMENT_MIN_FRAMES:
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
