"""Deterministic unit tests for dsp.py using synthetic sine tones.

worker_plan.md §5 calls out a synthetic sine-wave pair with a known pitch
offset as the harness that keeps the scorer honest before any real audio
exists. The good/bad check on an actual practice line (§5's second bullet)
is explicitly deferred until native reference audio is sourced (§0) — these
tests only need signal generation, not recordings.
"""
from pathlib import Path

import numpy as np
import pytest

from domain import dsp
from tools.synth_audio import write_sine_wav


def _extract(path: Path) -> dsp.ProsodyFeatures:
    snd = dsp.load_mono_16k(path)
    feat = dsp.extract_features(snd)
    return dsp.trim_silence(feat)


# --- load_mono_16k / extract_features sanity -----------------------------

def test_extract_features_detects_known_frequency(tmp_path):
    wav = tmp_path / "tone.wav"
    write_sine_wav(wav, freq_hz=150.0, duration_s=1.0)

    feat = _extract(wav)

    assert feat.voiced.mean() > 0.9  # a clean tone should be voiced almost throughout
    voiced_f0 = feat.f0_hz[feat.voiced]
    assert np.median(voiced_f0) == pytest.approx(150.0, abs=2.0)


# --- Scoring: identical vs. known pitch offset ----------------------------

def test_identical_clips_score_near_perfect(tmp_path):
    native_wav = tmp_path / "native.wav"
    user_wav = tmp_path / "user_good.wav"
    write_sine_wav(native_wav, freq_hz=150.0, duration_s=1.5)
    write_sine_wav(user_wav, freq_hz=150.0, duration_s=1.5)

    native = _extract(native_wav)
    user = _extract(user_wav)
    aligned = dsp.align(native, user)
    overall, pitch_score, timing_score, energy_score = dsp.score(aligned)

    assert overall > 95
    assert pitch_score > 95
    assert timing_score > 95
    assert energy_score > 95


def test_pitch_offset_scores_lower_than_identical(tmp_path):
    """A constant-frequency tone is the wrong stand-in for "pitch offset" here:
    per-clip semitone normalization (§4 step 5) is deliberately relative to
    the clip's OWN median F0, so two flat tones at different absolute Hz
    normalize to the same (flat) contour and correctly score identically —
    that's the design working as intended (it's what lets two speakers with
    different natural pitch ranges both score well on the same intonation).

    The known, deliberate offset that the design SHOULD penalize is a
    difference in contour *shape*: a rising intonation (native/good) vs. a
    flat delivery at the same average pitch (bad) — i.e. the "monotone
    delivery" case worker_plan.md §6 names for INTONATION_DROP.
    """
    native_wav = tmp_path / "native.wav"
    good_wav = tmp_path / "user_good.wav"
    bad_wav = tmp_path / "user_bad.wav"

    write_sine_wav(native_wav, freq_hz=130.0, freq_end_hz=170.0, duration_s=1.5)  # rising intonation
    write_sine_wav(good_wav, freq_hz=130.0, freq_end_hz=170.0, duration_s=1.5)    # same rise
    write_sine_wav(bad_wav, freq_hz=150.0, duration_s=1.5)                        # flat, same average Hz

    native = _extract(native_wav)
    good = _extract(good_wav)
    bad = _extract(bad_wav)

    good_aligned = dsp.align(native, good)
    bad_aligned = dsp.align(native, bad)

    good_overall, good_pitch, _, _ = dsp.score(good_aligned)
    bad_overall, bad_pitch, _, _ = dsp.score(bad_aligned)

    # The core assertion worker_plan.md §5 asks for: a known, deliberate
    # contour difference must produce a clearly, deterministically lower score.
    assert bad_pitch < good_pitch
    assert bad_overall < good_overall
    # The gap should be unmistakable, not noise. Score points shrink as
    # SCORE_K_PITCH_SEMITONES grows (calibration keeps moving it), so pin the
    # gap in distance units: invert score = 100*exp(-rmse/K) and require the
    # flat take to sit >= 1 semitone RMSE further from the native contour.
    rmse_gap = dsp.SCORE_K_PITCH_SEMITONES * np.log(good_pitch / bad_pitch)
    assert rmse_gap > 1.0


# --- Failure modes (worker_plan.md §7) ------------------------------------

def test_length_ratio_abort(tmp_path):
    native_wav = tmp_path / "native.wav"
    user_wav = tmp_path / "user.wav"
    write_sine_wav(native_wav, freq_hz=150.0, duration_s=1.0)
    write_sine_wav(user_wav, freq_hz=150.0, duration_s=4.0)  # 4:1, exceeds MAX_LENGTH_RATIO

    native = _extract(native_wav)
    user = _extract(user_wav)

    with pytest.raises(dsp.LengthRatioError):
        dsp.align(native, user)


def test_silent_clip_raises_no_speech_detected(tmp_path):
    silent_wav = tmp_path / "silent.wav"
    write_sine_wav(silent_wav, freq_hz=150.0, duration_s=1.0, amplitude=0.0)

    snd = dsp.load_mono_16k(silent_wav)
    feat = dsp.extract_features(snd)

    with pytest.raises(dsp.NoSpeechDetectedError):
        dsp.trim_silence(feat)


# --- Segments + archive: shape/consistency, not exact values --------------

def test_make_segments_and_archive_shapes(tmp_path):
    native_wav = tmp_path / "native.wav"
    bad_wav = tmp_path / "user_bad.wav"
    write_sine_wav(native_wav, freq_hz=150.0, duration_s=1.5)
    write_sine_wav(bad_wav, freq_hz=150.0 * (2 ** (4 / 12)), duration_s=1.5)

    native = _extract(native_wav)
    bad = _extract(bad_wav)
    aligned = dsp.align(native, bad)

    segments = dsp.make_segments(aligned)
    assert isinstance(segments, list)
    for seg in segments:
        assert seg["timestamp_start"] <= seg["timestamp_end"]
        assert seg["feedback_tag"] in {
            "INTONATION_DROP",
            "ENERGY_FLAT",
            "EMPHASIS_MISSED",
            "SYLLABLE_STRETCH",
            "PAUSE_MISSED",
            "PAUSE_EXTRA",
        }

    archive = dsp.build_archive(aligned)
    n = len(native)
    assert len(archive["times"]) == n
    assert len(archive["native_f0_hz"]) == n
    assert len(archive["user_f0_hz_aligned"]) == n
    assert len(archive["voiced_masks"]["native"]) == n
    assert len(archive["voiced_masks"]["user_aligned"]) == n


# --- Content axis (STT pronunciation score, 2026-07-28) ------------------

def test_content_score_from_wer_maps_wer_to_0_100():
    assert dsp.content_score_from_wer(0.0) == 100.0     # exact recognition
    assert dsp.content_score_from_wer(1.0) == 0.0       # nothing recognized
    assert dsp.content_score_from_wer(0.3) == pytest.approx(70.0)


def test_content_score_from_wer_clamps_and_passes_none():
    assert dsp.content_score_from_wer(1.5) == 0.0       # WER > 1 (insertions) clamps to 0
    assert dsp.content_score_from_wer(-0.1) == 100.0    # defensive lower clamp
    assert dsp.content_score_from_wer(None) is None     # STT unavailable → no axis


def test_blend_content_folds_axis_at_content_weight():
    cw = dsp.CONTENT_WEIGHT
    assert dsp.blend_content(80.0, 40.0) == pytest.approx((1 - cw) * 80.0 + cw * 40.0)


def test_blend_content_none_is_prosody_only():
    assert dsp.blend_content(72.5, None) == 72.5        # fails open: no content penalty
