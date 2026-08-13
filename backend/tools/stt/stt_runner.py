"""STT runner for the content gate (ticket 22).

Two callers, one recognizer:

  * On the Windows dev box faster-whisper has no cp314 wheel, so it stays out of
    backend/.venv per the wheel rule and this file is run as a script inside the
    quarantined `stt` conda env — `conda run -n stt python tools/stt/stt_runner.py <wav>`.
  * In the Linux container (cp312) faster-whisper is an ordinary pip dependency,
    so `content_gate` imports `transcribe` and calls it in-process. There is no
    conda in an image, and the subprocess path would fail open there — silently
    disabling the gate in the deployed app.

The faster_whisper import is deliberately inside `_model()`: importing this
module must stay safe in the backend venv, where the package is absent.
"""
import sys

# `base` balances French accuracy (real accented learners must not be wrongly
# rejected) against CPU cost (~2-5s/clip); int8 keeps it light. The Dockerfile
# pre-downloads this same size at build time.
MODEL_SIZE = "base"

_cached = None


def _model():
    """The recognizer, built once per process — loading it costs ~1-2s, which
    the long-lived worker should not pay per job."""
    global _cached
    if _cached is None:
        from faster_whisper import WhisperModel

        _cached = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    return _cached


def transcribe(wav_path: str) -> str:
    """Recognize the French speech in `wav_path` and return the joined text.

    faster-whisper decodes the wav itself, so no pre-resampling is needed."""
    segments, _ = _model().transcribe(wav_path, language="fr", beam_size=5)
    return " ".join(seg.text for seg in segments).strip()


if __name__ == "__main__":
    print(transcribe(sys.argv[1]))
