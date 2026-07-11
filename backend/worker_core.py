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

import dsp
import models
import storage

ALGO_VERSION = "dsp-2"


def fail_job(db, job: models.ProsodyJob, message: str):
    job.status = "FAILED"
    job.error_message = message
    db.commit()


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
        user_path = storage.get_path(user_asset.storage_key)
        if not user_path.exists():
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
        native_path = storage.get_path(native_key)
        if not native_path.exists():
            fail_job(db, job, f"Native reference audio missing at {native_key}.")
            return

        # 3. Run the pure DSP pipeline (no DB/storage inside dsp.py).
        try:
            native_feat = dsp.trim_silence(dsp.extract_features(dsp.load_mono_16k(native_path)))
            user_feat = dsp.trim_silence(dsp.extract_features(dsp.load_mono_16k(user_path)))
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

        # 5. Write feedback segments, each pointing at the archive.
        for seg in segments:
            db.add(
                models.AnalysisSegment(
                    job_id=job_id,
                    timestamp_start=seg["timestamp_start"],
                    timestamp_end=seg["timestamp_end"],
                    feedback_tag=seg["feedback_tag"],
                    explanation=seg["explanation"],
                    s3_coordinates_json_path=archive_key,
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
