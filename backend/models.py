from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import uuid

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
    user_s3_path = Column(String, nullable=False)
    overall_match_score = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("User", back_populates="jobs")
    practice = relationship("Practice", back_populates="jobs")
    segments = relationship("AnalysisSegment", back_populates="job")

class AnalysisSegment(Base):
    __tablename__ = "analysis_segments"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, ForeignKey("prosody_jobs.id"))
    timestamp_start = Column(Float, nullable=False)
    timestamp_end = Column(Float, nullable=False)
    feedback_tag = Column(String)
    explanation = Column(String)
    s3_coordinates_json_path = Column(String)

    job = relationship("ProsodyJob", back_populates="segments")
