"""Scoring-job routes: submit a take, poll its status, fetch its coordinates.

Gate policy lives in domain/job_gates.py and payload assembly in
api/serializers.py, so these handlers stay orchestration only.
"""
import logging
import uuid
from datetime import datetime, timedelta

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import Response
from sqlalchemy.orm import Session

from api import schemas, security
from api.serializers import job_list_item, job_status_payload
from domain import job_gates
from infra import database, models, queue, storage
from ingest import clip_ingest
from worker import core as worker_core

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/jobs", response_model=schemas.JobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_job(
    background_tasks: BackgroundTasks,
    practice_id: int = Form(...),
    user_audio_duration: float = Form(...),
    mode: str = Form("solo"),
    file: UploadFile = File(...),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    if mode not in job_gates.ALLOWED_JOB_MODES:
        raise HTTPException(status_code=400, detail="mode must be 'solo' or 'shadow'.")

    # Verify the native sample exists
    sample = db.query(models.Practice).filter(models.Practice.id == practice_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Practice not found")

    # Per-mode relative duration gate on the client-reported duration
    # (fast-fail; re-checked on the server-derived duration below).
    gate_error = job_gates.mode_duration_error(mode, user_audio_duration, sample.duration)
    if gate_error:
        raise HTTPException(status_code=400, detail=gate_error)

    # Create the job first so we can attach the asset to it.
    new_job = models.ProsodyJob(user_id=current_user.id, practice_id=sample.id, mode=mode)
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    # client_duration, not duration: the authoritative one is derived below.
    logger.info(
        "job=%s created status=%s practice=%s mode=%s client_duration=%.2fs user=%s",
        new_job.id, new_job.status, sample.id, mode, user_audio_duration, current_user.id,
    )

    # Persist the upload through the clip-ingestion module (store, derive
    # authoritative metadata, size + absolute duration gates, build the asset).
    asset_id = str(uuid.uuid4())
    try:
        asset = clip_ingest.ingest_clip(
            file.file,
            storage.upload_key(asset_id),
            role="USER_RECORDING",
            asset_id=asset_id,
            job_id=new_job.id,
            owner_user_id=current_user.id,
            client_reported_duration=user_audio_duration,
            expires_at=datetime.utcnow() + timedelta(days=job_gates.RETENTION_DAYS),
            max_bytes=job_gates.MAX_UPLOAD_BYTES,
            duration_bounds=(job_gates.MIN_DURATION_S, job_gates.MAX_DURATION_S),
        )
    except clip_ingest.ClipRejectedError as exc:
        logger.warning("job=%s upload rejected: %s", new_job.id, exc.log_message)
        worker_core.fail_job(db, new_job, exc.log_message)
        raise HTTPException(status_code=400, detail=exc.detail)

    # Authoritative per-mode gate on the duration derived from the real bytes
    # (the client-reported value above is not trusted).
    gate_error = job_gates.mode_duration_error(mode, asset.duration_seconds, sample.duration)
    if gate_error:
        logger.warning(
            "job=%s upload rejected (duration=%.2fs): %s",
            new_job.id, asset.duration_seconds, gate_error,
        )
        storage.delete(asset.storage_key)
        worker_core.fail_job(db, new_job, gate_error)
        raise HTTPException(status_code=400, detail=gate_error)
    db.add(asset)
    db.commit()

    # Dispatch behind the queue seam: published to SQS for a separate worker
    # container, or run in-process after the response under INLINE.
    queue.publish(
        new_job.id,
        lambda: background_tasks.add_task(worker_core.run, new_job.id, database.SessionLocal),
    )

    return {"id": new_job.id, "status": new_job.status}


@router.get("/jobs", response_model=schemas.JobListResponse)
def list_jobs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    """The caller's job history, newest first — backs the history page."""
    query = db.query(models.ProsodyJob).filter(models.ProsodyJob.user_id == current_user.id)
    # id breaks ties: SQLite's CURRENT_TIMESTAMP is second-granular, and an
    # unstable sort lets paging repeat or skip same-second takes.
    jobs = (
        query.order_by(models.ProsodyJob.created_at.desc(), models.ProsodyJob.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    # One lookup for the page's takes: a job rejected before storage has no
    # asset, so its duration stays absent.
    durations = dict(
        db.query(models.AudioAsset.job_id, models.AudioAsset.duration_seconds)
        .filter(
            models.AudioAsset.job_id.in_([job.id for job in jobs]),
            models.AudioAsset.role == "USER_RECORDING",
        )
        .all()
    )
    return {
        "jobs": [job_list_item(job, durations.get(job.id)) for job in jobs],
        "total": query.count(),
    }


@router.get("/jobs/{job_id}", response_model=schemas.JobStatusResponse)
def get_job_status(
    job_id: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    job = (
        db.query(models.ProsodyJob)
        .filter(models.ProsodyJob.id == job_id, models.ProsodyJob.user_id == current_user.id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_status_payload(job)


@router.get("/jobs/{job_id}/coordinates")
def get_job_coordinates(
    job_id: str,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(security.get_current_user),
):
    """Serve a SUCCESS job's coordinate archive verbatim for the pitch visualizer.

    Owner-scoped exactly like get_job_status (404 for another user's job). The
    archive is the fixed worker contract (times, native/user F0 + semitone + RMS,
    voiced masks) and is returned as-is — no recomputation, no key reshaping.
    """
    job = (
        db.query(models.ProsodyJob)
        .filter(models.ProsodyJob.id == job_id, models.ProsodyJob.user_id == current_user.id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "SUCCESS":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Coordinates are only available for a completed job.",
        )

    # Located by the worker's deterministic key, not via AnalysisSegment: a
    # SUCCESS job with no flagged segments writes no segment rows but still has
    # its archive on disk.
    key = storage.analysis_key(job_id)
    if not storage.exists(key):
        raise HTTPException(status_code=404, detail="Coordinate archive not found for this job.")
    return Response(content=storage.read_text(key), media_type="application/json")
