"""Deterministic unit tests for dsp-2 (the timing/pause upgrade to dsp.py).

dsp-2 extends the dsp-1 scorer (test_dsp.py) with an explicit *timing* axis:
the DTW warping path's local slope, tempo-normalized so that a uniformly
slower/faster reading is NOT penalized, and a joint pitch+energy DTW cost so
that silences (pauses) anchor the alignment. These tests pin the contract of
that upgrade against synthetic audio whose rhythm we control exactly.

We reuse test_dsp.py's synthetic-audio helpers so the two suites generate
signal identically; `_write_piecewise_wav` below adds the phase-continuous,
silence-capable generator the rhythm/pause tests need.
"""
import struct
import wave
from pathlib import Path

import numpy as np
import pytest

import dsp
from test_dsp import _write_sine_wav, _extract


# --- Synthetic audio: piecewise chirp/silence with phase continuity --------

def _write_piecewise_wav(path: Path, segments, sr: int = 16000, amplitude: float = 0.5):
    """Write a mono 16-bit PCM WAV from a list of (f_start_hz, f_end_hz, dur_s).

    Each segment is a linear frequency ramp from f_start_hz to f_end_hz over
    dur_s seconds; `f_start_hz=None` emits silence (zeros) for that duration.

    Phase is accumulated as the running integral of instantaneous frequency
    (2*pi * cumsum(f_inst) / sr) across the WHOLE clip, so voiced segments
    join without a phase discontinuity — no clicks that would inject spurious
    high-frequency energy and confuse the F0 tracker at segment boundaries.
    During a silent segment f_inst = 0, so the phase simply holds and the next
    voiced segment resumes exactly where the previous one left off.
    """
    inst_freq_parts = []
    voiced_parts = []
    for f_start, f_end, dur in segments:
        n = int(dur * sr)
        if f_start is None:
            inst_freq_parts.append(np.zeros(n))
            voiced_parts.append(np.zeros(n, dtype=bool))
        else:
            # endpoint=False so successive segments abut like arange-based time,
            # matching _write_sine_wav's sampling of the instantaneous frequency.
            inst_freq_parts.append(np.linspace(f_start, f_end, n, endpoint=False))
            voiced_parts.append(np.ones(n, dtype=bool))

    inst_freq = np.concatenate(inst_freq_parts)
    voiced = np.concatenate(voiced_parts)

    phase = 2 * np.pi * np.cumsum(inst_freq) / sr
    signal = amplitude * np.sin(phase)
    signal[~voiced] = 0.0  # hard-zero the silent regions

    samples = (signal * 32767).astype(np.int16)
    n_samples = len(samples)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sr)
        wf.writeframes(struct.pack(f"<{n_samples}h", *samples))


def _tags(aligned) -> set:
    """The set of feedback_tag strings make_segments emitted for this pair."""
    return {seg["feedback_tag"] for seg in dsp.make_segments(aligned)}


def _align(native_wav: Path, user_wav: Path):
    """Extract+trim both clips and align user onto the native timeline."""
    native = _extract(native_wav)
    user = _extract(user_wav)
    return dsp.align(native, user)


# --- 1. Identical clips: every component high, slope flat at 1.0 -----------

def test_identical_clips_all_components_high(tmp_path):
    """When native == user, there is nothing to penalize on any axis: pitch,
    timing, and energy RMSE are all ~0, so all four score components must be
    near-perfect. And because the two clips are frame-for-frame identical, the
    DTW path is the diagonal, so the tempo-normalized local slope must sit at
    1.0 everywhere (|log2(slope)| ~ 0), the definition of "matches the native's
    rhythm after removing overall tempo difference".
    """
    native_wav = tmp_path / "native.wav"
    user_wav = tmp_path / "user.wav"
    _write_sine_wav(native_wav, freq_hz=130.0, freq_end_hz=170.0, duration_s=1.5)
    _write_sine_wav(user_wav, freq_hz=130.0, freq_end_hz=170.0, duration_s=1.5)

    aligned = _align(native_wav, user_wav)
    overall, pitch_score, timing_score, energy_score = dsp.score(aligned)

    assert overall > 95
    assert pitch_score > 95
    assert timing_score > 95
    assert energy_score > 95

    # local_slope is defined on the native timeline; a perfect match is flat 1.0.
    assert len(aligned.local_slope) == len(aligned.native)
    assert np.abs(np.log2(aligned.local_slope)).max() < 0.3


# --- 2. Shadow-lag regression (PRD 8.7 / Phase 1.5) ------------------------

def test_shadow_lag_scores_high(tmp_path):
    """A learner shadowing a native clip starts and stops a beat late, so their
    recording is the same utterance wrapped in leading/trailing dead air. That
    edge silence is stripped by trim_silence BEFORE alignment, and the 15%
    Sakoe-Chiba band plus DTW then absorb any residual lag, so the delivery
    itself must still score high. This is the concrete regression guarding the
    PRD 8.7 claim that trim + banded DTW make shadow-lag a non-issue.
    """
    native_wav = tmp_path / "native.wav"
    user_wav = tmp_path / "user.wav"
    _write_sine_wav(native_wav, freq_hz=130.0, freq_end_hz=170.0, duration_s=1.5)
    # 0.5s silence, the SAME 1.5s chirp, 0.3s silence -> only the middle survives trim.
    _write_piecewise_wav(
        user_wav,
        [(None, None, 0.5), (130.0, 170.0, 1.5), (None, None, 0.3)],
    )

    aligned = _align(native_wav, user_wav)
    overall, pitch_score, timing_score, energy_score = dsp.score(aligned)

    assert overall >= 85
    assert timing_score >= 85
    # Pins the post-trim re-normalization of rms_z: with z-scores computed over
    # the UNTRIMMED clip, the user's 0.8s of dead air skews their mean/std and
    # this identical delivery scored ~61 on energy.
    assert energy_score >= 70


