"""Idempotent startup migrations, SQLite and PostgreSQL.

Phase 3 chose an information_schema lookup over adopting Alembic: this table is
six column additions with portable DDL, and Alembic would add a dependency, a
versions/ tree and a stamping step to manage that.

Column additions only: each entry is (table, column, DDL type). run() reads the
existing columns (PRAGMA table_info on SQLite, information_schema.columns on
PostgreSQL) and applies ALTER TABLE ADD COLUMN for missing ones, so it is safe
to call on every app startup against any historical database.
Never solve a schema change by deleting the DB — that destroys ingested
native-clip rows.
"""
from sqlalchemy import text

MIGRATIONS = [
    ("prosody_jobs", "pitch_score", "FLOAT"),
    ("prosody_jobs", "timing_score", "FLOAT"),
    ("prosody_jobs", "energy_score", "FLOAT"),
    ("prosody_jobs", "content_score", "FLOAT"),
    # DEFAULT so pre-shadow rows read as solo (they were).
    ("prosody_jobs", "mode", "TEXT NOT NULL DEFAULT 'solo'"),
    # Word-anchored feedback (PRD 8.4): JSON list of the segment's words, nullable.
    ("analysis_segments", "words", "TEXT"),
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


def run(engine):
    with engine.begin() as conn:
        for table, column, ddl in MIGRATIONS:
            existing = _existing_columns(conn, table)
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
