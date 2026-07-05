"""Deterministic unit tests for dsp.py using synthetic sine tones.

worker_plan.md §5 calls out a synthetic sine-wave pair with a known pitch
offset as the harness that keeps the scorer honest before any real audio
exists. The good/bad check on an actual practice line (§5's second bullet)
is explicitly deferred until native reference audio is sourced (§0) — these
tests only need signal generation, not recordings.
"""
import struct
import wave
from pathlib import Path

import numpy as np
import pytest

import dsp


def _write_sine_wav(
    path: Path,
    freq_hz: float,
    duration_s: float,
    sr: int = 16000,
    amplitude: float = 0.5,
    freq_end_hz: float = None,
):
    """Write a mono 16-bit PCM WAV. If freq_end_hz is given, generates a
    linear frequency sweep (chirp) from freq_hz to freq_end_hz instead of a
    constant tone — used to simulate an intonation contour (e.g. a rise)
    rather than a flat pitch.
    """
    n_samples = int(duration_s * sr)
    t = np.arange(n_samples) / sr
    if freq_end_hz is None:
        phase = 2 * np.pi * freq_hz * t
    else:
        # Linear chirp: instantaneous frequency f(t) = freq_hz + (freq_end_hz-freq_hz)*t/duration_s
        phase = 2 * np.pi * (freq_hz * t + (freq_end_hz - freq_hz) / (2 * duration_s) * t ** 2)
    samples = (amplitude * np.sin(phase) * 32767).astype(np.int16)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sr)
        wf.writeframes(struct.pack(f"<{n_samples}h", *samples))


def _extract(path: Path) -> dsp.ProsodyFeatures:
    snd = dsp.load_mono_16k(path)
    feat = dsp.extract_features(snd)
    return dsp.trim_silence(feat)


# --- load_mono_16k / extract_features sanity -----------------------------

def test_extract_features_detects_known_frequency(tmp_path):
    wav = tmp_path / "tone.wav"
    _write_sine_wav(wav, freq_hz=150.0, duration_s=1.0)

    feat = _extract(wav)

    assert feat.voiced.mean() > 0.9  # a clean tone should be voiced almost throughout
    voiced_f0 = feat.f0_hz[feat.voiced]
    assert np.median(voiced_f0) == pytest.approx(150.0, abs=2.0)


# --- Scoring: identical vs. known pitch offset ----------------------------

def test_identical_clips_score_near_perfect(tmp_path):
    native_wav = tmp_path / "native.wav"
    user_wav = tmp_path / "user_good.wav"
    _write_sine_wav(native_wav, freq_hz=150.0, duration_s=1.5)
    _write_sine_wav(user_wav, freq_hz=150.0, duration_s=1.5)

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

    _write_sine_wav(native_wav, freq_hz=130.0, freq_end_hz=170.0, duration_s=1.5)  # rising intonation
    _write_sine_wav(good_wav, freq_hz=130.0, freq_end_hz=170.0, duration_s=1.5)    # same rise
    _write_sine_wav(bad_wav, freq_hz=150.0, duration_s=1.5)                        # flat, same average Hz

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
    assert good_pitch - bad_pitch > 20  # the gap should be unmistakable, not noise


# --- Failure modes (worker_plan.md §7) ------------------------------------

def test_length_ratio_abort(tmp_path):
    native_wav = tmp_path / "native.wav"
    user_wav = tmp_path / "user.wav"
    _write_sine_wav(native_wav, freq_hz=150.0, duration_s=1.0)
    _write_sine_wav(user_wav, freq_hz=150.0, duration_s=4.0)  # 4:1, exceeds MAX_LENGTH_RATIO

    native = _extract(native_wav)
    user = _extract(user_wav)

    with pytest.raises(dsp.LengthRatioError):
        dsp.align(native, user)


def test_silent_clip_raises_no_speech_detected(tmp_path):
    silent_wav = tmp_path / "silent.wav"
    _write_sine_wav(silent_wav, freq_hz=150.0, duration_s=1.0, amplitude=0.0)

    snd = dsp.load_mono_16k(silent_wav)
    feat = dsp.extract_features(snd)

    with pytest.raises(dsp.NoSpeechDetectedError):
        dsp.trim_silence(feat)


# --- Segments + archive: shape/consistency, not exact values --------------

def test_make_segments_and_archive_shapes(tmp_path):
    native_wav = tmp_path / "native.wav"
    bad_wav = tmp_path / "user_bad.wav"
    _write_sine_wav(native_wav, freq_hz=150.0, duration_s=1.5)
    _write_sine_wav(bad_wav, freq_hz=150.0 * (2 ** (4 / 12)), duration_s=1.5)

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
