from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

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

class JobCreate(BaseModel):
    practice_id: int
    user_audio_duration: float

class JobResponse(BaseModel):
    id: str
    status: str
    user_s3_path: str # The pre-signed URL or path the frontend should upload to
    
    class Config:
        orm_mode = True
