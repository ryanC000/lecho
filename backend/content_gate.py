"""Content gate: reject unintelligible takes before prosody scoring (ticket 20).

The prosody scorer (dsp.py) measures *how* a line was said, never *what* was
said, so gibberish spoken in rhythm scores like a genuine take (2026-07-13
owner report; one gibberish take was uncatchable by prosody in principle). The
defense is a gate, not a graded axis: force-align the practice transcript
against the user's take with MFA (the same conda-quarantined aligner Task 2.1
uses offline) and reject when the acoustic fit is too poor to have said the
line — "we couldn't make out the line" — before any score is computed.

MFA forced alignment always *produces* an alignment (it forces the given words
onto the audio); the discrimination signal is the per-utterance
`speech_log_likelihood` MFA writes to `alignment_analysis.csv` when
`output_analysis` is on. A genuine take of practice 7 measured -47.9; a
gibberish take (owner records later — ticket 20) sits lower. The rejecting
threshold `CONTENT_GATE_MIN_SPEECH_LOGLIK` therefore graduates from that
gibberish-vs-genuine calibration; until then it is None (measure-and-log, never
reject) so an uncalibrated gate cannot wrongly block real learners.

This module isolates the conda/MFA subprocess from the numpy-only scoring core:
`parse_analysis_csv` and `decide` are pure and unit-tested; `assess` runs MFA
and *fails open* (returns assessed=False) on any infrastructure error, so a
broken aligner never blocks scoring — only a confident low-likelihood signal
rejects.

Run standalone to calibrate the threshold once a gibberish take exists:
    python content_gate.py path/to/take.wav "Hier soir, j'ai vu le film..."
"""
import csv
import io
import re
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import dsp

MFA_ENV = "mfa"
MFA_ACOUSTIC = "french_mfa"
MFA_DICTIONARY = "french_mfa"

# Per-utterance speech_log_likelihood below which a take is judged
# unintelligible. None = measure-and-log only (never reject): the value must be
# graduated from a gibberish-vs-genuine calibration (ticket 20, owner records
# the gibberish take), and an uncalibrated float would risk rejecting real
# learners. Genuine reference point: practice 7 emulation ~= -47.9 (2026-07-21).
CONTENT_GATE_MIN_SPEECH_LOGLIK = None

# MFA can take ~45s on a single short clip (model load dominates); cap it so a
# hung aligner fails the gate open instead of wedging the worker.
MFA_TIMEOUT_S = 180

# User-facing rejection (retryable — speaking the line clearly can fix it).
REJECT_MESSAGE = (
    "We couldn't make out the line — please record again, speaking the "
    "sentence clearly."
)

# Spelled-out French digits (MFA's dictionary has no numerals). Mirrors
# scripts/align_natives.normalize_transcript — the offline native aligner — so
# the gate normalizes user transcripts exactly as the reference clips were.
FRENCH_DIGITS = {
    "0": "zéro", "1": "un", "2": "deux", "3": "trois", "4": "quatre",
    "5": "cinq", "6": "six", "7": "sept", "8": "huit", "9": "neuf",
}


@dataclass
class ContentGateResult:
    """assessed=False means the gate could not run (MFA missing/errored) and
    scoring should proceed; passed is meaningful only when assessed is True."""
    assessed: bool
    passed: bool
    speech_log_likelihood: float | None
    detail: str


def normalize_transcript(text: str) -> str:
    """Lowercase, curly→straight apostrophes, digits spelled out, punctuation
    stripped except apostrophes/hyphens; accents preserved (the French
    dictionary keys on them). Same rules as the offline native aligner."""
    text = text.lower().replace("’", "'")
    text = re.sub(r"\d", lambda m: f" {FRENCH_DIGITS[m.group()]} ", text)
    text = "".join(ch if (ch.isalpha() or ch in " '-") else " " for ch in text)
    return " ".join(text.split())


def parse_analysis_csv(csv_text: str) -> float | None:
    """The first utterance's speech_log_likelihood from MFA's
    alignment_analysis.csv, or None if the column is absent/empty (pure)."""
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        value = row.get("speech_log_likelihood")
        if value not in (None, ""):
            return float(value)
    return None


def decide(speech_log_likelihood: float | None) -> bool:
    """True = intelligible enough to score. An ungraduated threshold (None) or
    an unmeasurable likelihood (None) never rejects (pure)."""
    if CONTENT_GATE_MIN_SPEECH_LOGLIK is None or speech_log_likelihood is None:
        return True
    return speech_log_likelihood >= CONTENT_GATE_MIN_SPEECH_LOGLIK


def _write_wav_16k(samples: np.ndarray, path: Path) -> None:
    """Write mono 16 kHz 16-bit PCM — the clean input MFA aligns reliably."""
    pcm = np.clip(samples, -1.0, 1.0)
    pcm = (pcm * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(dsp.TARGET_SR)
        wf.writeframes(pcm.tobytes())


def assess(user_wav_path, transcript: str) -> ContentGateResult:
    """Force-align `transcript` against the take and judge intelligibility.

    Fails open (assessed=False) on any MFA infrastructure failure — a missing
    conda env, a subprocess error, a timeout, no analysis CSV — so a broken
    aligner degrades to "score anyway", never to "block every practice".
    """
    snd = dsp.load_mono_16k(user_wav_path)
    normalized = normalize_transcript(transcript)
    if not normalized:
        return ContentGateResult(False, True, None, "empty transcript")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        corpus, out = tmp / "corpus", tmp / "out"
        corpus.mkdir()
        _write_wav_16k(snd.values[0], corpus / "utt.wav")
        (corpus / "utt.txt").write_text(normalized, encoding="utf-8")
        # output_analysis has no CLI flag; enable it through a config file
        # (MFA merges arbitrary yaml keys into the aligner constructor).
        cfg = tmp / "cfg.yaml"
        cfg.write_text("output_analysis: true\n", encoding="utf-8")

        try:
            proc = subprocess.run(
                ["conda", "run", "-n", MFA_ENV, "mfa", "align",
                 "--config_path", str(cfg), "--single_speaker", "--clean",
                 str(corpus), MFA_DICTIONARY, MFA_ACOUSTIC, str(out)],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=MFA_TIMEOUT_S,
                # Force UTF-8 so conda-run's echo can't crash on non-ASCII.
                env=_utf8_env(),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return ContentGateResult(False, True, None, f"MFA did not run: {exc}")
        if proc.returncode != 0:
            return ContentGateResult(False, True, None, "MFA alignment failed")

        analysis = out / "alignment_analysis.csv"
        if not analysis.exists():
            return ContentGateResult(False, True, None, "no analysis output")
        likelihood = parse_analysis_csv(analysis.read_text(encoding="utf-8"))

    if likelihood is None:
        return ContentGateResult(False, True, None, "no likelihood in analysis")
    passed = decide(likelihood)
    return ContentGateResult(True, passed, likelihood,
                             "intelligible" if passed else "below threshold")


def _utf8_env() -> dict:
    import os

    return {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Measure a take's MFA content-gate likelihood.")
    parser.add_argument("wav", type=Path)
    parser.add_argument("transcript")
    args = parser.parse_args()
    result = assess(args.wav, args.transcript)
    print(f"assessed={result.assessed} passed={result.passed} "
          f"speech_log_likelihood={result.speech_log_likelihood} ({result.detail})")
    print(f"(reject threshold CONTENT_GATE_MIN_SPEECH_LOGLIK = {CONTENT_GATE_MIN_SPEECH_LOGLIK})")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
