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
    """Resolve a key to a local path the worker can open. (S3: download to temp.)"""
    return STORAGE_ROOT / key


def delete(key: str) -> None:
    path = STORAGE_ROOT / key
    if path.exists():
        path.unlink()


def presign_put(key: str):
    """Return a presigned upload URL. No-op locally; real URL in Phase 3 (S3)."""
    return None
