"""Registration and login. Token/hash mechanics live in api/security.py."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from api import schemas, security
from infra import database, models

router = APIRouter()


@router.post("/auth/register", response_model=schemas.UserResponse)
def register(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = security.get_password_hash(user.password)
    new_user = models.User(email=user.email, password_hash=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@router.post("/auth/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    # Google accounts have no hash: short-circuit before verify_password, which
    # raises on a null hash rather than returning False.
    if not user or not user.password_hash or not security.verify_password(
        form_data.password, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _issue_token(user)


@router.post("/auth/google", response_model=schemas.Token)
def google_login(payload: schemas.GoogleCredential, db: Session = Depends(database.get_db)):
    """Exchange a Google Identity Services ID token for the app's own JWT."""
    if not security.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")

    try:
        claims = security.verify_google_id_token(payload.credential)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google credential",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = claims.get("email")
    if not email or not claims.get("email_verified"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google account has no verified email",
        )

    # Match on email: an existing password user signing in with Google reaches
    # their own account rather than being locked out by a duplicate.
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        user = models.User(email=email, password_hash=None, auth_provider="google")
        db.add(user)
        db.commit()
        db.refresh(user)

    return _issue_token(user)


def _issue_token(user):
    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}
