"""API lifecycle tests — the regression net for the whole core loop.

Runs the real FastAPI app against a per-test temp SQLite DB and temp storage
root (never the dev lecho.db): register → login → solo job on a synthetic
clip identical to the practice's native → the worker runs inline under
TestClient → SUCCESS with near-100 score and per-axis sub-scores. Plus the
ingestion gates and auth/ownership rejections.

Assertions for logout revocation activate with their tickets (master-plan 13) —
add them here when those land.
"""
import json
import wave
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
import worker_core
from test_dsp import _write_sine_wav

PASSWORD = "test-password-1"
NATIVE_DURATION_S = 3.0


@pytest.fixture(autouse=True)
def _skip_content_gate(monkeypatch):
    """Keep the MFA content gate (ticket 20) out of the hermetic suite — it
    shells out to conda/MFA (~45s per job). Its own decision logic and parsing
    are covered in test_content_gate.py; here it fails open so the worker scores
    exactly as before."""
    import content_gate

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


def test_shadow_bleed_rejected_with_headphones_message(client, tmp_path):
    # A speakers-not-headphones take: the upload literally contains the native
    # clip plus the 1s tail, so it passes both duration gates but the worker's
    # bleed gate must fail it — retryable, with the exact headphones message.
    # (Solo never runs this check: the lifecycle test above submits these same
    # native bytes as a solo take and must keep scoring SUCCESS.)
    headers = _auth_headers(client)
    with wave.open(str(client.native_wav)) as r:
        params = r.getparams()
        native_frames = r.readframes(r.getnframes())
    bled = tmp_path / "bled_take.wav"
    with wave.open(str(bled), "wb") as w:
        w.setparams(params)
        w.writeframes(native_frames + b"\x00" * params.framerate * params.sampwidth)

    r = _post_job(client, headers, bled.read_bytes(), NATIVE_DURATION_S + 1.0, mode="shadow")
    assert r.status_code == 202, r.text

    body = client.get(f"/jobs/{r.json()['id']}", headers=headers).json()
    assert body["status"] == "FAILED"
    assert body["retryable"] is True
    assert body["error_message"] == worker_core.BLEED_MESSAGE


# --- Coordinates endpoint (master-plan ticket 11) ---------------------------

# The fixed archive contract produced by the worker (dsp.build_archive).
_ARCHIVE_KEYS = {
    "times", "native_f0_hz", "user_f0_hz_aligned",
    "native_semitone", "user_semitone_aligned",
    "native_rms", "user_rms_aligned", "voiced_masks",
}


def test_coordinates_returns_archive_for_owner(client):
    headers = _auth_headers(client)
    job_id = _post_job(client, headers, client.native_wav.read_bytes(), NATIVE_DURATION_S).json()["id"]
    assert client.get(f"/jobs/{job_id}", headers=headers).json()["status"] == "SUCCESS"

    r = client.get(f"/jobs/{job_id}/coordinates", headers=headers)
    assert r.status_code == 200, r.text
    archive = r.json()
    assert set(archive) == _ARCHIVE_KEYS
    # Every top-level track is an equal-length array under the contract keys.
    n = len(archive["times"])
    for key in _ARCHIVE_KEYS - {"voiced_masks"}:
        assert len(archive[key]) == n, key
    for mask in archive["voiced_masks"].values():
        assert len(mask) == n


def test_coordinates_invisible_to_other_user(client):
    headers = _auth_headers(client, "owner@example.com")
    job_id = _post_job(client, headers, client.native_wav.read_bytes(), NATIVE_DURATION_S).json()["id"]
    other = _auth_headers(client, "other@example.com")
    assert client.get(f"/jobs/{job_id}/coordinates", headers=other).status_code == 404
    assert client.get(f"/jobs/{job_id}/coordinates", headers=headers).status_code == 200


