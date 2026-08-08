"""FastAPI application assembly — the HTTP transport adapter, and nothing else.

Run from `backend/`:  uvicorn api.main:app --reload

Layering (enforced by review, not tooling):
    api    -> domain, ingest, infra, worker
    worker -> domain, infra
    ingest -> infra
    domain -> nothing internal (pure policy and algorithms)
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import auth, health, jobs, practices
from infra import logs, migrations, models
from infra.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables (for local MVP), then apply idempotent column additions.
    # Runs at startup, not import — importing this module must not touch the DB.
    logs.configure()
    models.Base.metadata.create_all(bind=engine)
    migrations.run(engine)
    yield


def cors_origins() -> list[str]:
    """CORS_ORIGINS as a comma-separated list; defaults to the Vite dev server."""
    raw = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(title="L'Écho API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(practices.router)
app.include_router(auth.router)
app.include_router(jobs.router)
