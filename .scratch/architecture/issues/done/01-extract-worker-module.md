# 01 — Extract the scoring worker into a deep module

**What to build:** The job-scoring worker becomes its own module with a small interface — run a job by id, with the DB session factory accepted as a dependency rather than created inside. The HTTP app keeps a two-line dispatch and stays the only transport adapter for now (the Phase 3 SQS adapter is the second adapter this seam is specced for). Import-time side effects (table creation, migrations) move out of module import so importing the app no longer writes to the dev database.

**Blocked by:** None — can start immediately.

**Status:** done

- [ ] Worker module importable with zero DB/filesystem side effects
- [ ] Interface accepts its session factory; no `SessionLocal` hard-wiring inside
- [ ] Table-creation/migration side effects run at app startup, not at import
- [ ] All existing behaviour unchanged: a job run end-to-end produces identical rows/scores
- [ ] Full pytest suite green

## Comments
Done 2026-07-11 in e1a06f7. worker_core.run(job_id, session_factory); fail_job shared with the upload route; lifespan owns create_all+migrations. Verified: import writes nothing, TestClient lifespan serves practices, 12 tests green.
