"""Deploy-varying configuration (master-plan ticket 15).

Both seams resolve their env var when called, so a deploy changes them without
a code change. The app calls each once at import, so the process reads its
environment at startup and never re-reads it.
"""
import logging

from api.main import cors_origins
from api.security import DEV_SECRET_KEY, jwt_secret


def test_cors_origins_defaults_to_the_vite_dev_server(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    assert cors_origins() == ["http://localhost:5173"]


def test_cors_origins_splits_a_comma_separated_list(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", " https://lecho.app , https://www.lecho.app ")

    assert cors_origins() == ["https://lecho.app", "https://www.lecho.app"]


def test_jwt_secret_uses_the_env_value_without_warning(monkeypatch, caplog):
    monkeypatch.setenv("JWT_SECRET_KEY", "a-real-deployed-secret")
    caplog.set_level(logging.WARNING)

    assert jwt_secret() == "a-real-deployed-secret"
    assert caplog.messages == []


def test_missing_jwt_secret_falls_back_to_the_dev_default_and_warns(monkeypatch, caplog):
    """A deploy that forgets the secret must be loud, not silently forgeable."""
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    caplog.set_level(logging.WARNING)

    assert jwt_secret() == DEV_SECRET_KEY
    assert any("JWT_SECRET_KEY" in m for m in caplog.messages), caplog.messages
