"""Ambient-noise cleanup for the user's take (PRD §6.1, master-plan ticket 17).

Deliberately NOT part of the `features_for` pipeline. Denoising rewrites the
RMS contour, so running it inside the pure path would make the scorer's
deterministic tests depend on a spectral-subtraction library. The orchestrator
(`worker/core.py`) calls `denoise_clip` on the USER clip only; the native
reference and every pure-DSP entry point stay untouched.

Two stages, and only the first is unconditional:
  1. Bandpass to the speech band — rumble/handling noise below and hiss above
     carry no prosody, and always cost more than they contribute.
  2. Spectral noise reduction profiled on the clip's first NOISE_PROFILE_S.
     That profile is only trustworthy if the lead-in really is ambient. When a
     user starts speaking immediately it isn't, and subtracting it would eat
     their own voice — so the measured SNR gates this stage (see MIN_PROFILE_SNR_DB).
"""
import numpy as np
import parselmouth
from scipy.signal import butter, sosfiltfilt

from .features import load_mono_16k

BAND_LOW_HZ = 80.0        # below: room rumble, mic handling, mains hum
BAND_HIGH_HZ = 4000.0     # above: hiss; French prosody carries nothing up there
FILTER_ORDER = 4          # 4th-order Butterworth, zero-phase (sosfiltfilt)

NOISE_PROFILE_S = 0.3     # lead-in taken as the ambient-noise profile

# How far the body of the clip must sit above the lead-in for that lead-in to
# count as ambient rather than speech. Measured on synthetic takes: a clip that
# starts mid-speech reads ~0 dB, one with a genuine quiet lead-in reads 11-27 dB,
# so the two cases separate cleanly and this sits conservatively between them.
MIN_PROFILE_SNR_DB = 6.0

_SILENT_RMS = 1e-9        # below this the lead-in is digital silence, not a profile


def bandpass(samples: np.ndarray, sr: float) -> np.ndarray:
    """Zero-phase Butterworth bandpass over the speech band.

    `sosfiltfilt` (not `sosfilt`) because a one-pass IIR smears energy forward
    in time, which would shift the RMS contour the timing/energy axes score.
    """
    sos = butter(FILTER_ORDER, [BAND_LOW_HZ, BAND_HIGH_HZ], btype="bandpass", fs=sr, output="sos")
    return sosfiltfilt(sos, samples)


def snr_db(samples: np.ndarray, sr: float):
    """10*log10(speech_rms^2 / noise_rms^2), profiling the first NOISE_PROFILE_S
    as noise and the remainder as speech.

    None when there is no usable profile — a clip shorter than the window, or a
    lead-in of digital silence (synthetic audio, or a recorder that pads with
    zeros), which would divide by zero.
    """
    split = int(NOISE_PROFILE_S * sr)
    if len(samples) <= split:
        return None
    noise_rms = _rms(samples[:split])
    if noise_rms < _SILENT_RMS:
        return None
    return float(10.0 * np.log10(_rms(samples[split:]) ** 2 / noise_rms ** 2))


def denoise(samples: np.ndarray, sr: float):
    """Clean a raw user signal. Returns (cleaned samples, snr_db or None).

    The SNR is reported whether or not reduction ran — it's a quality signal
    about the recording, persisted on the asset row, not a by-product of the
    filtering.
    """
    banded = bandpass(samples, sr)
    snr = snr_db(banded, sr)
    if snr is None or snr < MIN_PROFILE_SNR_DB:
        return banded, snr

    import noisereduce  # heavy (pulls matplotlib); only loaded when it will run

    profile = banded[: int(NOISE_PROFILE_S * sr)]
    return noisereduce.reduce_noise(y=banded, sr=int(sr), y_noise=profile, stationary=True), snr


def denoise_clip(path):
    """Load a stored clip and clean it. Returns (parselmouth.Sound, snr_db).

    The orchestrator's seam: it hands over a storage path and gets back the
    same kind of Sound `load_mono_16k` produces, so the cleaned signal feeds
    `extract_features` exactly like an untouched one would.
    """
    snd = load_mono_16k(path)
    cleaned, snr = denoise(snd.values[0], snd.sampling_frequency)
    return parselmouth.Sound(cleaned, sampling_frequency=snd.sampling_frequency), snr


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x ** 2)))
