# 06 — align_natives.py ignores DATABASE_URL

**What to build:** [align_natives.py](../../../backend/tools/align_natives.py) builds its own engine
with a hardcoded `sqlite:///{BACKEND_DIR}/lecho.db` and `connect_args={"check_same_thread": False}`,
so it writes word alignments to the dev SQLite file no matter what `DATABASE_URL` says. After
ticket 01 it is the **only** module in the backend that does not respect the env var — every other
entry point (app, worker, seed) goes through `infra.database`.

Fix it the same way `tools/seed.py` was fixed in 01: import `SQLALCHEMY_DATABASE_URL` and
`CONNECT_ARGS` from `infra.database` instead of constructing the URL locally. That is the whole
change; the alignment logic is untouched.

**Why it matters:** it is an offline tool run by hand, so nothing breaks today — but against a
Postgres deployment it silently writes to the wrong database and the alignments never appear.
Silent-wrong-target is worse than a crash.

**Found during:** ticket 01 verification. Deliberately left out of 01 because it was outside that
ticket's file list.

**Blocked by:** None — can start immediately. Independent of 03/04/05.

**Status:** ready-for-agent

- [ ] `align_natives.py` uses `infra.database`'s URL and connect args; no local engine construction
- [ ] Running it with `DATABASE_URL` unset still targets the dev SQLite file (no behaviour change)
- [ ] Running it with a Postgres `DATABASE_URL` writes alignments to that database
- [ ] Full pytest suite still green
