"""Server-side audio metadata extraction.

Captured once at ingest so the DSP worker (and product analytics) never has to
re-derive sample rate / channels / duration from an archived blob later.

Phase 1 expects standard PCM WAV (the frontend transcodes MediaRecorder output
to 16-bit PCM WAV before upload), so the stdlib `wave` module is enough and we
avoid pulling in a heavy audio dependency this early.
"""
import wave
from dataclasses import dataclass
from pathlib import Path


class InvalidAudioError(ValueError):
    """Raised when the uploaded bytes are not a readable PCM WAV file."""


@dataclass
class AudioMeta:
    duration_seconds: float
    sample_rate: int
    channels: int
    codec: str


def extract_metadata(path: Path) -> AudioMeta:
    try:
        with wave.open(str(path), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()  # bytes per sample
    except (wave.Error, EOFError) as exc:
        raise InvalidAudioError(f"Not a readable PCM WAV file: {exc}") from exc

    if rate <= 0:
        raise InvalidAudioError("WAV reports a non-positive sample rate.")

    duration = frames / float(rate)
    codec = f"pcm_s{sample_width * 8}le"  # wave only handles little-endian PCM
    return AudioMeta(
        duration_seconds=duration,
        sample_rate=rate,
        channels=channels,
        codec=codec,
    )