# --- 3. Uniform tempo difference must not be penalized ---------------------

def test_uniform_tempo_not_penalized(tmp_path):
    """Reading the same line uniformly slower is a tempo difference, not a
    rhythm error: every syllable is stretched by the same factor, so relative
    timing is preserved. dsp-2 divides the local slope by the global tempo
    ratio precisely so this case reads as slope ~ 1.0 everywhere. A 1.15x
    slower read must therefore keep timing_score high.
    """
    native_wav = tmp_path / "native.wav"
    user_wav = tmp_path / "user.wav"
    _write_sine_wav(native_wav, freq_hz=130.0, freq_end_hz=170.0, duration_s=1.5)
    _write_sine_wav(user_wav, freq_hz=130.0, freq_end_hz=170.0, duration_s=1.725)  # 1.15x

    aligned = _align(native_wav, user_wav)
    _, _, timing_score, _ = dsp.score(aligned)

    assert timing_score >= 85


# --- 4. Non-uniform rhythm IS penalized, and tags the stretched syllable ----

def test_nonuniform_rhythm_penalized(tmp_path):
    """Same total duration (same global tempo) but the internal rhythm is
    warped: the user holds the middle 'syllable' 2x as long and rushes the tail
    to compensate. After tempo normalization the middle's local slope is ~2.0
    (> SLOPE_STRETCH_RATIO of 1.5) while the tail's is ~0.8 (below it), so the
    log2-slope RMSE is non-zero and timing_score must drop clearly below the
    uniform-tempo case, AND exactly the middle segment should raise a
    SYLLABLE_STRETCH tag. The 2x stretch is sized so the warping path deviates
    ~25 frames, still inside the 15% Sakoe-Chiba band, so DTW can actually
    follow it rather than clipping at the band edge.
    """
    native_wav = tmp_path / "native.wav"
    user_wav = tmp_path / "user.wav"
    _write_piecewise_wav(
        native_wav,
        [(130.0, 170.0, 0.5), (170.0, 170.0, 0.25), (170.0, 120.0, 1.25)],  # 2.0s
    )
    _write_piecewise_wav(
        user_wav,
        [(130.0, 170.0, 0.5), (170.0, 170.0, 0.5), (170.0, 120.0, 1.0)],  # 2.0s, mid 2x / tail 0.8x
    )

    aligned = _align(native_wav, user_wav)
    _, _, nonuniform_timing, _ = dsp.score(aligned)

    # Recompute test 3's uniform-tempo pair as the baseline to compare against.
    uni_native = tmp_path / "uni_native.wav"
    uni_user = tmp_path / "uni_user.wav"
    _write_sine_wav(uni_native, freq_hz=130.0, freq_end_hz=170.0, duration_s=1.5)
    _write_sine_wav(uni_user, freq_hz=130.0, freq_end_hz=170.0, duration_s=1.725)
    uni_aligned = _align(uni_native, uni_user)
    _, _, uniform_timing, _ = dsp.score(uni_aligned)

    # A real internal-rhythm error must score clearly worse than a pure tempo
    # difference; 10 points is a wide margin the design should easily clear.
    assert nonuniform_timing < uniform_timing - 10
    assert "SYLLABLE_STRETCH" in _tags(aligned)


# --- 5. Missed pause: native pauses, user speaks through --------------------

def test_pause_missed(tmp_path):
    """The native clip has a real 0.4s pause (> PAUSE_MIN_S) between two tones;
    the user runs the two together with no gap. The joint pitch+energy DTW cost
    keeps the user's continuous energy from being warped to fake a pause, so the
    native's silent frames align against voiced user frames and make_segments
    flags PAUSE_MISSED. The control (user2 == native) has the same pause and
    must NOT flag it, and reproducing the pause must score better overall than
    steamrolling it.
    """
    native_wav = tmp_path / "native.wav"
    user_wav = tmp_path / "user.wav"
    user2_wav = tmp_path / "user2.wav"
    native_segs = [(150.0, 150.0, 0.8), (None, None, 0.4), (150.0, 150.0, 0.8)]
    _write_piecewise_wav(native_wav, native_segs)
    _write_piecewise_wav(user_wav, [(150.0, 150.0, 1.6)])  # no pause
    _write_piecewise_wav(user2_wav, native_segs)           # control: identical to native

    aligned = _align(native_wav, user_wav)
    assert "PAUSE_MISSED" in _tags(aligned)

    aligned2 = _align(native_wav, user2_wav)
    assert "PAUSE_MISSED" not in _tags(aligned2)

    overall_missed, *_ = dsp.score(aligned)
    overall_control, *_ = dsp.score(aligned2)
    assert overall_control > overall_missed


# --- 6. Extra pause: user inserts a pause the native does not have ----------

def test_pause_extra(tmp_path):
    """Mirror of test 5: the native is one continuous tone, the user inserts a
    0.4s pause the original never had. The native's voiced frames then align
    against the user's silent stretch, and make_segments flags PAUSE_EXTRA.
    """
    native_wav = tmp_path / "native.wav"
    user_wav = tmp_path / "user.wav"
    _write_piecewise_wav(native_wav, [(150.0, 150.0, 1.6)])
    _write_piecewise_wav(user_wav, [(150.0, 150.0, 0.8), (None, None, 0.4), (150.0, 150.0, 0.8)])

    aligned = _align(native_wav, user_wav)
    assert "PAUSE_EXTRA" in _tags(aligned)
