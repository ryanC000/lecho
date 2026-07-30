"""Content gate: reject unintelligible takes before prosody scoring (ticket 22).

The prosody scorer (dsp.py) measures *how* a line was said, never *what* was
said, so gibberish spoken in rhythm scores like a genuine take (2026-07-13
owner report). The defense is a gate, not a graded axis.

Ticket 20 tried MFA *forced* alignment likelihood, but forced alignment maps
the given words onto the audio no matter what was spoken — its
`speech_log_likelihood` is the cross-speaker acoustic floor (the ADR 0003 wall),
not word content, and it could not separate gibberish from genuine takes. This
gate instead *recognizes the words*: a lightweight local STT (faster-whisper
`base`, quarantined in the `stt` conda env) transcribes the take, and we reject
when the word-error rate against the practice transcript is too high — "we
couldn't make out the line" — before any score is computed. WER separates
cleanly (gibberish ≈ 100% vs the target; genuine takes low).

This module isolates the STT subprocess from the numpy-only scoring core:
`word_error_rate` and `decide` are pure and unit-tested;
`assess` runs the recognizer and *fails open* (returns assessed=False) on any
infrastructure error, so a broken STT never blocks scoring — only a confidently
high WER rejects.

Run standalone to calibrate the threshold on a take:
    python -m domain.content_gate path/to/take.wav "Hier soir, j'ai vu le film..."
"""
import subprocess
from dataclasses import dataclass
from pathlib import Path

from domain.text_normalize import normalize_transcript

# faster-whisper runs in the `stt` conda env (no cp314 wheel → out of the
# backend venv, per the wheel rule); assess() shells out via `conda run`.
STT_ENV = "stt"
_RUNNER = Path(__file__).resolve().parent.parent / "tools" / "stt" / "stt_runner.py"

# Max word-error rate (recognized vs practice transcript) still judged
# intelligible. Graduated on the gibberish-vs-correct calibration set (ticket 22,
# 2026-07-28, faster-whisper base): six correct takes WER 0.13–0.60, four
# gibberish takes WER 1.00–1.40 — a clean [0.60, 1.00] gap. 0.80 sits mid-gap,
# biased high so real accented learners (worse than the low-effort take) aren't
# wrongly rejected. None here = measure-and-log only (never reject).
CONTENT_GATE_MAX_WER = 0.80

# faster-whisper `base` on CPU is ~2-5s/clip; cap so a hung recognizer fails the
# gate open instead of wedging the worker.
STT_TIMEOUT_S = 120

# User-facing rejection (retryable — speaking the line clearly can fix it).
REJECT_MESSAGE = (
    "We couldn't make out the line — please record again, speaking the "
    "sentence clearly."
)


@dataclass
class ContentGateResult:
    """assessed=False means the gate could not run (STT missing/errored) and
    scoring should proceed; passed is meaningful only when assessed is True."""
    assessed: bool
    passed: bool
    wer: float | None
    detail: str


def word_error_rate(ref: str, hyp: str) -> float:
    """Word-level Levenshtein distance / reference length (pure).

    Both sides are expected pre-normalized. An empty reference is 0.0 (nothing
    to get wrong); an empty hypothesis against a real reference is 1.0 (every
    word deleted → the take said none of the line)."""
    r, h = ref.split(), hyp.split()
    if not r:
        return 0.0
    # Levenshtein over word tokens, rolling two rows.
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        curr = [i]
        for j, hw in enumerate(h, 1):
            cost = 0 if rw == hw else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1] / len(r)


def decide(wer: float | None) -> bool:
    """True = intelligible enough to score. An ungraduated threshold (None) or
    an unmeasurable WER (None) never rejects (pure)."""
    if CONTENT_GATE_MAX_WER is None or wer is None:
        return True
    return wer <= CONTENT_GATE_MAX_WER


def assess(user_wav_path, transcript: str) -> ContentGateResult:
    """Recognize the take's words and judge intelligibility by WER.

    Fails open (assessed=False) on any STT infrastructure failure — a missing
    conda env, a subprocess error, a timeout, a non-zero exit — so a broken
    recognizer degrades to "score anyway", never to "block every practice". A
    successful recognition that yields *no* words is not an infra failure: it
    means the line wasn't spoken, so WER is 1.0 and the take is rejected.
    """
    ref = normalize_transcript(transcript)
    if not ref:
        return ContentGateResult(False, True, None, "empty transcript")

    try:
        proc = subprocess.run(
            ["conda", "run", "-n", STT_ENV, "python", str(_RUNNER),
             str(user_wav_path)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=STT_TIMEOUT_S,
            # Force UTF-8 so conda-run's echo can't crash on non-ASCII output.
            env=_utf8_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ContentGateResult(False, True, None, f"STT did not run: {exc}")
    if proc.returncode != 0:
        return ContentGateResult(False, True, None, "STT recognition failed")

    hyp = normalize_transcript(proc.stdout)
    wer = word_error_rate(ref, hyp)
    passed = decide(wer)
    return ContentGateResult(True, passed, wer,
                             "intelligible" if passed else "above WER threshold")


def _utf8_env() -> dict:
    import os

    return {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Measure a take's content-gate WER.")
    parser.add_argument("wav", type=Path)
    parser.add_argument("transcript")
    args = parser.parse_args()
    result = assess(args.wav, args.transcript)
    print(f"assessed={result.assessed} passed={result.passed} "
          f"wer={result.wer} ({result.detail})")
    print(f"(reject threshold CONTENT_GATE_MAX_WER = {CONTENT_GATE_MAX_WER})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
