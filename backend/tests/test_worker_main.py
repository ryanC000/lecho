"""Worker entrypoint: the ack contract that drives DLQ redrive.

Scoring itself is covered by the API/DSP suites — what matters here is *when*
the message is deleted, because that is the only thing standing between a
transient outage and a job vanishing.
"""
import pytest

from infra import queue
from worker import core, main


@pytest.fixture()
def deleted(monkeypatch):
    seen = []
    monkeypatch.setattr(queue, "delete", lambda handle: seen.append(handle))
    return seen


def test_scored_job_is_acknowledged(monkeypatch, deleted):
    scored = []
    monkeypatch.setattr(core, "run", lambda job_id, factory: scored.append(job_id))

    main.handle("rh-1", '{"job_id": "job-1"}')

    assert scored == ["job-1"]
    assert deleted == ["rh-1"]


def test_infrastructure_failure_leaves_the_message_for_redelivery(monkeypatch, deleted):
    def explode(job_id, factory):
        raise OSError("database unreachable")

    monkeypatch.setattr(core, "run", explode)

    with pytest.raises(OSError):
        main.handle("rh-2", '{"job_id": "job-2"}')

    assert deleted == []


def test_user_facing_failure_is_acknowledged(monkeypatch, deleted):
    """`core.run` records a FAILED row and returns normally, so the job is
    finished — redelivering it would only fail the same way."""
    monkeypatch.setattr(core, "run", lambda job_id, factory: None)

    main.handle("rh-3", '{"job_id": "job-3"}')

    assert deleted == ["rh-3"]
