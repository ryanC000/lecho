"""Scoring: aligned contours -> 0-100 per-axis and overall scores (PRD 8.6)."""
from dataclasses import dataclass

import numpy as np

from .align import Aligned
from .constants import (
    CONTENT_WEIGHT,
    ENERGY_WEIGHT,
    PITCH_WEIGHT,
    SCORE_K_ENERGY_Z,
    SCORE_K_PITCH_SEMITONES,
    SCORE_K_TIMING,
    TIMING_WEIGHT,
)

@dataclass(frozen=True)
class ScoringParams:
    """The scoring knobs the calibration harness sweeps, as an explicit
    argument to `score` rather than ambient module state.

    Defaults are the shipped constants above, so `score(aligned)` is unchanged
    for every caller. The harness passes trial values instead of monkeypatching
    module globals — a constant that fails to reach the formula is then a
    TypeError at the call site, not a plausible-looking wrong score.
    """
    k_pitch_semitones: float = SCORE_K_PITCH_SEMITONES
    k_timing: float = SCORE_K_TIMING
    k_energy_z: float = SCORE_K_ENERGY_Z
    pitch_weight: float = PITCH_WEIGHT
    timing_weight: float = TIMING_WEIGHT
    energy_weight: float = ENERGY_WEIGHT


DEFAULT_SCORING = ScoringParams()


# ------------------------------------------------------------------------
# 5. Scoring
# ------------------------------------------------------------------------

def score(aligned: Aligned, params: ScoringParams = DEFAULT_SCORING) -> tuple:
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

    pitch_score = 100.0 * np.exp(-pitch_rmse / params.k_pitch_semitones)
    energy_score = 100.0 * np.exp(-energy_rmse / params.k_energy_z)
    timing_score = 100.0 * np.exp(-timing_rmse / params.k_timing)
    overall = (
        params.pitch_weight * pitch_score
        + params.timing_weight * timing_score
        + params.energy_weight * energy_score
    )

    return float(overall), float(pitch_score), float(timing_score), float(energy_score)


def content_score_from_wer(wer: float | None) -> float | None:
    """Map the STT gate's word-error rate to a 0-100 pronunciation score (pure).

    100 = the recognizer heard the target line exactly; it falls linearly to 0 at
    WER >= 1.0 (nothing of the line recognized). None (no transcript / STT could
    not run) stays None so the overall falls back to prosody-only."""
    if wer is None:
        return None
    return 100.0 * (1.0 - min(max(wer, 0.0), 1.0))


def blend_content(prosody_overall: float, content_score: float | None) -> float:
    """Fold the content axis into the overall at CONTENT_WEIGHT (pure).

    overall = (1 - CONTENT_WEIGHT)*prosody + CONTENT_WEIGHT*content. A missing
    content score (STT unavailable) leaves the overall as the prosody score, so
    the content axis never penalizes a take it couldn't measure."""
    if content_score is None:
        return prosody_overall
    return (1.0 - CONTENT_WEIGHT) * prosody_overall + CONTENT_WEIGHT * content_score


def _rmse(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(np.mean((a - b) ** 2)))

