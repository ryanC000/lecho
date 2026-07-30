"""Feedback segments: contiguous deviation runs, tagged and timestamped (§6)."""
import numpy as np

from .align import Aligned
from .constants import (
    FRAME_HOP_S,
    PAUSE_MIN_S,
    SEGMENT_ENERGY_THRESHOLD_Z,
    SEGMENT_MIN_FRAMES,
    SEGMENT_PITCH_THRESHOLD_SEMITONES,
    SILENCE_RMS_FRAC,
    SLOPE_STRETCH_RATIO,
)

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
    # deviates beyond SLOPE_STRETCH_RATIO in either direction. Uses the
    # shorter tag window so a sub-window stretch isn't diluted below threshold.
    log_slope = np.log2(aligned.tag_slope)
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