def test_coordinates_conflict_when_not_success(client, tmp_path):
    # A bled shadow take FAILs the worker's bleed gate, so it never produces an
    # archive — /coordinates must 409, not 404.
    headers = _auth_headers(client)
    with wave.open(str(client.native_wav)) as r:
        params = r.getparams()
        native_frames = r.readframes(r.getnframes())
    bled = tmp_path / "bled_take.wav"
    with wave.open(str(bled), "wb") as w:
        w.setparams(params)
        w.writeframes(native_frames + b"\x00" * params.framerate * params.sampwidth)
    job_id = _post_job(client, headers, bled.read_bytes(), NATIVE_DURATION_S + 1.0, mode="shadow").json()["id"]
    assert client.get(f"/jobs/{job_id}", headers=headers).json()["status"] == "FAILED"

    assert client.get(f"/jobs/{job_id}/coordinates", headers=headers).status_code == 409


# --- Word alignment (master-plan tickets 05/06, PRD 8.4) --------------------

_WORDS = [
    {"word": "on", "start": 0.0, "end": 0.5},
    {"word": "les", "start": 0.5, "end": 1.0},
    {"word": "amis", "start": 1.0, "end": 1.5},
]


def test_overlapping_words_interval_rule():
    # [0.4, 1.1) overlaps "on" (touches 0.5), "les", "amis".
    assert worker_core.overlapping_words(_WORDS, 0.4, 1.1) == ["on", "les", "amis"]
    # A word ending exactly at seg_start does not overlap (strict >).
    assert worker_core.overlapping_words(_WORDS, 0.5, 0.9) == ["les"]
    # No overlap / empty alignment.
    assert worker_core.overlapping_words(_WORDS, 2.0, 3.0) == []
    assert worker_core.overlapping_words([], 0.0, 1.0) == []


def _write_alignment(client, words):
    storage.save_text(
        json.dumps({"practice_id": client.practice_id, "source": "manual",
                    "model": "french_mfa", "words": words}),
        storage.alignment_key(client.practice_id),
    )


def test_alignment_endpoint_404_then_serves_contract(client):
    # 404 before any alignment exists (like the native-audio route)...
    assert client.get(f"/practices/{client.practice_id}/alignment").status_code == 404
    assert client.get("/practices/99999/alignment").status_code == 404
    # ...200 with the verbatim contract once one is written.
    words = [{"word": "bonjour", "start": 0.0, "end": 3.0}]
    _write_alignment(client, words)
    r = client.get(f"/practices/{client.practice_id}/alignment")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["practice_id"] == client.practice_id
    assert body["words"] == words


def test_unaligned_job_segments_have_null_words(client):
    # No alignment for this practice → every segment renders as today (words null).
    headers = _auth_headers(client)
    job_id = _post_job(client, headers, client.native_wav.read_bytes(), NATIVE_DURATION_S).json()["id"]
    body = client.get(f"/jobs/{job_id}", headers=headers).json()
    assert body["status"] == "SUCCESS"
    assert all(seg["words"] is None for seg in body["segments"])


def test_aligned_job_attaches_overlapping_words(client, tmp_path):
    # A single word spanning the whole clip must attach to every segment a
    # mismatched shadow take produces.
    _write_alignment(client, [{"word": "bonjour", "start": 0.0, "end": NATIVE_DURATION_S + 1.0}])
    headers = _auth_headers(client)
    take = tmp_path / "mismatch.wav"
    _write_sine_wav(take, freq_hz=210.0, duration_s=NATIVE_DURATION_S + 1.0, freq_end_hz=250.0)
    job_id = _post_job(client, headers, take.read_bytes(), NATIVE_DURATION_S + 1.0, mode="shadow").json()["id"]
    body = client.get(f"/jobs/{job_id}", headers=headers).json()
    assert body["status"] == "SUCCESS", body["error_message"]
    assert body["segments"], "expected the mismatched take to flag segments"
    assert all(seg["words"] == ["bonjour"] for seg in body["segments"])


# --- Auth edges -------------------------------------------------------------

def test_duplicate_registration_rejected(client):
    _auth_headers(client)
    r = client.post("/auth/register", json={"email": "tester@example.com", "password": PASSWORD})
    assert r.status_code == 400


def test_login_wrong_password_rejected(client):
    _auth_headers(client)
    r = client.post("/auth/login", data={"username": "tester@example.com", "password": "wrong"})
    assert r.status_code == 401
