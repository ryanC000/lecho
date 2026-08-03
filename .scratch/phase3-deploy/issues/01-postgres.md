# 01 — PostgreSQL backend

**What to build:** The app runs on PostgreSQL in deployment while staying on SQLite for local
dev, selected purely by a `DATABASE_URL` env var (defaulting to the current `sqlite:///./lecho.db`
so dev and the test suite are unchanged). The SQLite-only `connect_args={"check_same_thread": False}`
in [database.py](../../../backend/infra/database.py) and [seed.py](../../../backend/tools/seed.py) becomes
conditional on the URL scheme. The startup migrations in
[migrations.py](../../../backend/infra/migrations.py) are SQLite-specific — they introspect via
`PRAGMA table_info` and emit bare `ALTER TABLE ADD COLUMN` — so the add-and-backfill mechanism gets
a Postgres path (information_schema lookup, or adopt Alembic as the docstring's "no Alembic until
Phase 3" anticipated — pick the lighter option and record it). Verify the ORM types in
[models.py](../../../backend/infra/models.py) map cleanly to Postgres (TEXT/FLOAT are fine; check any
booleans/defaults).

**Precondition:** `psycopg` (v3) must install as a prebuilt cp314 wheel (`--only-binary :all:`) —
see the Python 3.14 native-build note. If it doesn't, record the blocker and stop.

**Blocked by:** None — can start immediately. Coordinate with master-plan #15 (env-config), which
owns the env-var convention.

**Status:** done (`0054c05`)

Chose the `information_schema.columns` lookup over Alembic — six column additions with DDL
that is already portable did not justify a new dependency plus a `versions/` tree and stamping.
`migrations.py` now branches on `conn.dialect.name`. `models.py` needed no changes: Boolean,
Float, String and `DateTime(timezone=True)`/`server_default=func.now()` all map cleanly
(`boolean`, `double precision`, `character varying`, `timestamptz DEFAULT now()`).

- [x] `DATABASE_URL` selects the backend; unset falls back to the SQLite dev default
- [x] `check_same_thread` applied only for the SQLite scheme
- [x] Migrations apply idempotently on a fresh Postgres DB and on an existing SQLite one
- [x] Full pytest suite green on both SQLite (default) and a Postgres URL
- [x] `seed.py` populates a Postgres DB without error
