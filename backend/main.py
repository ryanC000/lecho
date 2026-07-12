from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
import uuid

import models, schemas, auth, clip_ingest, database, storage, migrations, worker_core
from database import engine

from typing import List

# --- Ingestion constraints (PRD FR-1) ---
MIN_DURATION_S = 2.0
MAX_DURATION_S = 15.0
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB — a 15s mono 16-bit WAV is well under this
RETENTION_DAYS = 30                   # PRD Section 4 storage lifecycle

# Solo-mode relative duration gate: generous (±50%) because an early/late
# stop press just pads the take with silence, which trim_silence strips
# before scoring and the 3:1 trimmed length-ratio abort still backstops.
# This only rejects takes that can't plausibly be the same utterance.
SOLO_TOLERANCE_FRAC = 0.5

# Shadow-mode duration gate (PRD 8.7): a shadow take runs the native clip's
# length plus a fixed tail, so its expected duration is native + SHADOW_TAIL_S
# within ±SHADOW_TOLERANCE_S (placeholder until calibration, Task 1.2).
SHADOW_TAIL_S = 1.0
SHADOW_TOLERANCE_S = 0.5

ALLOWED_JOB_MODES = {"solo", "shadow"}


def mode_duration_error(mode: str, duration: float, native_duration: float):
    """Per-mode relative duration gate. Returns the user-facing rejection
    message, or None if the duration passes. Applied twice per job: to the
    client-reported duration as a fast-fail, then to the server-derived
    duration as the authoritative check. The absolute 2-15s gate is separate
    (clip_ingest) and identical for both modes.
    """
    if mode == "shadow":
        expected = native_duration + SHADOW_TAIL_S
        if abs(duration - expected) > SHADOW_TOLERANCE_S:
            return (
                f"Shadow recording duration deviates too much from the expected "
                f"length ({expected:.1f}s = native + {SHADOW_TAIL_S:.0f}s tail)."
            )
        return None
    lo = native_duration * (1 - SOLO_TOLERANCE_FRAC)
    hi = native_duration * (1 + SOLO_TOLERANCE_FRAC)
    if duration < lo or duration > hi:
        return "Recording duration deviates too much from native reference."
    return None

# Creates all the API endpoints

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables (for local MVP), then apply idempotent column additions.
    # Runs at startup, not import — importing this module must not touch the DB.
    models.Base.metadata.create_all(bind=engine)
    migrations.run(engine)
    yield

app = FastAPI(title="L'Écho API", lifespan=lifespan)

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
    if not storage.exists(practice.audio_url):
        raise HTTPException(status_code=404, detail="Reference audio file is missing from storage.")
    return storage.audio_response(practice.audio_url)

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

@app.post("/jobs", response_model=schemas.JobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_job(
    background_tasks: BackgroundTasks,
    practice_id: int = Form(...),
    user_audio_duration: float = Form(...),
    mode: str = Form("solo"),
    file: UploadFile = File(...),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    if mode not in ALLOWED_JOB_MODES:
        raise HTTPException(status_code=400, detail="mode must be 'solo' or 'shadow'.")

    # Verify the native sample exists
    sample = db.query(models.Practice).filter(models.Practice.id == practice_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Practice not found")

    # Per-mode relative duration gate on the client-reported duration
    # (fast-fail; re-checked on the server-derived duration below).
    gate_error = mode_duration_error(mode, user_audio_duration, sample.duration)
    if gate_error:
        raise HTTPException(status_code=400, detail=gate_error)

    # Create the job first so we can attach the asset to it.
    new_job = models.ProsodyJob(user_id=current_user.id, practice_id=sample.id, mode=mode)
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

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
            expires_at=datetime.utcnow() + timedelta(days=RETENTION_DAYS),
            max_bytes=MAX_UPLOAD_BYTES,
            duration_bounds=(MIN_DURATION_S, MAX_DURATION_S),
        )
    except clip_ingest.ClipRejectedError as exc:
        worker_core.fail_job(db, new_job, exc.log_message)
        raise HTTPException(status_code=400, detail=exc.detail)

    # Authoritative per-mode gate on the duration derived from the real bytes
    # (the client-reported value above is not trusted).
    gate_error = mode_duration_error(mode, asset.duration_seconds, sample.duration)
    if gate_error:
        storage.delete(asset.storage_key)
        worker_core.fail_job(db, new_job, gate_error)
        raise HTTPException(status_code=400, detail=gate_error)
    db.add(asset)
    db.commit()

    # Dispatch to background worker (Phase 3 replaces this with SQS + a container).
    background_tasks.add_task(worker_core.run, new_job.id, database.SessionLocal)

    return {"id": new_job.id, "status": new_job.status}


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
        "mode": job.mode,
        "score": job.overall_match_score,
        "pitch_score": job.pitch_score,
        "timing_score": job.timing_score,
        "energy_score": job.energy_score,
        "error_message": job.error_message,
        "practice_id": job.practice_id,
        "transcript": job.practice.transcript if job.practice else None,
        "segments": job.segments,
        "retryable": retryable,
    }
