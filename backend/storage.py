"""Storage seam.

All audio I/O goes through this module so that swapping local disk for S3 in
Phase 3 is a one-file change behind the same interface. No route or worker
should ever touch a filesystem path or boto3 client directly.
"""
import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi.responses import FileResponse

# Backend identifiers persisted on AudioAsset.storage_backend so a
# mixed-migration DB knows where each asset actually lives.
BACKEND_LOCAL = "LOCAL"
BACKEND_S3 = "S3"

STORAGE_ROOT = Path(__file__).resolve().parent / "storage"


@dataclass
class StorageResult:
    key: str          # backend-agnostic canonical key, e.g. "uploads/2026/07/{id}.wav"
    backend: str      # BACKEND_LOCAL now, BACKEND_S3 later
    size_bytes: int
    sha256: str


def upload_key(asset_id: str, ext: str = "wav") -> str:
    """Date-sharded key so no single directory (or S3 prefix) grows unbounded."""
    now = datetime.utcnow()
    return f"uploads/{now:%Y}/{now:%m}/{asset_id}.{ext}"


def save_upload(file_obj, key: str) -> StorageResult:
    """Persist a file-like object at `key`, returning size + integrity hash.

    Streams in chunks and hashes on the way through so we never hold the whole
    clip in memory and the sha256 reflects exactly what hit disk.
    """
    dest = STORAGE_ROOT / key
    dest.parent.mkdir(parents=True, exist_ok=True)

    hasher = hashlib.sha256()
    size = 0
    with open(dest, "wb") as out:
        while True:
            chunk = file_obj.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            hasher.update(chunk)
            size += len(chunk)

    return StorageResult(key=key, backend=BACKEND_LOCAL, size_bytes=size, sha256=hasher.hexdigest())


def get_path(key: str) -> Path:
    """Materialize a key as a local path for processing that genuinely needs a
    file on disk (the DSP loader). (S3: download to temp.) Existence checks,
    reads, and HTTP serving must use exists()/open_read()/audio_response()
    instead — those don't require materialization on a remote backend.
    """
    return STORAGE_ROOT / key


def exists(key: str) -> bool:
    """Whether an object is stored at `key`. (S3: HEAD request.)"""
    return (STORAGE_ROOT / key).exists()


def open_read(key: str):
    """Open the object at `key` for binary reading. Caller (or the consumer it
    hands the stream to) is responsible for closing it. (S3: streaming GET.)
    """
    return open(STORAGE_ROOT / key, "rb")


def audio_response(key: str, media_type: str = "audio/wav"):
    """HTTP response serving the audio object at `key`.

    Local: a FileResponse. (S3: becomes a RedirectResponse to a presigned GET —
    the Phase 3 swap changes only this function, not the routes.)
    """
    return FileResponse(STORAGE_ROOT / key, media_type=media_type)


def save_text(text: str, key: str) -> str:
    """Persist a text blob (e.g. the analysis archive JSON) at `key`.

    Behind the same seam as audio so the Phase 3 S3 swap is one file. Returns
    the key so callers can store it on the row that references it.
    """
    dest = STORAGE_ROOT / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return key


def analysis_key(job_id: str) -> str:
    """Canonical key for a job's coordinate archive (served later by the
    visualizer's GET /jobs/{id}/coordinates endpoint — worker_plan.md §3)."""
    return f"analysis/{job_id}.json"


def delete(key: str) -> None:
    path = STORAGE_ROOT / key
    if path.exists():
        path.unlink()
