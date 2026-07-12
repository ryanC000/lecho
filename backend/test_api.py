"""API lifecycle tests — the regression net for the whole core loop.

Runs the real FastAPI app against a per-test temp SQLite DB and temp storage
root (never the dev lecho.db): register → login → solo job on a synthetic
clip identical to the practice's native → the worker runs inline under
TestClient → SUCCESS with near-100 score and per-axis sub-scores. Plus the
ingestion gates and auth/ownership rejections.

Assertions for shadow gates, /coordinates, and logout revocation activate with
their tickets (master-plan 07/11/13) — add them here when those land.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import clip_ingest
import database
import main
import models
import storage
from test_dsp import _write_sine_wav

PASSWORD = "test-password-1"
NATIVE_DURATION_S = 3.0


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
            _write_sine_wav(wav, freq_hz=120.0, duration_s=NATIVE_DURATION_S, freq_end_hz=180.0)
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


def _auth_headers(client, email="tester@example.com"):
    r = client.post("/auth/register", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    r = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _post_job(client, headers, wav_bytes, duration, mode=None):
    data = {"practice_id": client.practice_id, "user_audio_duration": duration}
    if mode is not None:
        data["mode"] = mode
    return client.post(
        "/jobs",
        headers=headers,
        data=data,
        files={"file": ("take.wav", wav_bytes, "audio/wav")},
    )


# --- The core loop ---------------------------------------------------------

def test_lifecycle_solo_job_scores_near_100(client):
    headers = _auth_headers(client)
    r = _post_job(client, headers, client.native_wav.read_bytes(), NATIVE_DURATION_S)
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]

    # BackgroundTasks ran inline under TestClient — the job is already final.
    body = client.get(f"/jobs/{job_id}", headers=headers).json()
    assert body["status"] == "SUCCESS", body["error_message"]
    assert body["score"] >= 95  # identical clips
    for axis in ("pitch_score", "timing_score", "energy_score"):
        assert body[axis] is not None and body[axis] >= 90, (axis, body[axis])
    assert body["transcript"] == "bonjour tout le monde"
    assert isinstance(body["segments"], list)
    assert body["mode"] == "solo"  # mode omitted on POST → solo (backward compatible)


def test_job_requires_auth(client):
    r = _post_job(client, {}, client.native_wav.read_bytes(), NATIVE_DURATION_S)
    assert r.status_code == 401


def test_job_invisible_to_other_user(client):
    headers = _auth_headers(client, "owner@example.com")
    job_id = _post_job(client, headers, client.native_wav.read_bytes(), NATIVE_DURATION_S).json()["id"]
    other = _auth_headers(client, "other@example.com")
    assert client.get(f"/jobs/{job_id}", headers=other).status_code == 404
    assert client.get(f"/jobs/{job_id}", headers=headers).status_code == 200


# --- Ingestion gates --------------------------------------------------------

def test_solo_relative_duration_gate(client):
    headers = _auth_headers(client)
    r = _post_job(client, headers, client.native_wav.read_bytes(), NATIVE_DURATION_S * 2)
    assert r.status_code == 400
    assert "deviates" in r.json()["detail"]


def test_absolute_duration_gate_on_real_bytes(client, tmp_path):
    # Client-reported duration passes the relative gate; the real bytes (1s)
    # violate the absolute 2-15s gate derived server-side.
    headers = _auth_headers(client)
    short = tmp_path / "short.wav"
    _write_sine_wav(short, freq_hz=150.0, duration_s=1.0)
    r = _post_job(client, headers, short.read_bytes(), NATIVE_DURATION_S)
    assert r.status_code == 400
    assert "between 2 and 15" in r.json()["detail"]


def test_unreadable_audio_rejected(client):
    headers = _auth_headers(client)
    r = _post_job(client, headers, b"definitely not a wav", NATIVE_DURATION_S)
    assert r.status_code == 400
    assert "readable WAV" in r.json()["detail"]


# --- Shadow mode (master-plan ticket 07) -------------------------------------

def test_invalid_mode_rejected(client):
    headers = _auth_headers(client)
    r = _post_job(client, headers, client.native_wav.read_bytes(), NATIVE_DURATION_S, mode="duet")
    assert r.status_code == 400
    assert "mode" in r.json()["detail"]


def test_shadow_client_duration_gate(client):
    # A native-length take (no +1s tail) fails the shadow gate on the
    # client-reported duration before any bytes are inspected.
    headers = _auth_headers(client)
    r = _post_job(client, headers, client.native_wav.read_bytes(), NATIVE_DURATION_S, mode="shadow")
    assert r.status_code == 400
    assert "Shadow recording duration" in r.json()["detail"]


def test_shadow_server_duration_gate(client):
    # Client-reported duration passes the fast-fail (native + 1s), but the
    # real bytes are native-length — the server-derived check must catch it.
    headers = _auth_headers(client)
    r = _post_job(
        client, headers, client.native_wav.read_bytes(),
        NATIVE_DURATION_S + 1.0, mode="shadow",
    )
    assert r.status_code == 400
    assert "Shadow recording duration" in r.json()["detail"]


def test_shadow_job_accepted_and_scored(client, tmp_path):
    # A correctly-sized shadow take (native + 1s tail) whose content is the
    # learner's own voice (a chirp in a different register — no bleed).
    headers = _auth_headers(client)
    take = tmp_path / "shadow_take.wav"
    _write_sine_wav(take, freq_hz=210.0, duration_s=NATIVE_DURATION_S + 1.0, freq_end_hz=250.0)
    r = _post_job(client, headers, take.read_bytes(), NATIVE_DURATION_S + 1.0, mode="shadow")
    assert r.status_code == 202, r.text

    body = client.get(f"/jobs/{r.json()['id']}", headers=headers).json()
    assert body["mode"] == "shadow"
    assert body["status"] == "SUCCESS", body["error_message"]


# --- Auth edges -------------------------------------------------------------

def test_duplicate_registration_rejected(client):
    _auth_headers(client)
    r = client.post("/auth/register", json={"email": "tester@example.com", "password": PASSWORD})
    assert r.status_code == 400


def test_login_wrong_password_rejected(client):
    _auth_headers(client)
    r = client.post("/auth/login", data={"username": "tester@example.com", "password": "wrong"})
    assert r.status_code == 401
