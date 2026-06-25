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

class NativeSampleResponse(BaseModel):
    id: int
    s3_path: str
    transcript: str
    linguistic_notes: Optional[str] = None
    difficulty_level: Optional[str] = None
    duration: float

    class Config:
        orm_mode = True

class JobCreate(BaseModel):
    native_sample_id: int
    user_audio_duration: float

class JobResponse(BaseModel):
    id: str
    status: str
    user_s3_path: str # The pre-signed URL or path the frontend should upload to
    
    class Config:
        orm_mode = True
