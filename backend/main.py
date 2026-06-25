from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
import time

import models, schemas, auth, database
from database import engine

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

# --- Mock Worker Task ---
def mock_worker_task(job_id: str):
    # In production, this would be an SQS worker container running Parselmouth
    # We'll just wait 5 seconds and update the job to SUCCESS
    time.sleep(5)
    db = database.SessionLocal()
    job = db.query(models.ProsodyJob).filter(models.ProsodyJob.id == job_id).first()
    if job:
        job.status = "SUCCESS"
        job.overall_match_score = 85.5
        db.commit()
    db.close()

@app.post("/jobs", response_model=schemas.JobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_job(job_req: schemas.JobCreate, background_tasks: BackgroundTasks, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    # Verify the native sample exists
    sample = db.query(models.NativeSample).filter(models.NativeSample.id == job_req.native_sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Native sample not found")
        
    # Backend validation (redundant with frontend): +/- 20% duration check
    lower_bound = sample.duration * 0.8
    upper_bound = sample.duration * 1.2
    if job_req.user_audio_duration < lower_bound or job_req.user_audio_duration > upper_bound:
        raise HTTPException(status_code=400, detail="Recording duration deviates too much from native reference.")

    # Generate a unique Job ID and save it
    new_job = models.ProsodyJob(
        user_id=current_user.id,
        native_sample_id=sample.id,
        user_s3_path="mock-s3-upload-path/audio.wav" # Mocking S3 pre-signed URL
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    # Dispatch to background worker (Simulating SQS)
    background_tasks.add_task(mock_worker_task, new_job.id)

    return {"id": new_job.id, "status": new_job.status, "user_s3_path": new_job.user_s3_path}

@app.get("/jobs/{job_id}", response_model=dict)
def get_job_status(job_id: str, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_user)):
    job = db.query(models.ProsodyJob).filter(models.ProsodyJob.id == job_id, models.ProsodyJob.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"id": job.id, "status": job.status, "score": job.overall_match_score}
