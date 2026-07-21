# 02 — S3 storage backend

**What to build:** Implement the `BACKEND_S3` path that [storage.py](../../../backend/storage.py)
was designed around — every method already documents its S3 equivalent in a comment, so this is the
one-file swap the seam promised, not a route change. A `STORAGE_BACKEND` env var (`LOCAL` default)
selects it; bucket, region, and credentials come from env. Per method: `save_upload`/`save_text`
stream a `put_object` and keep returning the same `StorageResult`/key; `exists` is a `HEAD`;
`open_read`/`read_text` are a streaming `GET`; `audio_response` returns a `RedirectResponse` to a
**presigned GET** (as the docstring specifies); `get_path` downloads to a temp file for the DSP
loader (the one place that genuinely needs a local path) and the caller cleans it up. No route,
worker, or ingest caller changes — they already go through the seam. `StorageResult.backend` must
record `BACKEND_S3` so a mixed-migration DB knows where each asset lives.

**Precondition:** `boto3` must install as a prebuilt wheel. Local/CI testing uses a
MinIO or LocalStack S3 endpoint via an optional `S3_ENDPOINT_URL` override — no real AWS account
needed to exercise the path.

**Blocked by:** None — can start immediately. Enables 04 (worker container needs shared storage).

**Status:** ready-for-agent

- [ ] `STORAGE_BACKEND=S3` round-trips an upload: save → exists → read → serve
- [ ] `audio_response` issues a presigned redirect, not a file stream, under S3
- [ ] `get_path` materializes to temp and the temp file is cleaned up after use
- [ ] No caller outside `storage.py` changed; leak grep for raw S3/boto3 usage is clean
- [ ] Full pytest suite green against a LocalStack/MinIO endpoint
