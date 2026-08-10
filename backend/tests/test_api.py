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
from datetime import datetime
from pathlib import Path

import pytest

from api import security
from infra import database, models, storage
from worker import core as worker_core
from conftest import NATIVE_DURATION_S
from tools.synth_audio import write_sine_wav

PASSWORD = "test-password-1"


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


def test_content_axis_blends_into_overall(client, monkeypatch):
    # Override the autouse stub: the gate recognized the words at WER 0.2, which
    # maps to a content sub-score of 80 and must blend into the overall.
    from domain import content_gate, dsp

    monkeypatch.setattr(
        content_gate, "assess",
        lambda *a, **k: content_gate.ContentGateResult(True, True, 0.2, "stub wer"),
    )
    headers = _auth_headers(client)
    job_id = _post_job(client, headers, client.native_wav.read_bytes(), NATIVE_DURATION_S).json()["id"]
    body = client.get(f"/jobs/{job_id}", headers=headers).json()

    assert body["status"] == "SUCCESS", body["error_message"]
    assert body["content_score"] == 80.0
    prosody = (dsp.PITCH_WEIGHT * body["pitch_score"]
               + dsp.TIMING_WEIGHT * body["timing_score"]
               + dsp.ENERGY_WEIGHT * body["energy_score"])
    assert body["score"] == pytest.approx(dsp.blend_content(prosody, 80.0), abs=0.2)


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
    write_sine_wav(short, freq_hz=150.0, duration_s=1.0)
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
    write_sine_wav(take, freq_hz=210.0, duration_s=NATIVE_DURATION_S + 1.0, freq_end_hz=250.0)
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


# --- Job history (master-plan ticket 18) ------------------------------------

def _seed_jobs(client, email, specs):
    """Insert history rows straight into the DB — the list endpoint doesn't care
    how a job was produced, and running the worker per row would be slow.
    `specs` is a list of (status, score); returns the ids, oldest first."""
    from infra import database

    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).one()
        ids = []
        for i, (job_status, score) in enumerate(specs):
            job = models.ProsodyJob(
                user_id=user.id,
                practice_id=client.practice_id,
                mode="solo",
                status=job_status,
                overall_match_score=score,
                # Explicit, distinct timestamps: SQLite's CURRENT_TIMESTAMP is
                # second-granular, so seeded rows would otherwise tie.
                created_at=datetime(2026, 1, 1, 12, 0, i),
            )
            db.add(job)
            db.flush()
            ids.append(job.id)
        db.commit()
        return ids
    finally:
        db.close()


def test_job_history_lists_owner_jobs_newest_first(client):
    headers = _auth_headers(client)
    ids = _seed_jobs(client, "tester@example.com", [("SUCCESS", 71.0), ("FAILED", None), ("PENDING", None)])

    body = client.get("/jobs", headers=headers).json()

    assert body["total"] == 3
    assert [row["id"] for row in body["jobs"]] == list(reversed(ids))
    newest, _, oldest = body["jobs"]
    assert newest["status"] == "PENDING" and newest["score"] is None
    assert oldest["status"] == "SUCCESS" and oldest["score"] == 71.0
    assert oldest["practice_id"] == client.practice_id
    assert oldest["practice_title"] == "Synthetic chirp"
    assert oldest["mode"] == "solo"
    # UTC-tagged, or the browser reads the timestamp as local time.
    assert oldest["created_at"] == "2026-01-01T12:00:00Z"


def test_job_history_paginates(client):
    headers = _auth_headers(client)
    ids = _seed_jobs(client, "tester@example.com", [("SUCCESS", float(i)) for i in range(5)])

    first = client.get("/jobs?limit=2&offset=0", headers=headers).json()
    assert first["total"] == 5
    assert [row["id"] for row in first["jobs"]] == [ids[4], ids[3]]

    last = client.get("/jobs?limit=2&offset=4", headers=headers).json()
    assert last["total"] == 5
    assert [row["id"] for row in last["jobs"]] == [ids[0]]


def test_job_history_pages_are_stable_for_same_second_takes(client):
    # Every row shares one timestamp, so ordering rests entirely on the id
    # tiebreak — without it, paging could repeat or skip rows.
    headers = _auth_headers(client)
    ids = _seed_jobs(client, "tester@example.com", [("SUCCESS", 50.0)] * 4)
    _same_created_at(ids)

    paged = []
    for offset in range(4):
        paged += [row["id"] for row in client.get(f"/jobs?limit=1&offset={offset}", headers=headers).json()["jobs"]]

    assert sorted(paged) == sorted(ids)


