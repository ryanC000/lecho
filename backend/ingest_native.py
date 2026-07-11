"""Ingest a native reference clip for a Practice (master_implementation_plan.md appendix, Phase 1R).

Converts any Praat-readable audio to canonical 16kHz mono PCM WAV, sanity-checks
it with the real DSP pipeline (voiced speech must survive silence trimming),
stores it through the storage seam, and links it via Practice.audio_url.

Usage (from backend/, with the venv python):
    # Attach to an existing practice:
    python ingest_native.py ../native_audio/clip.wav --practice-id 3

    # Create a new practice for the clip:
    python ingest_native.py ../native_audio/clip.wav --title "Film Review Intro" \
        --transcript "Hier soir, j'ai vu..." --level B2 [--speed Normal] [--notes "..."]

The practice's `duration` is always updated to the clip's real duration, since
both duration gates and the recorder UI key off it.
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

import audio_meta
import database
import dsp
import storage
from models import AudioAsset, Practice

# A native clip must leave room for the user gates: recordings are bounded by
# ±20% of the native duration AND the absolute 2-15s window (PRD FR-1), so the
# native itself must sit in [2/0.8, 15/1.2].
MIN_NATIVE_S = 2.5
MAX_NATIVE_S = 12.5


def derive_length(duration_s: float) -> str:
    if duration_s < 5:
        return "Short"
    if duration_s <= 8:
        return "Medium"
    return "Long"


def main():
    parser = argparse.ArgumentParser(description="Ingest a native reference clip.")
    parser.add_argument("audio", type=Path, help="Path to the source audio file")
    parser.add_argument("--practice-id", type=int, help="Attach to this existing practice")
    parser.add_argument("--title", help="Create a new practice with this title")
    parser.add_argument("--transcript", help="Transcript for the new practice")
    parser.add_argument("--level", default="B2", help="CEFR level for the new practice")
    parser.add_argument("--speed", default="Normal", help="Speed label for the new practice")
    parser.add_argument("--notes", default=None, help="Linguistic notes for the new practice")
    parser.add_argument("--force", action="store_true",
                        help="Ingest even if duration is outside the recommended bounds")
    args = parser.parse_args()

    if not args.audio.exists():
        sys.exit(f"Audio file not found: {args.audio}")
    if bool(args.practice_id) == bool(args.title):
        sys.exit("Provide exactly one of --practice-id or --title (with --transcript).")
    if args.title and not args.transcript:
        sys.exit("--title requires --transcript.")

    # 1. Convert to canonical 16kHz mono PCM WAV (accepts anything Praat reads).
    snd = dsp.load_mono_16k(args.audio)
    duration = snd.get_total_duration()

    if not (MIN_NATIVE_S <= duration <= MAX_NATIVE_S) and not args.force:
        sys.exit(
            f"Clip is {duration:.2f}s; native clips must be {MIN_NATIVE_S}-{MAX_NATIVE_S}s so user\n"
            f"recordings (±20% of native, absolute 2-15s) stay inside the PRD FR-1 gates.\n"
            f"Split the clip at a sentence boundary, or re-run with --force."
        )

    # 2. Sanity-check with the real pipeline: the clip must contain trimmable,
    #    voiced speech, or every job against it would fail in the worker.
    try:
        feat = dsp.trim_silence(dsp.extract_features(snd))
    except dsp.NoSpeechDetectedError as exc:
        sys.exit(f"Clip failed the speech check ({exc}) — is this the right file?")
    voiced_pct = 100.0 * feat.voiced.mean()

    db = database.SessionLocal()
    try:
        # 3. Resolve or create the practice.
        if args.practice_id:
            practice = db.query(Practice).filter(Practice.id == args.practice_id).first()
            if not practice:
                sys.exit(f"No practice with id {args.practice_id}.")
        else:
            practice = Practice(
                title=args.title,
                transcript=args.transcript,
                level=args.level,
                length=derive_length(duration),
                speed=args.speed,
                duration=duration,
                notes=args.notes,
            )
            db.add(practice)
            db.flush()  # assign practice.id for the storage key

        # 4. Store the converted WAV through the seam and link it.
        key = f"native/{practice.id}.wav"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_wav = Path(tmp) / "converted.wav"
            snd.save(str(tmp_wav), "WAV")
            with open(tmp_wav, "rb") as f:
                result = storage.save_upload(f, key)
            meta = audio_meta.extract_metadata(storage.open_read(key))

        db.add(AudioAsset(
            job_id=None,
            owner_user_id=None,
            role="NATIVE_REFERENCE",
            storage_key=result.key,
            storage_backend=result.backend,
            size_bytes=result.size_bytes,
            sha256=result.sha256,
            duration_seconds=meta.duration_seconds,
            sample_rate=meta.sample_rate,
            channels=meta.channels,
            codec=meta.codec,
            expires_at=None,  # native references don't expire
        ))
        practice.audio_url = key
        practice.duration = round(meta.duration_seconds, 2)
        db.commit()

        print(f"Ingested '{args.audio.name}' -> practice {practice.id} ('{practice.title}')")
        print(f"  key={key}  duration={meta.duration_seconds:.2f}s  "
              f"sr={meta.sample_rate}  voiced={voiced_pct:.0f}% of trimmed frames")
    finally:
        db.close()


if __name__ == "__main__":
    main()
