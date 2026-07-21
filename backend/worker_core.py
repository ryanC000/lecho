"""Job-scoring worker core (orchestrator).

Real DSP runs here (worker_plan.md §2 keeps orchestration in the worker; the
pure algorithm lives in dsp.py). `run` opens the user recording and the
practice's native reference, runs the F0/RMS/DTW pipeline, and writes the
score + feedback segments + coordinate archive.

This module is the transport-independent seam: FastAPI's BackgroundTasks calls
`run` in-process today, and the Phase 3 SQS entrypoint imports the same
function — a transport swap, not a rewrite. The DB session factory is a
parameter (not created here) so tests and future transports can substitute it.
Importing this module has no side effects.
"""
import json

import content_gate
import dsp
import models
import storage

ALGO_VERSION = "dsp-3"

# User-facing failure for a detected bleed (master-plan Task 3.2). Retryable —
# the fix is on the user's side, so re-recording can help.
BLEED_MESSAGE = (
    "It sounds like the native audio was picked up by your microphone. "
    "Please use headphones for shadow takes, or switch to Solo mode."
)


def fail_job(db, job: models.ProsodyJob, message: str):
    job.status = "FAILED"
    job.error_message = message
    db.commit()


def load_alignment_words(practice_id):
    """The practice's alignment words (list of {word, start, end}), or [] when no
    alignment JSON exists (unaligned practice — the common case today)."""
    if practice_id is None:
        return []
    key = storage.alignment_key(practice_id)
    if not storage.exists(key):
        return []
    return json.loads(storage.read_text(key)).get("words", [])


def overlapping_words(words, seg_start, seg_end):
    """Words whose [start, end) interval overlaps [seg_start, seg_end), in order
    (PRD 8.4 word-mapping rule: word.start < seg.end and word.end > seg.start)."""
    return [w["word"] for w in words if w["start"] < seg_end and w["end"] > seg_start]


def run(job_id: str, session_factory):
    db = session_factory()
    try:
        job = db.query(models.ProsodyJob).filter(models.ProsodyJob.id == job_id).first()
        if not job:
            return

        # 1. Resolve the user recording (persisted at ingest).
        user_asset = (
            db.query(models.AudioAsset)
            .filter(models.AudioAsset.job_id == job_id, models.AudioAsset.role == "USER_RECORDING")
            .first()
        )
        if not user_asset:
            fail_job(db, job, "No user recording asset found for job.")
            return
        if not storage.exists(user_asset.storage_key):
            fail_job(db, job, f"Stored user audio missing at {user_asset.storage_key}.")
            return

        # 2. Resolve the native reference. Linked via Practice.audio_url as a
        #    storage key (worker_plan.md §0). Until native clips are sourced,
        #    this is null for every seeded practice — fail loudly and clearly
        #    (§7: "native reference missing"), which is the expected state now.
        native_key = job.practice.audio_url if job.practice else None
        if not native_key:
            fail_job(db, job, "This practice isn't ready for scoring yet — its reference audio hasn't been added.")
            return
        if not storage.exists(native_key):
            fail_job(db, job, f"Native reference audio missing at {native_key}.")
            return

        # 3. Run the pure DSP pipeline (no DB/storage inside dsp.py). get_path
        #    materializes each clip locally for the DSP loader (S3: temp file).
        try:
            native_path = storage.get_path(native_key)
            user_path = storage.get_path(user_asset.storage_key)
            # Shadow takes: hard bleed gate on the raw signals BEFORE any
            # feature extraction — a bled take must never be scored. (The
            # extra decode for the gate is negligible next to the pipeline.)
            if job.mode == "shadow":
                peak_ncc = dsp.detect_bleed(
                    dsp.load_mono_16k(native_path).values[0],
                    dsp.load_mono_16k(user_path).values[0],
                    dsp.TARGET_SR,
                )
                if peak_ncc > dsp.NCC_BLEED_THRESHOLD:
                    raise dsp.BleedDetectedError(BLEED_MESSAGE)
            # Content gate (ticket 20): force-align the practice transcript
            # against the take and reject unintelligible ones before scoring —
            # prosody alone can't tell gibberish from a genuine take. Fails
            # open (a broken MFA env scores anyway); only a confident
            # low-likelihood signal rejects.
            transcript = job.practice.transcript if job.practice else None
            if transcript:
                gate = content_gate.assess(user_path, transcript)
                if gate.assessed and not gate.passed:
                    fail_job(db, job, content_gate.REJECT_MESSAGE)
                    return
            native_feat = dsp.features_for(native_path)
            user_feat = dsp.features_for(user_path)
            aligned = dsp.align(native_feat, user_feat)
            overall, pitch_score, timing_score, energy_score = dsp.score(aligned)
            segments = dsp.make_segments(aligned)
            archive = dsp.build_archive(aligned)
        except dsp.DspError as exc:
            # Expected, user-facing failures (no speech, length ratio, etc.).
            fail_job(db, job, str(exc))
            return

        # 4. Persist the coordinate archive behind the storage seam.
        archive_key = storage.save_text(json.dumps(archive), storage.analysis_key(job_id))

        # 4b. Word-anchor the segments (PRD 8.4): if this practice has an
        #     alignment, attach to each segment the words whose intervals
        #     overlap it. No alignment / no overlap → words stays null.
        alignment_words = load_alignment_words(job.practice_id)

        # 5. Write feedback segments, each pointing at the archive.
        for seg in segments:
            words = overlapping_words(alignment_words, seg["timestamp_start"], seg["timestamp_end"])
            db.add(
                models.AnalysisSegment(
                    job_id=job_id,
                    timestamp_start=seg["timestamp_start"],
                    timestamp_end=seg["timestamp_end"],
                    feedback_tag=seg["feedback_tag"],
                    explanation=seg["explanation"],
                    coordinates_key=archive_key,
                    words=json.dumps(words) if words else None,
                )
            )

        # 6. Finalize the job.
        job.status = "SUCCESS"
        job.overall_match_score = round(overall, 1)
        job.pitch_score = round(pitch_score, 1)
        job.timing_score = round(timing_score, 1)
        job.energy_score = round(energy_score, 1)
        job.algo_version = ALGO_VERSION
        db.commit()
    except Exception as exc:  # never let a background failure vanish silently
        db.rollback()
        job = db.query(models.ProsodyJob).filter(models.ProsodyJob.id == job_id).first()
        if job:
            job.status = "FAILED"
            job.error_message = str(exc)
            db.commit()
    finally:
        db.close()
