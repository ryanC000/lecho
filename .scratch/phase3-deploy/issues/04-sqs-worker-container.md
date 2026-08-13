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

**Blocked by:** nothing — 02 (`23975b5`) and 03 (`910bd67`) are both done. The app image and
the compose stack (Postgres + MinIO) are in place; the worker service is added alongside them.

**Carried forward from 02:** the S3 suite is green on a *fresh* bucket but not re-runnable
against a dirty one — `conftest.py` isolates tests by pointing `STORAGE_ROOT` at a per-test
`tmp_path`, which is a LOCAL-only mechanism, so under S3 every test shares one bucket and
`test_alignment_endpoint_404_then_serves_contract` fails on the second run. Provision a fresh
bucket per CI run, or add a per-test key prefix to the storage seam.

**Blocker found while implementing — the content gate dies in a container.**
`content_gate.assess` shells out to `conda run -n stt` (faster-whisper has no cp314 wheel on the
Windows dev box, so it lives in a quarantined conda env). No image has conda, so in a container
the call raises `OSError`, is caught, and **fails open** — the deployed app would score gibberish
as a valid take and always return `content_score: null`, silently undoing ticket 22. The
quarantine's cause does not apply in the image: it is cp312 Linux x86_64, where faster-whisper is
an ordinary pip install. Fixed with a `CONTENT_GATE_BACKEND` env (`SUBPROCESS` default keeps the
dev box exactly as it was, `INPROCESS` imports the recognizer directly), faster-whisper added to
`requirements.txt` behind a `python_version < "3.13"` marker, and the `base` model baked into the
image at build time so pods don't each download it on their first job.

**DLQ semantics need no new code.** `worker.core.run` catches broad `Exception` and converts it to
a `FAILED` row, which is exactly the right split: a *user-facing* failure (bad audio, bleed,
unintelligible take) returns normally, so the message is deleted and never retried — the job is
finished, badly. Only an *infrastructure* failure (database unreachable, S3 down) escapes `run`;
the worker leaves that message undeleted, and the queue's redrive policy moves it to the DLQ after
`maxReceiveCount`. The entrypoint classifies nothing.

**Status:** code complete, **live path unverified** — the boxes needing a real queue are open
because no AWS account exists yet. Everything verifiable without one is green.

- [x] Upload publishes `job_id` to SQS; route returns without running DSP inline —
      `infra/queue.py`; `jobs.py` calls `queue.publish` with an INLINE fallback passed in as a
      callable (infra sits *below* worker in the layering, so the seam must not import it).
      Covered by `tests/test_queue.py` against a fake client, not a real queue.
- [x] Standalone worker polls SQS and scores via unchanged `worker.core.run` — `worker/main.py`,
      20s long poll, SIGTERM finishes the message in flight so `kubectl scale` costs no work
- [x] `QUEUE_BACKEND=INLINE` preserves the synchronous path; full suite green under it —
      105 passed, 3 skipped (96 before, plus the 9 new queue/worker tests)
- [x] Carried-forward S3 isolation fixed — `STORAGE_PREFIX` on the storage seam, applied only at
      the bucket boundary so stored keys stay canonical; `conftest.py` sets a per-test value
- [ ] Poison messages land in a DLQ after the retry limit; row shows the failure — the *ack
      contract* that drives this is covered by `tests/test_worker_main.py` (delete on normal
      return, leave undeleted when scoring raises), but the redrive itself is queue configuration
      and needs a real queue to observe (`k8s/README.md`: visibility 300s, `maxReceiveCount` 3)
- [ ] `docker compose up` runs app + worker as separate services scoring a real job — added as the
      `queue` compose profile, **not yet run** (no Docker daemon, no queue). It points at **real**
      SQS deliberately: boto3 resolves one credential set per process, so MinIO's keys and a real
      queue cannot coexist in one container, and emulating SQS locally would mean the LocalStack
      image that ticket 02 rejected.
