"""Shared fixtures for the backend suite.

The `client` fixture is the hermetic seam: a real FastAPI app bound to a
per-test temp SQLite DB and temp storage root, so the suite never touches the
dev `lecho.db` or `backend/storage/`.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api import main
from infra import database, models, storage
from ingest import clip_ingest
from tools.synth_audio import write_sine_wav

NATIVE_DURATION_S = 3.0


@pytest.fixture(autouse=True)
def _skip_content_gate(monkeypatch):
    """Keep the STT content gate out of the hermetic suite — it shells out to
    conda (~45s per job). Its own decision logic and parsing are covered in
    test_content_gate.py; here it fails open so the worker scores exactly as
    before."""
    from domain import content_gate

    monkeypatch.setattr(
        content_gate, "assess",
        lambda *a, **k: content_gate.ContentGateResult(False, True, None, "stubbed in tests"),
    )


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient on a temp DB + temp storage root, with one seeded practice
    whose native reference is a synthetic 120→180Hz chirp."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSession)
    monkeypatch.setattr(main, "engine", engine)  # lifespan create_all/migrations
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path / "storage")

    with TestClient(main.app) as c:  # context manager runs the lifespan
        db = TestingSession()
        try:
            practice = models.Practice(
                title="Synthetic chirp",
                transcript="bonjour tout le monde",
                level="B2",
                length="Short",
                speed="Normal",
                duration=NATIVE_DURATION_S,
            )
            db.add(practice)
            db.flush()
            wav = tmp_path / "native.wav"
            write_sine_wav(wav, freq_hz=120.0, duration_s=NATIVE_DURATION_S, freq_end_hz=180.0)
            with open(wav, "rb") as f:
                asset = clip_ingest.ingest_clip(f, f"native/{practice.id}.wav", role="NATIVE_REFERENCE")
            db.add(asset)
            practice.audio_url = asset.storage_key
            practice.duration = round(asset.duration_seconds, 2)
            db.commit()
            c.practice_id = practice.id
            c.native_wav = wav
        finally:
            db.close()
        yield c
