"""Standalone STT runner for the content gate (ticket 22).

Runs inside the quarantined `stt` conda env (faster-whisper has no cp314 wheel,
so it stays out of backend/.venv per the wheel rule). `content_gate.assess`
invokes it as `conda run -n stt python tools/stt/stt_runner.py <wav>` and reads the
recognized French text from stdout. Deliberately imports nothing from the
backend — the stt env has only faster-whisper, not parselmouth/dsp.
"""
import sys

from faster_whisper import WhisperModel


def transcribe(wav_path: str) -> str:
    """Recognize the French speech in `wav_path` and return the joined text.

    `base` balances French accuracy (real accented learners must not be wrongly
    rejected) against CPU cost (~2-5s/clip); int8 keeps it light. faster-whisper
    decodes the wav itself, so no pre-resampling is needed."""
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(wav_path, language="fr", beam_size=5)
    return " ".join(seg.text for seg in segments).strip()


if __name__ == "__main__":
    print(transcribe(sys.argv[1]))
