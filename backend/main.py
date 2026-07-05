from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
import json
import uuid

import models, schemas, auth, database, storage, audio_meta, dsp
from database import engine

from typing import List

# --- Ingestion constraints (PRD FR-1) ---
MIN_DURATION_S = 2.0
MAX_DURATION_S = 15.0
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB — a 15s mono 16-bit WAV is well under this
RETENTION_DAYS = 30                   # PRD Section 4 storage lifecycle

# Creates all the API endpoints 

# Create tables (for local MVP)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="L'Écho API")

# Configure CORS for React frontend (Vite default port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/practices", response_model=List[schemas.Practice])
def get_practices(db: Session = Depends(database.get_db)):
    practices = db.query(models.Practice).all()
    return practices

@app.get("/practices/{practice_id}", response_model=schemas.Practice)
def get_practice(practice_id: int, db: Session = Depends(database.get_db)):
    practice = db.query(models.Practice).filter(models.Practice.id == practice_id).first()
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")
    return practice

@app.get("/practices/{practice_id}/audio")
def get_practice_audio(practice_id: int, db: Session = Depends(database.get_db)):
    """Stream a practice's native reference clip (ingested via ingest_native.py).

    Unauthenticated like the rest of the practice catalog — native clips are
    shared content, unlike user recordings.
    """
    practice = db.query(models.Practice).filter(models.Practice.id == practice_id).first()
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")
    if not practice.audio_url:
        raise HTTPException(status_code=404, detail="This practice has no reference audio yet.")
    path = storage.get_path(practice.audio_url)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Reference audio file is missing from storage.")
    return FileResponse(path, media_type="audio/wav")

@app.post("/auth/register", response_model=schemas.UserResponse)
def register(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(email=user.email, password_hash=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/auth/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# --- Worker Task (orchestrator) ---
# Real DSP now runs here (worker_plan.md §2 keeps orchestration in the worker
# task; the pure algorithm lives in dsp.py). This opens both the user recording
# and the practice's native reference, runs the F0/RMS/DTW pipeline, and writes
# the score + feedback segments + coordinate archive. Its only input is job_id
# (everything else is fetched from the DB), so the Phase 3 SQS split is a
# transport swap, not a rewrite.
ALGO_VERSION = "dsp-2"


def worker_task(job_id: str):
    db = database.SessionLocal()
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
            _fail_job(db, job, "No user recording asset found for job.")
            return
        user_path = storage.get_path(user_asset.storage_key)
        if not user_path.exists():
            _fail_job(db, job, f"Stored user audio missing at {user_asset.storage_key}.")
            return

        # 2. Resolve the native reference. Linked via Practice.audio_url as a
        #    storage key (worker_plan.md §0). Until native clips are sourced,
        #    this is null for every seeded practice — fail loudly and clearly
        #    (§7: "native reference missing"), which is the expected state now.
        native_key = job.practice.audio_url if job.practice else None
        if not native_key:
            _fail_job(db, job, "This practice isn't ready for scoring yet — its reference audio hasn't been added.")
            return
        native_path = storage.get_path(native_key)
        if not native_path.exists():
            _fail_job(db, job, f"Native reference audio missing at {native_key}.")
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
            _fail_job(db, job, str(exc))
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


@app.post("/jobs", response_model=schemas.JobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_job(
    background_tasks: BackgroundTasks,
    practice_id: int = Form(...),
    user_audio_duration: float = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    # Verify the native sample exists
    sample = db.query(models.Practice).filter(models.Practice.id == practice_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Practice not found")

    # Relative duration gate (±20% of native), matching the client-side check.
    lower_bound = sample.duration * 0.8
    upper_bound = sample.duration * 1.2
    if user_audio_duration < lower_bound or user_audio_duration > upper_bound:
        raise HTTPException(status_code=400, detail="Recording duration deviates too much from native reference.")

    # Create the job first so we can attach the asset to it.
    new_job = models.ProsodyJob(user_id=current_user.id, practice_id=sample.id)
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    # Persist the upload through the storage seam.
    asset_id = str(uuid.uuid4())
    key = storage.upload_key(asset_id)
    result = storage.save_upload(file.file, key)

    # Guard size (after write we know the real byte count).
    if result.size_bytes == 0 or result.size_bytes > MAX_UPLOAD_BYTES:
        storage.delete(key)
        _fail_job(db, new_job, "Uploaded audio is empty or exceeds the size limit.")
        raise HTTPException(status_code=400, detail="Uploaded audio is empty or too large.")

    # Extract authoritative metadata from the real bytes (not client-trusted).
    try:
        meta = audio_meta.extract_metadata(storage.get_path(key))
    except audio_meta.InvalidAudioError as exc:
        storage.delete(key)
        _fail_job(db, new_job, f"Invalid audio: {exc}")
        raise HTTPException(status_code=400, detail="Uploaded file is not a readable WAV recording.")

    # Absolute duration gate (PRD FR-1: 2s–15s), enforced on the derived duration.
    if meta.duration_seconds < MIN_DURATION_S or meta.duration_seconds > MAX_DURATION_S:
        storage.delete(key)
        _fail_job(db, new_job, f"Duration {meta.duration_seconds:.2f}s outside {MIN_DURATION_S}-{MAX_DURATION_S}s.")
        raise HTTPException(status_code=400, detail="Recording must be between 2 and 15 seconds long.")

    asset = models.AudioAsset(
        id=asset_id,
        job_id=new_job.id,
        owner_user_id=current_user.id,
        role="USER_RECORDING",
        storage_key=result.key,
        storage_backend=result.backend,
        size_bytes=result.size_bytes,
        sha256=result.sha256,
        duration_seconds=meta.duration_seconds,
        sample_rate=meta.sample_rate,
        channels=meta.channels,
        codec=meta.codec,
        client_reported_duration=user_audio_duration,
        expires_at=datetime.utcnow() + timedelta(days=RETENTION_DAYS),
    )
    db.add(asset)
    db.commit()

    # Dispatch to background worker (Phase 3 replaces this with SQS + a container).
    background_tasks.add_task(worker_task, new_job.id)

    return {"id": new_job.id, "status": new_job.status}


def _fail_job(db: Session, job: models.ProsodyJob, message: str):
    job.status = "FAILED"
    job.error_message = message
    db.commit()


@app.get("/jobs/{job_id}", response_model=schemas.JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    job = db.query(models.ProsodyJob).filter(models.ProsodyJob.id == job_id, models.ProsodyJob.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # A failed job is retryable unless it failed because the practice has no
    # native reference yet — re-recording can't fix that (worker_plan.md §7).
    retryable = None
    if job.status == "FAILED":
        retryable = bool(job.practice and job.practice.audio_url)
    return {
        "id": job.id,
        "status": job.status,
        "score": job.overall_match_score,
        "error_message": job.error_message,
        "practice_id": job.practice_id,
        "transcript": job.practice.transcript if job.practice else None,
        "segments": job.segments,
        "retryable": retryable,
    }
