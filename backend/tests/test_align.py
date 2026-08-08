"""Unit tests for align_natives (no conda / MFA needed — the aligner is stubbed).

The TextGrid parser and transcript normalizer are the contract-critical pieces:
they must be correct regardless of whether MFA ran or a file was hand-authored.
The last test covers main()'s database binding on a throwaway SQLite file.
"""
import json
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from infra import database, models, storage
from tools import align_natives


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


def test_main_reads_practices_from_the_configured_database(tmp_path, monkeypatch):
    """main() must go through infra.database's session factory, so it follows
    DATABASE_URL like every other entry point instead of a hardcoded dev SQLite
    path (phase3-deploy ticket 06). MFA itself is stubbed — this is about which
    database the practices come from, not about alignment.
    """
    engine = create_engine(
        f"sqlite:///{tmp_path / 'elsewhere.db'}", connect_args={"check_same_thread": False}
    )
    models.Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    db = Session()
    practice = models.Practice(
        title="Configured DB", transcript="bonjour", level="A1", length="Short",
        speed="Slow", duration=1.0, audio_url="native/1.wav",
    )
    db.add(practice)
    db.commit()
    practice_id = practice.id
    db.close()

    monkeypatch.setattr(database, "SessionLocal", Session)
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path / "storage")
    monkeypatch.setattr(
        align_natives, "align_practice",
        lambda p: {"practice_id": p.id, "source": "manual", "model": "stub", "words": []},
    )
    monkeypatch.setattr(sys, "argv", ["align_natives"])

    align_natives.main()

    written = tmp_path / "storage" / storage.alignment_key(practice_id)
    assert json.loads(written.read_text(encoding="utf-8"))["practice_id"] == practice_id
