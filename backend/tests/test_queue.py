"""Queue seam: both backends, with a fake SQS client.

The SQS branch is covered against a stub rather than a real queue (or moto) —
what needs pinning is that publish/receive/delete speak the right calls and that
the message body round-trips through parse_job_id, none of which needs AWS.
"""
import json

import pytest

from infra import queue


class FakeSqs:
    def __init__(self, messages=None):
        self.sent = []
        self.deleted = []
        self.received_with = None
        self._messages = messages or []

    def send_message(self, QueueUrl, MessageBody):
        self.sent.append((QueueUrl, MessageBody))

    def receive_message(self, **kwargs):
        self.received_with = kwargs
        return {"Messages": self._messages} if self._messages else {}

    def delete_message(self, QueueUrl, ReceiptHandle):
        self.deleted.append((QueueUrl, ReceiptHandle))


@pytest.fixture()
def sqs(monkeypatch):
    fake = FakeSqs()
    monkeypatch.setattr(queue, "_client", fake)
    monkeypatch.setattr(queue, "QUEUE_URL", "https://sqs.test/queue")
    return fake


def test_inline_runs_the_callers_fallback_and_never_touches_sqs(monkeypatch, sqs):
    monkeypatch.setattr(queue, "BACKEND", queue.BACKEND_INLINE)
    ran = []

    queue.publish("job-1", lambda: ran.append("job-1"))

    assert ran == ["job-1"]
    assert sqs.sent == []


def test_sqs_publishes_the_job_id_and_skips_the_fallback(monkeypatch, sqs):
    monkeypatch.setattr(queue, "BACKEND", queue.BACKEND_SQS)
    ran = []

    queue.publish("job-2", lambda: ran.append("job-2"))

    assert ran == []
    assert len(sqs.sent) == 1
    url, body = sqs.sent[0]
    assert url == "https://sqs.test/queue"
    assert json.loads(body) == {"job_id": "job-2"}


def test_published_body_parses_back_to_the_job_id(monkeypatch, sqs):
    monkeypatch.setattr(queue, "BACKEND", queue.BACKEND_SQS)

    queue.publish("job-3", lambda: None)

    assert queue.parse_job_id(sqs.sent[0][1]) == "job-3"


def test_receive_long_polls_one_message_at_a_time(monkeypatch):
    fake = FakeSqs(messages=[{"ReceiptHandle": "rh-1", "Body": '{"job_id": "job-4"}'}])
    monkeypatch.setattr(queue, "_client", fake)
    monkeypatch.setattr(queue, "QUEUE_URL", "https://sqs.test/queue")

    assert queue.receive() == [("rh-1", '{"job_id": "job-4"}')]
    assert fake.received_with["WaitTimeSeconds"] == queue.POLL_WAIT_S
    assert fake.received_with["MaxNumberOfMessages"] == 1


def test_receive_returns_empty_when_the_queue_is_idle(sqs):
    assert queue.receive() == []


def test_delete_acknowledges_by_receipt_handle(sqs):
    queue.delete("rh-9")

    assert sqs.deleted == [("https://sqs.test/queue", "rh-9")]
