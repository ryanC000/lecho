"""Practice catalog routes — the shared, unauthenticated content.

Native clips and alignments are shared reference material, unlike user
recordings, so none of these routes require a token.
"""
import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api import schemas
from infra import database, models, storage

router = APIRouter()


@router.get("/practices", response_model=List[schemas.Practice])
def get_practices(db: Session = Depends(database.get_db)):
    practices = db.query(models.Practice).all()
    return practices


@router.get("/practices/{practice_id}", response_model=schemas.Practice)
def get_practice(practice_id: int, db: Session = Depends(database.get_db)):
    practice = db.query(models.Practice).filter(models.Practice.id == practice_id).first()
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")
    return practice


@router.get("/practices/{practice_id}/audio")
def get_practice_audio(practice_id: int, db: Session = Depends(database.get_db)):
    """Stream a practice's native reference clip (ingested via ingest_native.py)."""
    practice = db.query(models.Practice).filter(models.Practice.id == practice_id).first()
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")
    if not practice.audio_url:
        raise HTTPException(status_code=404, detail="This practice has no reference audio yet.")
    if not storage.exists(practice.audio_url):
        raise HTTPException(status_code=404, detail="Reference audio file is missing from storage.")
    return storage.audio_response(practice.audio_url)


@router.get("/practices/{practice_id}/audio-url")
def get_practice_audio_url(practice_id: int, db: Session = Depends(database.get_db)):
    """The URL a fetch()-based player should load directly — see
    storage.direct_audio_url for why this differs from GET .../audio."""
    practice = db.query(models.Practice).filter(models.Practice.id == practice_id).first()
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")
    if not practice.audio_url:
        raise HTTPException(status_code=404, detail="This practice has no reference audio yet.")
    if not storage.exists(practice.audio_url):
        raise HTTPException(status_code=404, detail="Reference audio file is missing from storage.")
    same_origin_path = f"/practices/{practice_id}/audio"
    return {"url": storage.direct_audio_url(practice.audio_url, same_origin_path)}


@router.get("/practices/{practice_id}/alignment")
def get_practice_alignment(practice_id: int, db: Session = Depends(database.get_db)):
    """Serve a practice's word-alignment JSON (PRD 8.4), produced offline by
    align_natives.py. Unauthenticated like the audio route; 404 when absent."""
    practice = db.query(models.Practice).filter(models.Practice.id == practice_id).first()
    if not practice:
        raise HTTPException(status_code=404, detail="Practice not found")
    key = storage.alignment_key(practice_id)
    if not storage.exists(key):
        raise HTTPException(status_code=404, detail="This practice has no alignment yet.")
    return json.loads(storage.read_text(key))
