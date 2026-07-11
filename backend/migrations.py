"""Idempotent startup migrations (no Alembic until Phase 3).

Column additions only: each entry is (table, column, DDL type). run() checks
PRAGMA table_info and applies ALTER TABLE ADD COLUMN for missing columns, so
it is safe to call on every app startup against any historical lecho.db.
Never solve a schema change by deleting the DB — that destroys ingested
native-clip rows.
"""
from sqlalchemy import text

MIGRATIONS = [
    ("prosody_jobs", "pitch_score", "FLOAT"),
    ("prosody_jobs", "timing_score", "FLOAT"),
    ("prosody_jobs", "energy_score", "FLOAT"),
]


def run(engine):
    with engine.begin() as conn:
        for table, column, ddl in MIGRATIONS:
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
