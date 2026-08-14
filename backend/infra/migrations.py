"""Idempotent startup migrations, SQLite and PostgreSQL.

Phase 3 chose an information_schema lookup over adopting Alembic: this table is
six column additions with portable DDL, and Alembic would add a dependency, a
versions/ tree and a stamping step to manage that.

MIGRATIONS holds column additions: each entry is (table, column, DDL type).
run() reads the existing columns (PRAGMA table_info on SQLite,
information_schema.columns on PostgreSQL) and applies ALTER TABLE ADD COLUMN
for missing ones, so it is safe to call on every app startup against any
historical database. DROPPED_COLUMNS is the mirror image: columns the model has
since removed, dropped when still present (SQLite 3.35+). Relaxing
users.password_hash to nullable (Google Sign-In) is the one step neither list
covers and is handled separately below.
Never solve a schema change by deleting the DB — that destroys ingested
native-clip rows.
"""
from sqlalchemy import text

MIGRATIONS = [
    ("prosody_jobs", "pitch_score", "FLOAT"),
    ("prosody_jobs", "timing_score", "FLOAT"),
    ("prosody_jobs", "energy_score", "FLOAT"),
    ("prosody_jobs", "content_score", "FLOAT"),
    # Why a job FAILED, and which DSP version scored it. Both were added to the
    # model without a migration, so pre-existing databases 500 on any job read.
    ("prosody_jobs", "error_message", "TEXT"),
    ("prosody_jobs", "algo_version", "TEXT"),
    # DEFAULT so pre-shadow rows read as solo (they were).
    ("prosody_jobs", "mode", "TEXT NOT NULL DEFAULT 'solo'"),
    # Word-anchored feedback (PRD 8.4): JSON list of the segment's words, nullable.
    ("analysis_segments", "words", "TEXT"),
    # DEFAULT so pre-Google rows read as password accounts (they were).
    ("users", "auth_provider", "TEXT NOT NULL DEFAULT 'password'"),
]

# Columns the model dropped, still present on older databases. AudioAsset
# replaced prosody_jobs.user_s3_path, but the column stayed behind NOT NULL with
# no default, so every insert into an untouched database fails.
DROPPED_COLUMNS = [
    ("prosody_jobs", "user_s3_path"),
]


def _existing_columns(conn, table):
    if conn.dialect.name == "sqlite":
        return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
    rows = conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = :table"
        ),
        {"table": table},
    )
    return {row[0] for row in rows}


def _password_hash_is_not_null(conn):
    if conn.dialect.name == "sqlite":
        rows = conn.execute(text("PRAGMA table_info(users)"))
        return any(row[1] == "password_hash" and row[3] == 1 for row in rows)
    row = conn.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'users' "
            "AND column_name = 'password_hash'"
        )
    ).first()
    return row is not None and row[0] == "NO"


def _relax_password_hash(conn):
    """Google accounts have no password. SQLite cannot ALTER a column's
    nullability, so the users table is rebuilt (12-step recipe); PostgreSQL
    does it in one statement."""
    if not _password_hash_is_not_null(conn):
        return
    if conn.dialect.name != "sqlite":
        conn.execute(text("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL"))
        return
    conn.execute(
        text(
            "CREATE TABLE users_migrated ("
            " id INTEGER NOT NULL PRIMARY KEY,"
            " email VARCHAR NOT NULL,"
            " password_hash VARCHAR,"
            " auth_provider VARCHAR NOT NULL DEFAULT 'password',"
            " is_active BOOLEAN,"
            " created_at DATETIME DEFAULT (CURRENT_TIMESTAMP)"
            ")"
        )
    )
    conn.execute(
        text(
            "INSERT INTO users_migrated (id, email, password_hash, auth_provider, is_active, created_at) "
            "SELECT id, email, password_hash, auth_provider, is_active, created_at FROM users"
        )
    )
    conn.execute(text("DROP TABLE users"))
    conn.execute(text("ALTER TABLE users_migrated RENAME TO users"))
    conn.execute(text("CREATE UNIQUE INDEX ix_users_email ON users (email)"))
    conn.execute(text("CREATE INDEX ix_users_id ON users (id)"))


def run(engine):
    with engine.begin() as conn:
        for table, column, ddl in MIGRATIONS:
            existing = _existing_columns(conn, table)
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        for table, column in DROPPED_COLUMNS:
            if column in _existing_columns(conn, table):
                conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
        # After the loop: the rebuild copies auth_provider, so it must exist.
        _relax_password_hash(conn)
