"""ORM row -> response payload assembly.

Keeps the decoding rules (JSON-encoded columns, derived flags) out of the route
handlers, so a route reads as "look it up, serialize it".
"""
import json

from infra import models


def job_status_payload(job: models.ProsodyJob) -> dict:
    """The GET /jobs/{id} body (schemas.JobStatusResponse)."""
    # A failed job is retryable unless it failed because the practice has no
    # native reference yet — re-recording can't fix that (worker_plan.md §7).
    retryable = None
    if job.status == "FAILED":
        retryable = bool(job.practice and job.practice.audio_url)
    # AnalysisSegment.words is stored as a JSON string; decode it to the list the
    # schema expects (null when the segment has no anchored words).
    segments = [
        {
            "timestamp_start": seg.timestamp_start,
            "timestamp_end": seg.timestamp_end,
            "feedback_tag": seg.feedback_tag,
            "explanation": seg.explanation,
            "words": json.loads(seg.words) if seg.words else None,
        }
        for seg in job.segments
    ]
    return {
        "id": job.id,
        "status": job.status,
        "mode": job.mode,
        "score": job.overall_match_score,
        "pitch_score": job.pitch_score,
        "timing_score": job.timing_score,
        "energy_score": job.energy_score,
        "content_score": job.content_score,
        "error_message": job.error_message,
        "practice_id": job.practice_id,
        "transcript": job.practice.transcript if job.practice else None,
        "segments": segments,
        "retryable": retryable,
    }
