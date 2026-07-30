"""Synthetic WAV generation for tests and the calibration smoke corpus.

Lives here rather than in the test suite because `calibrate.py --smoke` needs
it to build its synthetic corpus, and a dev tool must not import a test module.
"""
import struct
import wave
from pathlib import Path

import numpy as np


def write_sine_wav(
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
