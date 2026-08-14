"""Startup migrations against a historical database.

The users table predates Google sign-in: password_hash was NOT NULL and there
was no auth_provider column. These tests build that shape by hand and check
that run() upgrades it in place, twice, without losing rows.
"""
from sqlalchemy import create_engine, text

from infra import migrations, models

LEGACY_USERS_DDL = """
CREATE TABLE users (
    id INTEGER NOT NULL PRIMARY KEY,
    email VARCHAR NOT NULL,
    password_hash VARCHAR NOT NULL,
    is_active BOOLEAN,
    created_at DATETIME
)
"""


def _legacy_engine(tmp_path):
    """Current schema for every table except users, which is rewound to its
    pre-Google shape — run() expects the other tables to exist."""
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    models.Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE users"))
        conn.execute(text(LEGACY_USERS_DDL))
        conn.execute(text("CREATE UNIQUE INDEX ix_users_email ON users (email)"))
        conn.execute(text("CREATE INDEX ix_users_id ON users (id)"))
        conn.execute(
            text(
                "INSERT INTO users (id, email, password_hash, is_active) "
                "VALUES (1, 'existing@example.com', 'hashed', 1)"
            )
        )
    return engine


def _columns(engine):
    with engine.begin() as conn:
        return {row[1]: row for row in conn.execute(text("PRAGMA table_info(users)"))}


def test_legacy_users_table_gains_provider_and_nullable_hash(tmp_path):
    engine = _legacy_engine(tmp_path)
    migrations.run(engine)

    cols = _columns(engine)
    assert "auth_provider" in cols
    assert cols["password_hash"][3] == 0  # notnull flag cleared

    with engine.begin() as conn:
        row = conn.execute(text("SELECT email, password_hash, auth_provider FROM users")).one()
    assert row == ("existing@example.com", "hashed", "password")


LEGACY_JOBS_DDL = """
CREATE TABLE prosody_jobs (
    id VARCHAR NOT NULL PRIMARY KEY,
    user_id INTEGER,
    practice_id INTEGER,
    status VARCHAR,
    user_s3_path VARCHAR NOT NULL,
    overall_match_score FLOAT,
    created_at DATETIME,
    updated_at DATETIME
)
"""


def _legacy_jobs_engine(tmp_path):
    """prosody_jobs rewound to before AudioAsset: no per-axis scores, no mode,
    and the NOT NULL user_s3_path that AudioAsset replaced."""
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-jobs.db'}")
    models.Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE prosody_jobs"))
        conn.execute(text(LEGACY_JOBS_DDL))
        conn.execute(
            text(
                "INSERT INTO prosody_jobs (id, user_id, status, user_s3_path, overall_match_score) "
                "VALUES ('job-old', 1, 'SUCCESS', 'legacy/path.wav', 72.5)"
            )
        )
    return engine


def _job_columns(engine):
    with engine.begin() as conn:
        return {row[1] for row in conn.execute(text("PRAGMA table_info(prosody_jobs)"))}


def test_legacy_jobs_table_gains_score_columns_and_loses_user_s3_path(tmp_path):
    engine = _legacy_jobs_engine(tmp_path)
    migrations.run(engine)

    cols = _job_columns(engine)
    # Added to the model without a migration, so historical DBs 500 on any job read.
    assert {"error_message", "algo_version", "mode", "content_score"} <= cols
    # Dead NOT NULL column: left in place it rejects every insert.
    assert "user_s3_path" not in cols

    with engine.begin() as conn:
        # The pre-existing row survives the drop, minus the dropped column.
        assert conn.execute(text("SELECT overall_match_score FROM prosody_jobs")).scalar() == 72.5
        conn.execute(
            text(
                "INSERT INTO prosody_jobs (id, user_id, status, mode) "
                "VALUES ('job-new', 1, 'PENDING', 'shadow')"
            )
        )
        assert conn.execute(text("SELECT count(*) FROM prosody_jobs")).scalar() == 2


def test_dropping_user_s3_path_is_idempotent(tmp_path):
    engine = _legacy_jobs_engine(tmp_path)
    migrations.run(engine)
    migrations.run(engine)  # column already gone — must not raise

    assert "user_s3_path" not in _job_columns(engine)


def test_run_is_idempotent(tmp_path):
    engine = _legacy_engine(tmp_path)
    migrations.run(engine)
    migrations.run(engine)

    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM users")).scalar() == 1
        # A Google-shaped row (no password) is insertable after the rebuild.
        conn.execute(
            text(
                "INSERT INTO users (email, password_hash, auth_provider) "
                "VALUES ('camille@example.com', NULL, 'google')"
            )
        )
        assert conn.execute(text("SELECT count(*) FROM users")).scalar() == 2
