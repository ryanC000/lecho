"""Probe endpoints for the Kubernetes deployment (phase3-deploy ticket 05).

The split matters: liveness must not touch the database, or a brief Postgres
outage restarts every API pod instead of just draining traffic from them.
"""
from sqlalchemy.exc import OperationalError

from infra import database


def test_liveness_is_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_liveness_does_not_touch_the_database(client, monkeypatch):
    """A dead database must leave liveness green — that is the whole point of
    having two probes."""
    monkeypatch.setattr(database, "SessionLocal", _broken_session_factory)

    assert client.get("/health").status_code == 200


def test_readiness_is_ready_when_the_database_answers(client):
    r = client.get("/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_readiness_is_503_when_the_database_is_down(client, monkeypatch):
    monkeypatch.setattr(database, "SessionLocal", _broken_session_factory)

    r = client.get("/health/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable"}


class _BrokenSession:
    """A session whose every query fails the way an unreachable server does."""

    def execute(self, *args, **kwargs):
        raise OperationalError("SELECT 1", None, Exception("connection refused"))

    def close(self):
        pass


def _broken_session_factory():
    return _BrokenSession()
