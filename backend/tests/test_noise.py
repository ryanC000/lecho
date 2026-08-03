"""Ambient-noise pipeline tests (master-plan ticket 17).

Covers the pre-scoring cleanup applied to the USER clip only: the 80-4000 Hz
bandpass, the SNR estimate persisted on the asset row, and the SNR gate that
decides whether the first 300ms is a trustworthy noise profile.
"""
import numpy as np
import pytest

from domain.dsp import noise
from tools.synth_audio import write_sine_wav

SR = 16000
DURATION_S = 3.0


def _tone(freq_hz, duration_s=DURATION_S, amplitude=0.5, sr=SR):
    t = np.arange(int(duration_s * sr)) / sr
    return amplitude * np.sin(2 * np.pi * freq_hz * t)


def _with_ambient_lead_in(signal, noise_amp, sr=SR, seed=0):
    """A realistic take: `noise_amp` white noise throughout, but only ambient
    (no speech) for the first NOISE_PROFILE_S."""
    rng = np.random.default_rng(seed)
    body = signal.copy()
    body[: int(noise.NOISE_PROFILE_S * sr)] = 0.0
    return body + rng.normal(0, noise_amp, len(body))


# --- Bandpass --------------------------------------------------------------

def test_bandpass_attenuates_out_of_band_and_keeps_speech_band():
    rumble, speech, hiss = _tone(30.0), _tone(300.0), _tone(6000.0)
    filtered = noise.bandpass(rumble + speech + hiss, SR)

    # Correlate the result against each component to see what survived.
    def retained(component):
        return abs(float(np.dot(filtered, component) / np.dot(component, component)))

    assert retained(speech) > 0.9   # in-band, essentially untouched
    assert retained(rumble) < 0.1   # below the 80 Hz corner
    assert retained(hiss) < 0.1     # above the 4000 Hz corner


# --- SNR estimate ----------------------------------------------------------

def test_snr_is_high_when_the_lead_in_is_quiet_ambient():
    clip = _with_ambient_lead_in(_tone(200.0), noise_amp=0.02)
    assert noise.snr_db(noise.bandpass(clip, SR), SR) > noise.MIN_PROFILE_SNR_DB


def test_snr_is_near_zero_when_the_lead_in_is_already_speech():
    # A tone from sample zero: the "noise profile" is as loud as the body, so
    # the estimate must land near 0 dB and stay under the gate.
    snr = noise.snr_db(noise.bandpass(_tone(200.0), SR), SR)
    assert abs(snr) < 1.0
    assert snr < noise.MIN_PROFILE_SNR_DB


def test_snr_is_none_on_a_silent_clip_rather_than_dividing_by_zero():
    # The pure pipeline rejects this downstream (NoSpeechDetectedError); here it
    # must simply not blow up on log10(0/0).
    assert noise.snr_db(noise.bandpass(np.zeros(int(DURATION_S * SR)), SR), SR) is None


def test_a_silent_lead_in_reads_as_a_high_snr():
    # Zero-phase filter ringing leaves a digitally-silent lead-in slightly above
    # zero, so this lands on the high-SNR path rather than the None guard.
    clip = _tone(200.0)
    clip[: int(noise.NOISE_PROFILE_S * SR)] = 0.0
    assert noise.snr_db(noise.bandpass(clip, SR), SR) > noise.MIN_PROFILE_SNR_DB


def test_snr_is_none_when_the_clip_is_shorter_than_the_noise_profile():
    short = _tone(200.0, duration_s=noise.NOISE_PROFILE_S / 2)
    assert noise.snr_db(noise.bandpass(short, SR), SR) is None


# --- The SNR gate ----------------------------------------------------------

def test_reduction_is_skipped_when_the_profile_is_not_credibly_ambient():
    # Speech from sample zero: subtracting this "profile" would eat the user's
    # own voice, so denoise must stop after the bandpass.
    clip = _tone(200.0)
    cleaned, snr = noise.denoise(clip, SR)

    assert snr < noise.MIN_PROFILE_SNR_DB
    assert cleaned == pytest.approx(noise.bandpass(clip, SR))


def test_reduction_runs_and_lowers_the_noise_floor_when_the_lead_in_is_ambient():
    clip = _with_ambient_lead_in(_tone(200.0), noise_amp=0.05)
    cleaned, snr = noise.denoise(clip, SR)
    banded = noise.bandpass(clip, SR)

    assert snr > noise.MIN_PROFILE_SNR_DB
    # The lead-in holds nothing but ambient noise: reduction must measurably
    # quiet it relative to the bandpass-only signal.
    lead_in = slice(0, int(noise.NOISE_PROFILE_S * SR))
    assert _rms(cleaned[lead_in]) < 0.5 * _rms(banded[lead_in])


def _rms(x):
    return float(np.sqrt(np.mean(x ** 2)))


# --- The orchestrator seam -------------------------------------------------

def test_denoise_clip_loads_a_stored_clip_and_returns_a_sound(tmp_path):
    wav = tmp_path / "take.wav"
    write_sine_wav(wav, freq_hz=120.0, duration_s=DURATION_S, freq_end_hz=180.0)

    snd, snr = noise.denoise_clip(wav)

    assert snd.sampling_frequency == 16000
    assert snd.values.shape[0] == 1
    assert snr is not None
