"""Unit tests for align_natives' pure helpers (no conda / MFA / DB needed).

The TextGrid parser and transcript normalizer are the contract-critical pieces:
they must be correct regardless of whether MFA ran or a file was hand-authored.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent / "scripts"))

import align_natives  # noqa: E402


# A long-form Praat TextGrid as MFA emits it: two interval tiers (words, phones),
# empty boundary intervals, and one <eps> the parser must skip.
FIXTURE_TEXTGRID = '''File type = "ooTextFile"
Object class = "TextGrid"

xmin = 0
xmax = 1.2
tiers? <exists>
size = 2
item []:
    item [1]:
        class = "IntervalTier"
        name = "words"
        xmin = 0
        xmax = 1.2
        intervals: size = 4
        intervals [1]:
            xmin = 0
            xmax = 0.31
            text = ""
        intervals [2]:
            xmin = 0.31
            xmax = 0.42
            text = "on"
        intervals [3]:
            xmin = 0.42
            xmax = 0.90
            text = "les"
        intervals [4]:
            xmin = 0.90
            xmax = 1.2
            text = "<eps>"
    item [2]:
        class = "IntervalTier"
        name = "phones"
        xmin = 0
        xmax = 1.2
        intervals: size = 1
        intervals [1]:
            xmin = 0.31
            xmax = 0.42
            text = "o~"
'''


def test_parse_textgrid_words_tier_only():
    words = align_natives.parse_textgrid(FIXTURE_TEXTGRID)
    # Empty and <eps> intervals dropped; phones tier ignored.
    assert words == [("on", 0.31, 0.42), ("les", 0.42, 0.90)]


def test_parse_textgrid_empty_when_no_words():
    assert align_natives.parse_textgrid('name = "phones"\ntext = "a"\n') == []


def test_normalize_strips_punctuation_keeps_apostrophes_and_accents():
    out = align_natives.normalize_transcript("Hier soir, j'ai vu le film Napoléon !")
    assert out == "hier soir j'ai vu le film napoléon"


def test_normalize_curly_apostrophe_and_hyphen():
    assert align_natives.normalize_transcript("C’est un week-end") == "c'est un week-end"


def test_normalize_spells_out_digits():
    assert align_natives.normalize_transcript("Il a 2 chats") == "il a deux chats"
