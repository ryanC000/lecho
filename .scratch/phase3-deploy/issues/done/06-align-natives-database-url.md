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

**Status:** done — `b1f73cf`, 2026-08-08

- [x] `align_natives.py` uses `infra.database`'s URL and connect args; no local engine construction
      — went one step further than the ticket prescribed: `main()` now calls
      `database.SessionLocal()` rather than re-deriving `SQLALCHEMY_DATABASE_URL` +
      `CONNECT_ARGS`. Same source of truth, less code, and it satisfies "no local engine
      construction" literally. Unlike `seed.py`, this tool never needs its own engine —
      it only reads.
- [x] Running it with `DATABASE_URL` unset still targets the dev SQLite file — **with one
      real behaviour change:** the old path was absolute, `SessionLocal` resolves
      `sqlite:///./lecho.db` against cwd, so the tool must now be run from `backend/`.
      The module docstring already documented that as the usage.
- [x] Running it with a Postgres `DATABASE_URL` reads practices from that database —
      verified inside the compose stack from ticket 03: `python -m tools.align_natives
      --practice-id 2` found the Postgres-only practice ("Compose smoke") and proceeded to
      MFA, and `--practice-id 999` correctly reported none. No `lecho.db` exists in that
      image at all. It then fails at `conda`, which is not installed in the container —
      the MFA step itself is unverified there and needs a dev machine with the `mfa` env.
- [x] Full pytest suite still green — 72 passed, 1 skipped

**Correction to this ticket's premise:** `BACKEND_DIR` was referenced but never defined
anywhere in the module, so `main()` raised `NameError` on every invocation. The tool was not
silently writing to the wrong database — it was not running at all. The fix is the same
either way, and `main()` now has its first test coverage.
