"""Clip ingestion: bytes in → stored, validated, catalogued AudioAsset.

The one implementation of "persist audio through the storage seam, derive
authoritative metadata from the real bytes, gate it, and build the AudioAsset
row" shared by the upload route (USER_RECORDING) and the native-clip ingest CLI
(NATIVE_REFERENCE). Asset invariants — sha256, authoritative duration, expiry
policy — live here and nowhere else.

The returned AudioAsset is constructed but not added to any session; callers
own the transaction. On any gate failure the stored object is deleted and
ClipRejectedError is raised carrying both an internal log message and a
user-facing detail.
"""
import audio_meta
import models
import storage


class ClipRejectedError(Exception):
    """A clip failed ingestion gates. `log_message` is for job records/logs;
    `detail` is the user-facing explanation."""

    def __init__(self, log_message: str, detail: str):
        super().__init__(log_message)
        self.log_message = log_message
        self.detail = detail


def ingest_clip(
    file_obj,
    key: str,
    *,
    role: str,
    asset_id: str = None,
    job_id: str = None,
    owner_user_id: int = None,
    client_reported_duration: float = None,
    expires_at=None,
    max_bytes: int = None,
    duration_bounds: tuple = None,
) -> models.AudioAsset:
    result = storage.save_upload(file_obj, key)

    # Size gate (after write we know the real byte count).
    if max_bytes is not None and (result.size_bytes == 0 or result.size_bytes > max_bytes):
        storage.delete(key)
        raise ClipRejectedError(
            "Uploaded audio is empty or exceeds the size limit.",
            "Uploaded audio is empty or too large.",
        )

    # Extract authoritative metadata from the real bytes (not client-trusted).
    try:
        meta = audio_meta.extract_metadata(storage.open_read(key))
    except audio_meta.InvalidAudioError as exc:
        storage.delete(key)
        raise ClipRejectedError(
            f"Invalid audio: {exc}",
            "Uploaded file is not a readable WAV recording.",
        ) from exc

    # Duration gate on the derived duration (PRD FR-1 for user recordings).
    if duration_bounds is not None:
        lo, hi = duration_bounds
        if meta.duration_seconds < lo or meta.duration_seconds > hi:
            storage.delete(key)
            raise ClipRejectedError(
                f"Duration {meta.duration_seconds:.2f}s outside {lo}-{hi}s.",
                f"Recording must be between {int(lo)} and {int(hi)} seconds long.",
            )

    kwargs = {"id": asset_id} if asset_id else {}
    return models.AudioAsset(
        job_id=job_id,
        owner_user_id=owner_user_id,
        role=role,
        storage_key=result.key,
        storage_backend=result.backend,
        size_bytes=result.size_bytes,
        sha256=result.sha256,
        duration_seconds=meta.duration_seconds,
        sample_rate=meta.sample_rate,
        channels=meta.channels,
        codec=meta.codec,
        client_reported_duration=client_reported_duration,
        expires_at=expires_at,
        **kwargs,
    )
