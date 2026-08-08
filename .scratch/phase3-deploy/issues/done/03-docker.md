# 03 — Docker images and local compose

**What to build:** The backend ships as a Docker image, and `docker compose up` brings up the full
local stack — the FastAPI app, a Postgres service, and a LocalStack/MinIO service for S3 — wired
together by env vars, so a fresh clone runs the production-shaped stack with one command. The image
runs uvicorn; a `.dockerignore` keeps `backend/.venv`, `lecho.db`, and `storage/` out of the build
context. The worker still runs in-process at this stage (the SQS split is 04), so this is one app
image plus backing services.

**Frontend containerization is out of scope**, and the reason is not just phase scoping: a Vite
build is static HTML/CSS/JS with no runtime, and static assets belong on a CDN rather than in a pod
burning cluster memory. It is also **blocked regardless** — `frontend/src/utils/auth.js:5` hardcodes
`API_BASE = 'http://localhost:8000'` and `backend/api/main.py:35` hardcodes the CORS origin, and
Vite bakes env values into the bundle at *build* time. An image built today would be permanently
pinned to localhost. Master-plan ticket 15 (env-config) owns both values and gates any frontend
deployment, containerized or not. See 05 for the hosting decision.

**Precondition:** `praat-parselmouth`, `numpy`, and the DSP deps must resolve to Linux (manylinux)
wheels inside the image's base Python — verify at build time by importing them in the build.

- The **Python 3.14 risk in earlier drafts of this ticket no longer applies**: the project venv is
  **3.12.4**, and psycopg, boto3, and scipy all resolved as prebuilt cp312 wheels. Pin the base
  image to 3.12 to match; record it if you deviate.
- **Master-plan ticket 17 (ambient-noise pipeline) has landed** (`a449200`) and added `scipy` and
  `noisereduce` to `requirements.txt`. The build-time import check must cover both. Note that
  `noisereduce` pulls **matplotlib, Pillow, fonttools, kiwisolver and contourpy** — roughly
  50–60 MB of plotting stack into a headless worker image that will never render a chart. Worth a
  multi-stage build, or revisiting whether the ~30 lines of `scipy.signal` spectral subtraction
  would let the dependency go.
- **If an ARM cluster is a candidate** (Oracle's free tier is ARM64 — see 05), also run
  `docker build --platform linux/arm64` once and confirm parselmouth resolves. numpy and scipy
  publish ARM wheels reliably; parselmouth is the one that could force an x86-only host.

**Blocked by:** nothing — 01 (`0054c05`) and 02 (`23975b5`) are both done and merged.

**Status:** done — `910bd67`, 2026-08-08

- [x] `docker build` produces a runnable backend image — note there is **no `/` route** in
      this app, so uvicorn was verified on `GET /practices` (200, `[]`) instead. Adding a
      root route was out of scope.
- [x] `.dockerignore` excludes `.venv`, `lecho.db`, and local `storage/` — confirmed against
      the running container: `/app` holds only source, and `/app/storage` does not exist.
- [x] `docker compose up` boots app + Postgres + MinIO; a recording scores end-to-end —
      register → login → upload → poll returned SUCCESS at **99.0**, and the coordinates
      endpoint served 43,839 bytes. `native/`, `uploads/2026/08/` and `analysis/` keys all
      confirmed present in the bucket.
- [x] App reaches Postgres and S3 purely via compose-injected env vars — the container
      reports `postgresql+psycopg://lecho:lecho@db:5432/lecho` and `S3 / lecho /
      http://s3:9000`, none of it baked into the image.
- [x] Image build verifies parselmouth/numpy/scipy import at build time — the check also
      covers `noisereduce`, `psycopg` and `boto3`.
- [x] Base image Python recorded (3.12-slim, matching the 3.12.4 venv); ARM64 outcome
      recorded in the Dockerfile header — see below.

**ARM64: parselmouth rules it out.** `docker build --platform linux/arm64` could not run here
(no QEMU binfmt registered), so the question was settled from the package index instead:
`praat-parselmouth` 0.4.7 publishes Linux wheels for **i686 and x86_64 only — no aarch64 at
any Python version**. `numpy`, `scipy`, `psycopg-binary` and `noisereduce` all resolve aarch64
wheels cleanly; parselmouth alone is the blocker. **An ARM host (Oracle's free tier) would
require building Praat's C++ from source — treat the cluster in 05 as x86_64.**

**Carried forward to 04/05 — presigned audio URLs are unreachable from a host browser.**
`GET /practices/{id}/audio` redirects to a URL presigned from `S3_ENDPOINT_URL`, which must be
`http://s3:9000` for the app to reach MinIO on the compose network — and that name does not
resolve outside it. SigV4 signs the host header, so the client cannot rewrite it, and no single
hostname reaches MinIO from both sides (`host.docker.internal` was tried: it resolves in the
container but is unreachable from the Windows host). Server-side scoring is unaffected — it
reads through the same seam inside the network — so this surfaces only once a browser plays
audio against the compose stack. A real fix means splitting the presign endpoint from the API
endpoint in `infra/storage.py`. **Moot on real AWS S3**, whose endpoint is publicly resolvable,
which is what 05 deploys against.

**Not done (advisory, not a checkbox):** the multi-stage build. `noisereduce` still pulls
matplotlib/Pillow/fonttools/kiwisolver/contourpy into the image. Multi-stage would not drop
them — `noisereduce` imports matplotlib at runtime — so the only real win is removing the
dependency, as this ticket already suggested. Left alone.