def _same_created_at(job_ids):
    """Collapse the seeded rows onto one timestamp."""
    from infra import database

    db = database.SessionLocal()
    try:
        for job_id in job_ids:
            db.query(models.ProsodyJob).filter(models.ProsodyJob.id == job_id).update(
                {"created_at": datetime(2026, 1, 1, 12, 0, 0)}
            )
        db.commit()
    finally:
        db.close()


def test_job_history_excludes_other_users_jobs(client):
    owner = _auth_headers(client, "owner@example.com")
    other = _auth_headers(client, "other@example.com")
    owner_ids = _seed_jobs(client, "owner@example.com", [("SUCCESS", 80.0)])
    _seed_jobs(client, "other@example.com", [("SUCCESS", 90.0), ("SUCCESS", 91.0)])

    body = client.get("/jobs", headers=owner).json()
    assert body["total"] == 1
    assert [row["id"] for row in body["jobs"]] == owner_ids

    assert client.get("/jobs", headers=other).json()["total"] == 2


def test_job_history_requires_auth(client):
    assert client.get("/jobs").status_code == 401


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
    write_sine_wav(take, freq_hz=210.0, duration_s=NATIVE_DURATION_S + 1.0, freq_end_hz=250.0)
    job_id = _post_job(client, headers, take.read_bytes(), NATIVE_DURATION_S + 1.0, mode="shadow").json()["id"]
    body = client.get(f"/jobs/{job_id}", headers=headers).json()
    assert body["status"] == "SUCCESS", body["error_message"]
    assert body["segments"], "expected the mismatched take to flag segments"
    assert all(seg["words"] == ["bonjour"] for seg in body["segments"])


# --- Ambient-noise pipeline (master-plan ticket 17) --------------------------

def _write_noisy_take(path, noise_amp, sr=16000, seed=0, ambient_lead_in=True):
    """A noisy take: the native chirp with white noise running throughout.

    `ambient_lead_in` picks which branch of the SNR gate the worker takes — True
    leaves NOISE_PROFILE_S of ambient-only lead-in (a credible noise profile, so
    reduction runs), False starts the chirp at sample zero (the profile is
    speech, so reduction is skipped and only the bandpass applies).
    """
    import numpy as np

    from domain.dsp import noise

    n = int(NATIVE_DURATION_S * sr)
    t = np.arange(n) / sr
    phase = 2 * np.pi * (120.0 * t + (180.0 - 120.0) / (2 * NATIVE_DURATION_S) * t ** 2)
    samples = 0.5 * np.sin(phase)
    if ambient_lead_in:
        samples[: int(noise.NOISE_PROFILE_S * sr)] = 0.0
    samples += np.random.default_rng(seed).normal(0, noise_amp, n)

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())


def test_noisy_recording_scores_without_a_hard_failure(client, tmp_path):
    headers = _auth_headers(client)
    take = tmp_path / "noisy_take.wav"
    _write_noisy_take(take, noise_amp=0.15)

    r = _post_job(client, headers, take.read_bytes(), NATIVE_DURATION_S)
    assert r.status_code == 202, r.text

    body = client.get(f"/jobs/{r.json()['id']}", headers=headers).json()
    assert body["status"] == "SUCCESS", body["error_message"]
    assert body["score"] is not None


def test_noisy_take_that_starts_mid_speech_still_scores(client, tmp_path):
    # The motivating case for the SNR gate: no ambient lead-in, so the first
    # 300ms is the user's own voice. Reduction must be skipped rather than
    # subtracting their speech from itself — and the take must still score.
    headers = _auth_headers(client)
    take = tmp_path / "no_lead_in.wav"
    _write_noisy_take(take, noise_amp=0.05, ambient_lead_in=False)

    r = _post_job(client, headers, take.read_bytes(), NATIVE_DURATION_S)
    body = client.get(f"/jobs/{r.json()['id']}", headers=headers).json()

    assert body["status"] == "SUCCESS", body["error_message"]
    # Bandpass-only keeps the contour close to the (untouched) native reference;
    # full reduction here would gut it and drag the energy axis down.
    assert body["score"] >= 80, body["score"]


