"""SQS worker entrypoint — the standalone scoring container.

Run from `backend/`:  python -m worker.main

Long-polls the queue and calls `worker.core.run` per message. That function is
the transport-independent seam the API also calls under QUEUE_BACKEND=INLINE, so
nothing about scoring changes here — only how the job arrives.

Retry semantics fall out of `core.run`'s existing contract rather than being
re-implemented:

  * A *user-facing* failure (bad audio, bleed, unintelligible take) is recorded
    on the row by `fail_job` and `run` returns normally. The message is deleted:
    the job is finished, badly, and redelivering it would only fail again.
  * An *infrastructure* failure (database unreachable, S3 down) escapes `run`.
    The message is not deleted, becomes visible again after the queue's
    visibility timeout, and the redrive policy moves it to the DLQ once
    maxReceiveCount is hit.

The process does not create tables or run migrations — the API owns schema, and
having N workers race it at startup is a way to deadlock a deploy.
"""
import logging
import signal

from infra import database, logs, queue
from worker import core

logger = logging.getLogger(__name__)

_stopping = False


def _request_stop(signum, _frame):
    """Finish the message in flight, then exit. Kubernetes sends SIGTERM on
    scale-down and rollout; dying mid-DSP would leave the job to time out and
    redeliver instead of simply completing."""
    global _stopping
    _stopping = True
    logger.info("signal=%s received — finishing current message then exiting", signum)


def handle(receipt_handle: str, body: str) -> None:
    job_id = queue.parse_job_id(body)
    core.run(job_id, database.SessionLocal)
    queue.delete(receipt_handle)


def main() -> None:
    logs.configure()
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    if queue.BACKEND != queue.BACKEND_SQS:
        raise SystemExit(
            f"worker.main needs QUEUE_BACKEND={queue.BACKEND_SQS}; got {queue.BACKEND}. "
            "Under INLINE the API scores its own jobs and this process has nothing to consume."
        )

    logger.info("worker started queue=%s", queue.QUEUE_URL)
    while not _stopping:
        for receipt_handle, body in queue.receive():
            try:
                handle(receipt_handle, body)
            except Exception:
                # Left undeleted on purpose — see the module docstring. Logged
                # rather than raised so one poison message cannot crash-loop the
                # pod out from under the healthy messages behind it.
                logger.exception("message failed; leaving it for redelivery/DLQ")
    logger.info("worker stopped")


if __name__ == "__main__":
    main()
