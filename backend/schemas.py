from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

# File for pydantic to validate all data transferred to and from backend

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str

class PracticeBase(BaseModel):
    title: str
    transcript: str
    level: str
    length: str
    speed: str
    duration: float
    audio_url: Optional[str] = None
    video_url: Optional[str] = None
    notes: Optional[str] = None

class Practice(PracticeBase):
    id: int
    class Config:
        orm_mode = True

# NOTE: job creation is now a multipart/form-data upload (file + practice_id +
# user_audio_duration), so those fields are declared as Form(...) params on the
# endpoint rather than a JSON body model. JobCreate is kept for documentation.
class JobCreate(BaseModel):
    practice_id: int
    user_audio_duration: float

class JobResponse(BaseModel):
    id: str
    status: str

    class Config:
        orm_mode = True

class SegmentResponse(BaseModel):
    timestamp_start: float
    timestamp_end: float
    feedback_tag: Optional[str] = None
    explanation: Optional[str] = None

    class Config:
        orm_mode = True

class JobStatusResponse(BaseModel):
    id: str
    status: str
    score: Optional[float] = None
    error_message: Optional[str] = None
    practice_id: Optional[int] = None
    transcript: Optional[str] = None
    segments: List[SegmentResponse] = []

    class Config:
        orm_mode = True
