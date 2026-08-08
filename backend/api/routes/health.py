"""Probe endpoints for orchestrators (phase3-deploy ticket 05).

Two endpoints, because Kubernetes asks two different questions and answering
them the same way is a known way to build a restart loop:

    /health        liveness  — is this process alive? Never touches the DB, so
                               a Postgres blip cannot restart every API pod.
    /health/ready  readiness — can this pod serve traffic? Checks the DB, so a
                               pod that cannot reach it is drained, not killed.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from infra import database

router = APIRouter()


@router.get("/health")
def liveness():
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(db: Session = Depends(database.get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ready"}
