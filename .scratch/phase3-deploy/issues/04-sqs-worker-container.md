# 04 — SQS queue and standalone worker container

**What to build:** The scoring job crosses a real queue instead of an in-process background task.
The upload route in [main.py](../../../backend/api/main.py) currently ends with
`background_tasks.add_task(worker_core.run, ...)` (`worker.core`) — replace that dispatch with publishing the
`job_id` to an SQS queue. A new worker entrypoint (`backend/worker/main.py`) long-polls the queue
and calls the existing `worker.core.run(job_id, database.SessionLocal)` per message — `run` was
built as the transport-independent seam ("the Phase 3 SQS entrypoint imports the same function — a
transport swap, not a rewrite"), so no scoring logic moves. On success the message is deleted; on an
unexpected exception it goes to a dead-letter queue after N receives (the existing `fail_job` path
still records user-facing failures on the row). The worker runs as its own container / compose
service. Publish behind a small seam mirroring the storage one, with a `QUEUE_BACKEND` (`INLINE`
default) so dev and the test suite keep the synchronous in-process path and stay deterministic.

**Precondition (hard):** requires 02 (S3). Once the worker is a separate container it no longer
shares the app's local `storage/` disk, so both sides must read/write audio through S3 — a
local-disk worker container would fail to find the uploaded clip.

**Blocked by:** 03 (worker needs a container image). 02 is done (`23975b5`).

**Carried forward from 02:** the S3 suite is green on a *fresh* bucket but not re-runnable
against a dirty one — `conftest.py` isolates tests by pointing `STORAGE_ROOT` at a per-test
`tmp_path`, which is a LOCAL-only mechanism, so under S3 every test shares one bucket and
`test_alignment_endpoint_404_then_serves_contract` fails on the second run. Provision a fresh
bucket per CI run, or add a per-test key prefix to the storage seam.

**Status:** blocked

- [ ] Upload publishes `job_id` to SQS; route returns without running DSP inline
- [ ] Standalone worker polls SQS and scores via unchanged `worker.core.run`
- [ ] Poison messages land in a DLQ after the retry limit; row shows the failure
- [ ] `QUEUE_BACKEND=INLINE` preserves the synchronous path; full suite green under it
- [ ] `docker compose up` runs app + worker as separate services scoring a real job
