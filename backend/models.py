from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import uuid

# All tables required for the project

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    jobs = relationship("ProsodyJob", back_populates="owner")

class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id = Column(Integer, primary_key=True, index=True)
    jti = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

class Practice(Base):
    __tablename__ = "practices"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    transcript = Column(String, nullable=False)
    level = Column(String, nullable=False)
    length = Column(String, nullable=False)
    speed = Column(String, nullable=False)
    duration = Column(Float, nullable=False)
    audio_url = Column(String, nullable=True)
    video_url = Column(String, nullable=True)
    notes = Column(String, nullable=True)

    jobs = relationship("ProsodyJob", back_populates="practice")

class ProsodyJob(Base):
    __tablename__ = "prosody_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.id"))
    practice_id = Column(Integer, ForeignKey("practices.id"))
    status = Column(String, default="PENDING")
    overall_match_score = Column(Float)
    pitch_score = Column(Float, nullable=True)      # per-axis sub-scores (dsp-2); null for pre-dsp-2 rows
    timing_score = Column(Float, nullable=True)
    energy_score = Column(Float, nullable=True)
    error_message = Column(String, nullable=True)   # why a job FAILED (today failures vanish silently)
    algo_version = Column(String, nullable=True)     # which DSP version produced the score (KPI comparability)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", back_populates="jobs")
    practice = relationship("Practice", back_populates="jobs")
    segments = relationship("AnalysisSegment", back_populates="job")
    # A job owns its audio assets (user recording now; denoised/processed later).
    assets = relationship("AudioAsset", back_populates="job")


class AudioAsset(Base):
    __tablename__ = "audio_assets"

    # --- identity / linking ---
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("prosody_jobs.id"), nullable=True)  # replaces old user_s3_path literal
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # null for shared native clips
    role = Column(String, nullable=False)  # USER_RECORDING | NATIVE_REFERENCE | PROCESSED

    # --- storage / integrity (load-bearing now) ---
    storage_key = Column(String, nullable=False)
    storage_backend = Column(String, nullable=False, default="LOCAL")  # LOCAL | S3
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String, nullable=False)

    # --- audio technical (server-derived at ingest) ---
    duration_seconds = Column(Float, nullable=False)  # authoritative, re-derived from the file
    sample_rate = Column(Integer, nullable=False)
    channels = Column(Integer, nullable=False)
    codec = Column(String, nullable=False)

    # --- integrity cross-check ---
    client_reported_duration = Column(Float, nullable=True)

    # --- quality signals (populated Phase 2 noise pipeline) ---
    snr_db = Column(Float, nullable=True)
    pitch_confidence = Column(Float, nullable=True)

    # --- lifecycle ---
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)  # created_at + 30d for user recordings

    job = relationship("ProsodyJob", back_populates="assets")

class AnalysisSegment(Base):
    __tablename__ = "analysis_segments"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, ForeignKey("prosody_jobs.id"))
    timestamp_start = Column(Float, nullable=False)
    timestamp_end = Column(Float, nullable=False)
    feedback_tag = Column(String)
    explanation = Column(String)
    # Backend-agnostic storage key of the job's coordinate archive. The DB
    # column keeps its historical name (s3_coordinates_json_path) to avoid a
    # SQLite table rebuild — only the ORM attribute is renamed.
    coordinates_key = Column("s3_coordinates_json_path", String)

    job = relationship("ProsodyJob", back_populates="segments")
