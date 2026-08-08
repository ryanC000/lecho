"""Job-pipeline logging (master-plan ticket 16).

Pins the observability contract, not the prose: every job line carries a
grep-able `job=<id>` prefix, a failure logs its reason before the status flips,
the DSP stages report wall-clock timings, and upload rejections and bleed
detections are visible on the console.
"""
import logging
import wave

from conftest import NATIVE_DURATION_S
from infra import models
from test_api import _auth_headers, _post_job
from tools.synth_audio import write_sine_wav
from worker import core as worker_core


def _job_messages(caplog, job_id):
    return [r.getMessage() for r in caplog.records if f"job={job_id}" in r.getMessage()]


def _bled_take(client, tmp_path):
    """A speakers-not-headphones shadow take: the native clip plus a 1s tail."""
    with wave.open(str(client.native_wav)) as r:
        params = r.getparams()
        frames = r.readframes(r.getnframes())
    path = tmp_path / "bled_take.wav"
    with wave.open(str(path), "wb") as w:
        w.setparams(params)
        w.writeframes(frames + b"\x00" * params.framerate * params.sampwidth)
    return path


def test_successful_job_reads_as_one_story(client, caplog):
    caplog.set_level(logging.INFO)
    headers = _auth_headers(client)
    job_id = _post_job(client, headers, client.native_wav.read_bytes(), NATIVE_DURATION_S).json()["id"]

    messages = _job_messages(caplog, job_id)
    created = [m for m in messages if "created" in m]
    assert len(created) == 1, messages
    assert "status=PENDING" in created[0]
    assert f"practice={client.practice_id}" in created[0]
    assert "mode=solo" in created[0]
    assert f"client_duration={NATIVE_DURATION_S:.2f}s" in created[0]

    assert any("-> SUCCESS" in m for m in messages), messages
    timings = [m for m in messages if " dsp " in m]
    assert len(timings) == 1, messages
    for stage in ("extract=", "align=", "score="):
        assert stage in timings[0], timings[0]

    # Grep-ability: every pipeline line about this run leads with job=<id>.
    pipeline = [
        r.getMessage() for r in caplog.records
        if r.name in ("api.routes.jobs", "worker.core")
    ]
    assert pipeline
    assert all(m.startswith(f"job={job_id} ") for m in pipeline), pipeline


def test_fail_job_logs_reason_before_status_flips():
    job = models.ProsodyJob(id="job-1", status="PENDING")
    seen = []

    class _Spy(logging.Handler):
        def emit(self, record):
            seen.append((record.getMessage(), job.status))

    class _Db:
        def commit(self):
            pass

    spy = _Spy()
    logging.getLogger().addHandler(spy)
    try:
        worker_core.fail_job(_Db(), job, "native reference missing")
    finally:
        logging.getLogger().removeHandler(spy)

    assert job.status == "FAILED"
    assert len(seen) == 1, seen
    message, status_when_logged = seen[0]
    assert "native reference missing" in message
    assert status_when_logged == "PENDING"


def test_upload_rejection_is_logged_against_its_job(client, caplog, tmp_path):
    caplog.set_level(logging.INFO)
    headers = _auth_headers(client)
    short = tmp_path / "short.wav"
    write_sine_wav(short, freq_hz=150.0, duration_s=1.0)

    assert _post_job(client, headers, short.read_bytes(), NATIVE_DURATION_S).status_code == 400

    rejections = [m for m in caplog.messages if "upload rejected" in m]
    assert len(rejections) == 1, caplog.messages
    assert rejections[0].startswith("job=")
    assert "Duration 1.00s outside" in rejections[0]


def test_server_side_duration_gate_rejection_is_logged(client, caplog):
    # The gate on the server-derived duration (the client-reported value passed):
    # a native-length take submitted as a shadow take, which needs a 1s tail.
    caplog.set_level(logging.INFO)
    headers = _auth_headers(client)
    r = _post_job(
        client, headers, client.native_wav.read_bytes(),
        NATIVE_DURATION_S + 1.0, mode="shadow",
    )
    assert r.status_code == 400

    rejections = [m for m in caplog.messages if "upload rejected" in m]
    assert len(rejections) == 1, caplog.messages
    assert f"duration={NATIVE_DURATION_S:.2f}s" in rejections[0]
    assert "Shadow recording duration" in rejections[0]


def test_bleed_detection_is_logged_with_its_measurement(client, caplog, tmp_path):
    caplog.set_level(logging.INFO)
    headers = _auth_headers(client)
    take = _bled_take(client, tmp_path)
    job_id = _post_job(
        client, headers, take.read_bytes(), NATIVE_DURATION_S + 1.0, mode="shadow"
    ).json()["id"]

    messages = _job_messages(caplog, job_id)
    bleed = [m for m in messages if "bleed" in m]
    assert len(bleed) == 1, messages
    assert "peak_ncc=" in bleed[0]
    assert any("-> FAILED" in m for m in messages), messages
