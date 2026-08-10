import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from infra import database, models

# Custom login and register logic

# Replace with env variables in production
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "supersecretkey_for_lecho_mvp")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Empty until the OAuth client ID from the Google Cloud console is configured.
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    
    # We add a unique identifier (jti) for revoking tokens
    import uuid
    to_encode.update({"exp": expire, "jti": str(uuid.uuid4())})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_google_id_token(credential: str) -> dict:
    """Return the claims of a Google Sign-In ID token, or raise ValueError.

    google-auth checks the signature against Google's public keys plus the
    issuer, audience and expiry — everything except the email_verified claim.
    """
    return google_id_token.verify_oauth2_token(
        credential, google_requests.Request(), GOOGLE_CLIENT_ID
    )


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        jti: str = payload.get("jti")
        if user_id is None or jti is None:
            raise credentials_exception
            
        # Check if token is revoked
        is_revoked = db.query(models.RevokedToken).filter(models.RevokedToken.jti == jti).first()
        if is_revoked:
            raise credentials_exception
            
    except JWTError:
        raise credentials_exception
        
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user
