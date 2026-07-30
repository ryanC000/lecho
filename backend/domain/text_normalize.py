"""French transcript normalization, shared by the two places that must agree.

The offline aligner (tools/align_natives.py) normalizes a practice transcript
before handing it to MFA; the content gate (domain/content_gate.py) normalizes
both the transcript and the ASR hypothesis before measuring word-error rate.
If these two ever diverged, the WER comparison would count normalization
differences as pronunciation errors — so there is exactly one implementation.
"""
import re

# Digits are not in MFA's pronunciation dictionary and the ASR emits words, so
# spell them out. French multi-digit numbers are genuinely irregular; spelling
# digit-by-digit is a deterministic, dictionary-safe fallback (no current
# transcript has digits).
FRENCH_DIGITS = {
    "0": "zéro", "1": "un", "2": "deux", "3": "trois", "4": "quatre",
    "5": "cinq", "6": "six", "7": "sept", "8": "huit", "9": "neuf",
}


def normalize_transcript(text: str) -> str:
    """Lowercase, curly→straight apostrophes, digits spelled out, punctuation
    stripped except apostrophes/hyphens. Accents are preserved — the French
    dictionary keys on them.
    """
    text = text.lower().replace("’", "'")
    text = re.sub(r"\d", lambda m: f" {FRENCH_DIGITS[m.group()]} ", text)
    text = "".join(ch if (ch.isalpha() or ch in " '-") else " " for ch in text)
    return " ".join(text.split())
