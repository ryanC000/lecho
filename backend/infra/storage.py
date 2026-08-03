"""Storage seam.

All audio I/O goes through this module so that swapping local disk for S3 in
Phase 3 is a one-file change behind the same interface. No route or worker
should ever touch a filesystem path or boto3 client directly.
"""
import hashlib
import os
import shutil
import tempfile
import weakref
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi.responses import FileResponse, RedirectResponse

# Backend identifiers persisted on AudioAsset.storage_backend so a
# mixed-migration DB knows where each asset actually lives.
BACKEND_LOCAL = "LOCAL"
BACKEND_S3 = "S3"

STORAGE_ROOT = Path(__file__).resolve().parent / "storage"

# Which backend is live. Plain env with a dev-safe default: local disk unless
# the deployment says otherwise. Bucket/region/endpoint come from env too;
# credentials are left to boto3's own chain (env vars, instance role).
# S3_ENDPOINT_URL points at MinIO/LocalStack so the S3 path is exercisable
# without an AWS account.
BACKEND = os.getenv("STORAGE_BACKEND", BACKEND_LOCAL).upper()
S3_BUCKET = os.getenv("S3_BUCKET", "")
S3_REGION = os.getenv("AWS_REGION") or None
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL") or None
PRESIGN_EXPIRY_S = 3600

CHUNK_BYTES = 1024 * 1024

_client = None


def _s3():
    """The shared S3 client, built on first use so LOCAL never needs credentials."""
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config

        # SigV4 explicitly: botocore still presigns with the legacy SigV2 scheme
        # by default, which regions launched after 2014 reject.
        _client = boto3.client(
            "s3",
            region_name=S3_REGION,
            endpoint_url=S3_ENDPOINT_URL,
            config=Config(signature_version="s3v4"),
        )
    return _client


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


def _stream_hash(file_obj, out) -> tuple:
    """Copy `file_obj` into `out` in chunks, hashing on the way through, so we
    never hold the whole clip in memory and the sha256 reflects exactly what was
    stored. Returns (size_bytes, sha256 hex)."""
    hasher = hashlib.sha256()
    size = 0
    while True:
        chunk = file_obj.read(CHUNK_BYTES)
        if not chunk:
            break
        out.write(chunk)
        hasher.update(chunk)
        size += len(chunk)
    return size, hasher.hexdigest()


def save_upload(file_obj, key: str) -> StorageResult:
    """Persist a file-like object at `key`, returning size + integrity hash.

    Streams in chunks and hashes on the way through so we never hold the whole
    clip in memory and the sha256 reflects exactly what hit disk. (S3: the same
    chunked stream lands in a spooled buffer, which is then put_object'd.)
    """
    if BACKEND == BACKEND_S3:
        with tempfile.SpooledTemporaryFile(max_size=CHUNK_BYTES) as buf:
            size, digest = _stream_hash(file_obj, buf)
            buf.seek(0)
            _s3().put_object(Bucket=S3_BUCKET, Key=key, Body=buf)
        return StorageResult(key=key, backend=BACKEND_S3, size_bytes=size, sha256=digest)

    dest = STORAGE_ROOT / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as out:
        size, digest = _stream_hash(file_obj, out)
    return StorageResult(key=key, backend=BACKEND_LOCAL, size_bytes=size, sha256=digest)


def _unlink(path_str: str) -> None:
    try:
        os.unlink(path_str)
    except OSError:
        pass


class _TempPath(Path):
    """A downloaded copy that deletes itself when the caller drops its last
    reference (see get_path)."""


def get_path(key: str) -> Path:
    """Materialize a key as a local path for processing that genuinely needs a
    file on disk (the DSP loader). (S3: download to temp.) Existence checks,
    reads, and HTTP serving must use exists()/open_read()/audio_response()
    instead — those don't require materialization on a remote backend.

    Under S3 the returned path is a temp copy that cleans itself up once the
    caller stops referencing it, so callers keep the plain "use the path, then
    forget it" contract they have under LOCAL — no caller-side deletion.
    """
    if BACKEND == BACKEND_S3:
        fd, name = tempfile.mkstemp(suffix=Path(key).suffix)
        os.close(fd)
        with open(name, "wb") as out:
            _s3().download_fileobj(S3_BUCKET, key, out)
        path = _TempPath(name)
        weakref.finalize(path, _unlink, name)
        return path
    return STORAGE_ROOT / key


def exists(key: str) -> bool:
    """Whether an object is stored at `key`. (S3: HEAD request.)"""
    if BACKEND == BACKEND_S3:
        from botocore.exceptions import ClientError

        try:
            _s3().head_object(Bucket=S3_BUCKET, Key=key)
            return True
        except ClientError as exc:
            if exc.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
                return False
            raise
    return (STORAGE_ROOT / key).exists()


def open_read(key: str):
    """Open the object at `key` for binary reading. Caller (or the consumer it
    hands the stream to) is responsible for closing it. (S3: streaming GET.)
    """
    if BACKEND == BACKEND_S3:
        return _s3().get_object(Bucket=S3_BUCKET, Key=key)["Body"]
    return open(STORAGE_ROOT / key, "rb")


def audio_response(key: str, media_type: str = "audio/wav"):
    """HTTP response serving the audio object at `key`.

    Local: a FileResponse. S3: a RedirectResponse to a presigned GET, so the
    bytes never pass through the API — the swap is in this function, not in the
    routes.
    """
    if BACKEND == BACKEND_S3:
        url = _s3().generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET, "Key": key, "ResponseContentType": media_type},
            ExpiresIn=PRESIGN_EXPIRY_S,
        )
        return RedirectResponse(url)
    return FileResponse(STORAGE_ROOT / key, media_type=media_type)


def save_text(text: str, key: str) -> str:
    """Persist a text blob (e.g. the analysis archive JSON) at `key`.

    Behind the same seam as audio so the Phase 3 S3 swap is one file. Returns
    the key so callers can store it on the row that references it.
    """
    if BACKEND == BACKEND_S3:
        _s3().put_object(Bucket=S3_BUCKET, Key=key, Body=text.encode("utf-8"))
        return key

    dest = STORAGE_ROOT / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return key


def read_text(key: str) -> str:
    """Read a text blob (e.g. the analysis archive JSON) stored at `key`.

    Symmetric with save_text, behind the same seam. (S3: streaming GET → decode.)
    """
    if BACKEND == BACKEND_S3:
        with _s3().get_object(Bucket=S3_BUCKET, Key=key)["Body"] as body:
            return body.read().decode("utf-8")
    return (STORAGE_ROOT / key).read_text(encoding="utf-8")


def analysis_key(job_id: str) -> str:
    """Canonical key for a job's coordinate archive (served later by the
    visualizer's GET /jobs/{id}/coordinates endpoint — worker_plan.md §3)."""
    return f"analysis/{job_id}.json"


def alignment_key(practice_id: int) -> str:
    """Canonical key for a practice's word-alignment JSON (produced offline by
    align_natives.py, served by GET /practices/{id}/alignment — PRD 8.4)."""
    return f"alignments/{practice_id}.json"


def delete(key: str) -> None:
    if BACKEND == BACKEND_S3:
        _s3().delete_object(Bucket=S3_BUCKET, Key=key)
        return

    path = STORAGE_ROOT / key
    if path.exists():
        path.unlink()
