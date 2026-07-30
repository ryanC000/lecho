"""Load, standardize, and extract prosody features (worker_plan.md §4 steps 1-5).

Pipeline stages 1-3: load_mono_16k -> extract_features -> trim_silence, with
features_for() as the standard entry point that composes all three.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import parselmouth

from .constants import (
    FRAME_HOP_S,
    PITCH_CEILING_HZ,
    PITCH_FLOOR_HZ,
    RMS_WINDOW_S,
    SILENCE_RMS_FRAC,
    TARGET_SR,
)
from .errors import NoSpeechDetectedError

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

def extract_features(snd: parselmouth.Sound, *, pitch_floor_hz: float = PITCH_FLOOR_HZ) -> ProsodyFeatures:
    """F0 (Praat autocorrelation) and RMS on the same 10ms frame grid.

    F0 frame times come from Praat's pitch object; RMS is computed with a
    window centered on those same times, so the two streams share a frame
    grid without a separate resampling step (worker_plan.md §4 step 2).

    `pitch_floor_hz` is a parameter only so the calibration harness can sweep it
    (creak/octave diagnostic); production always uses the default.
    """
    pitch = snd.to_pitch_ac(
        time_step=FRAME_HOP_S,
        pitch_floor=pitch_floor_hz,
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


def features_for(path, *, pitch_floor_hz: float = PITCH_FLOOR_HZ) -> ProsodyFeatures:
    """Load a stored clip and produce its trimmed prosody features.

    The pipeline's standard entry point (load → extract → trim), so callers
    don't re-encode the stage order. The stage functions stay public as
    internal seams for the test suite and for callers that already hold a
    loaded Sound (the ingest CLI).
    """
    return trim_silence(extract_features(load_mono_16k(path), pitch_floor_hz=pitch_floor_hz))

