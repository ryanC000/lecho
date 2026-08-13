"""Queue seam.

Job dispatch goes through this module so that swapping FastAPI's in-process
BackgroundTasks for SQS is a one-file change behind the same interface —
the same shape as the storage seam next door.

`QUEUE_BACKEND=INLINE` (the default) keeps the pre-queue behaviour: the API
scores the job itself, after the response, in the same process. Dev and the test
suite stay on it so the suite is deterministic and needs no AWS account.
`QUEUE_BACKEND=SQS` publishes the job id instead, and a separate worker
container consumes it — the split that lets audio processing scale on its own.

Nothing here knows how a job is scored; `worker.core.run` is the transport-
independent seam both sides call.
"""
import json
import logging
import os

BACKEND_INLINE = "INLINE"
BACKEND_SQS = "SQS"

BACKEND = os.getenv("QUEUE_BACKEND", BACKEND_INLINE).upper()
QUEUE_URL = os.getenv("SQS_QUEUE_URL", "")
REGION = os.getenv("AWS_REGION") or None

# Long-poll rather than spin: one ReceiveMessage call parks for up to this long
# waiting for work, which is both cheaper (SQS bills per request) and lower
# latency than sleeping between polls.
POLL_WAIT_S = 20

logger = logging.getLogger(__name__)

_client = None


def _sqs():
    """The shared SQS client, built on first use so INLINE never needs credentials."""
    global _client
    if _client is None:
        import boto3

        _client = boto3.client("sqs", region_name=REGION)
    return _client


def publish(job_id: str, run_inline) -> None:
    """Hand a created job to whatever will score it.

    `run_inline` is the caller's in-process fallback, invoked only under INLINE.
    It is passed in rather than imported because infra sits *below* worker in the
    layering (api -> worker -> infra): this module must not know how a job runs.
    Under SQS the API's work ends here and the request returns without touching
    the DSP pipeline.
    """
    if BACKEND == BACKEND_SQS:
        _sqs().send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps({"job_id": job_id}))
        logger.info("job=%s published to SQS", job_id)
        return
    run_inline()


def parse_job_id(body: str) -> str:
    """The job id carried by a message body. The encoding lives here, next to
    the publisher that wrote it, so the two can never drift."""
    return json.loads(body)["job_id"]


def receive(wait_seconds: int = POLL_WAIT_S) -> list:
    """Long-poll for work, returning [(receipt_handle, body), ...].

    SQS-only: the worker entrypoint has nothing to consume under INLINE, where
    the API scores its own jobs. One message at a time — a scoring job is
    seconds of CPU, so there is nothing to gain from batching and a batch would
    only widen the window in which a pod eviction loses in-flight work.
    """
    response = _sqs().receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=wait_seconds,
    )
    return [(m["ReceiptHandle"], m["Body"]) for m in response.get("Messages", [])]


def delete(receipt_handle: str) -> None:
    """Acknowledge a message. Not called when scoring raises, which is what lets
    the redrive policy move a genuinely undeliverable job to the DLQ."""
    _sqs().delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt_handle)
