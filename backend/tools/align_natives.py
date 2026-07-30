"""Produce word-level alignment JSON for ingested native clips (PRD 8.4, Task 2.1).

For every practice that has a native reference clip, this shells out to Montreal
Forced Aligner (quarantined in its own `mfa` conda env — see tools/README_MFA.md)
and writes `alignments/{practice_id}.json` through the storage seam. Downstream
consumers (worker word-mapper, karaoke, pitch-chart labels) are coupled to the JSON
contract, not to MFA, so a hand-authored file (`"source": "manual"`) is a drop-in
substitute when MFA misbehaves on a short clip.

Usage (from backend/, with the venv python — this script imports the backend but
does NOT need the mfa env; it calls `conda run -n mfa` itself):
    python -m tools.align_natives                 # align every practice with audio
    python -m tools.align_natives --practice-id 7 # align just one

Alignment JSON contract (fixed — hand-authored files must be drop-in identical;
times are seconds on the native clip's timeline):
    {"practice_id": 7, "source": "mfa", "model": "french_mfa",
     "words": [{"word": "on", "start": 0.31, "end": 0.42}]}
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from domain.text_normalize import normalize_transcript
from infra import storage
from infra.models import Practice

MFA_ENV = "mfa"
MFA_ACOUSTIC = "french_mfa"
MFA_DICTIONARY = "french_mfa"

def parse_textgrid(content: str):
    """Extract (word, start, end) tuples from the 'words' tier of a long-form
    Praat TextGrid (MFA's output format). Empty and <eps> intervals are skipped.
    """
    words = []
    in_words_tier = False
    xmin = xmax = None
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("name ="):
            in_words_tier = line.split("=", 1)[1].strip().strip('"') == "words"
            continue
        if not in_words_tier:
            continue
        if line.startswith("xmin ="):
            xmin = float(line.split("=", 1)[1])
        elif line.startswith("xmax ="):
            xmax = float(line.split("=", 1)[1])
        elif line.startswith("text ="):
            word = line.split("=", 1)[1].strip().strip('"').strip()
            if word and word.lower() != "<eps>" and xmin is not None and xmax is not None:
                words.append((word, xmin, xmax))
            xmin = xmax = None
    return words


def align_practice(practice: Practice) -> dict:
    """Run MFA on one practice's native clip and return the contract dict."""
    clip_path = storage.get_path(practice.audio_url)
    if not clip_path.exists():
        raise FileNotFoundError(f"Native clip missing at {practice.audio_url}")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        corpus, out = tmp / "corpus", tmp / "out"
        corpus.mkdir()
        shutil.copyfile(clip_path, corpus / f"{practice.id}.wav")
        (corpus / f"{practice.id}.txt").write_text(
            normalize_transcript(practice.transcript), encoding="utf-8"
        )

        subprocess.run(
            ["conda", "run", "-n", MFA_ENV, "mfa", "align",
             str(corpus), MFA_DICTIONARY, MFA_ACOUSTIC, str(out), "--clean"],
            check=True,
        )

        textgrid = out / f"{practice.id}.TextGrid"
        if not textgrid.exists():
            raise RuntimeError(f"MFA produced no TextGrid for practice {practice.id}")
        parsed = parse_textgrid(textgrid.read_text(encoding="utf-8"))

    words = [
        {"word": w, "start": round(start, 3), "end": round(end, 3)}
        for w, start, end in sorted(parsed, key=lambda t: t[1])
    ]
    return {"practice_id": practice.id, "source": "mfa",
            "model": MFA_ACOUSTIC, "words": words}


def main():
    parser = argparse.ArgumentParser(description="Word-align native reference clips with MFA.")
    parser.add_argument("--practice-id", type=int, help="Align only this practice (default: all with audio).")
    args = parser.parse_args()

    # Bind to the backend's dev DB by absolute path so the script works from any
    # cwd (database.py resolves sqlite:///./lecho.db relative to cwd at import).
    engine = create_engine(
        f"sqlite:///{BACKEND_DIR / 'lecho.db'}", connect_args={"check_same_thread": False}
    )
    db = sessionmaker(bind=engine)()
    try:
        query = db.query(Practice).filter(Practice.audio_url.isnot(None))
        if args.practice_id:
            query = query.filter(Practice.id == args.practice_id)
        practices = query.all()
        if not practices:
            sys.exit("No practices with a native clip to align.")

        for practice in practices:
            print(f"Aligning practice {practice.id} ('{practice.title}')...")
            payload = align_practice(practice)
            key = storage.save_text(
                json.dumps(payload, ensure_ascii=False), storage.alignment_key(practice.id)
            )
            print(f"  wrote {key}  ({len(payload['words'])} words)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