def test_reduction_failure_falls_open_and_still_scores(client, tmp_path, monkeypatch):
    # A broken noisereduce install must cost the SNR-informed cleanup, not the
    # user's score (same fail-open contract as the STT content gate).
    import builtins

    real_import = builtins.__import__

    def _no_noisereduce(name, *args, **kwargs):
        if name == "noisereduce":
            raise ModuleNotFoundError("No module named 'noisereduce'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_noisereduce)

    headers = _auth_headers(client)
    take = tmp_path / "noisy_take.wav"
    _write_noisy_take(take, noise_amp=0.05)

    r = _post_job(client, headers, take.read_bytes(), NATIVE_DURATION_S)
    body = client.get(f"/jobs/{r.json()['id']}", headers=headers).json()

    assert body["status"] == "SUCCESS", body["error_message"]


def test_snr_is_persisted_on_the_user_recording_asset(client, tmp_path):
    from domain.dsp import noise
    from infra import database

    headers = _auth_headers(client)
    take = tmp_path / "noisy_take.wav"
    _write_noisy_take(take, noise_amp=0.05)
    job_id = _post_job(client, headers, take.read_bytes(), NATIVE_DURATION_S).json()["id"]

    db = database.SessionLocal()
    try:
        asset = (
            db.query(models.AudioAsset)
            .filter(models.AudioAsset.job_id == job_id, models.AudioAsset.role == "USER_RECORDING")
            .one()
        )
        # A genuine quiet lead-in against a full-level body: comfortably above
        # the gate, so reduction ran and the number is a real measurement.
        assert asset.snr_db is not None
        assert asset.snr_db > noise.MIN_PROFILE_SNR_DB
    finally:
        db.close()


# --- Auth edges -------------------------------------------------------------

def test_duplicate_registration_rejected(client):
    _auth_headers(client)
    r = client.post("/auth/register", json={"email": "tester@example.com", "password": PASSWORD})
    assert r.status_code == 400


def test_login_wrong_password_rejected(client):
    _auth_headers(client)
    r = client.post("/auth/login", data={"username": "tester@example.com", "password": "wrong"})
    assert r.status_code == 401


# --- Google sign-in ---------------------------------------------------------

def _stub_google(monkeypatch, **claims):
    """Configure a client ID and make token verification return `claims`.
    The signature check itself is google-auth's job, not ours to re-test."""
    monkeypatch.setattr(security, "GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(security, "verify_google_id_token", lambda credential: claims)


def test_google_login_creates_user_and_authenticates(client, monkeypatch):
    _stub_google(monkeypatch, email="camille@example.com", email_verified=True)
    r = client.post("/auth/google", json={"credential": "fake-id-token"})
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # The app JWT works on a real authenticated endpoint.
    job = _post_job(client, headers, client.native_wav.read_bytes(), NATIVE_DURATION_S)
    assert job.status_code == 202, job.text

    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == "camille@example.com").one()
        assert user.auth_provider == "google"
        assert user.password_hash is None
    finally:
        db.close()


def test_google_login_rejects_unverified_email(client, monkeypatch):
    _stub_google(monkeypatch, email="camille@example.com", email_verified=False)
    r = client.post("/auth/google", json={"credential": "fake-id-token"})
    assert r.status_code == 401


def test_google_login_rejects_invalid_credential(client, monkeypatch):
    monkeypatch.setattr(security, "GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(
        security, "verify_google_id_token",
        lambda credential: (_ for _ in ()).throw(ValueError("bad signature")),
    )
    r = client.post("/auth/google", json={"credential": "tampered"})
    assert r.status_code == 401


def test_google_login_unconfigured_returns_503(client):
    r = client.post("/auth/google", json={"credential": "fake-id-token"})
    assert r.status_code == 503


def test_google_user_password_login_returns_401_not_500(client, monkeypatch):
    _stub_google(monkeypatch, email="camille@example.com", email_verified=True)
    assert client.post("/auth/google", json={"credential": "fake-id-token"}).status_code == 200

    r = client.post("/auth/login", data={"username": "camille@example.com", "password": PASSWORD})
    assert r.status_code == 401


def test_google_login_reuses_existing_password_account(client, monkeypatch):
    _auth_headers(client)  # registers tester@example.com with a password
    _stub_google(monkeypatch, email="tester@example.com", email_verified=True)
    r = client.post("/auth/google", json={"credential": "fake-id-token"})
    assert r.status_code == 200, r.text

    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == "tester@example.com").one()
        assert user.auth_provider == "password"  # untouched
        assert user.password_hash is not None
    finally:
        db.close()

    # Password login still works for that account.
    r = client.post("/auth/login", data={"username": "tester@example.com", "password": PASSWORD})
    assert r.status_code == 200
