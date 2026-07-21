# 03 — Docker images and local compose

**What to build:** The backend ships as a Docker image, and `docker compose up` brings up the full
local stack — the FastAPI app, a Postgres service, and a LocalStack/MinIO service for S3 — wired
together by env vars, so a fresh clone runs the production-shaped stack with one command. The image
runs uvicorn; a `.dockerignore` keeps `backend/.venv`, `lecho.db`, and `storage/` out of the build
context. The worker still runs in-process at this stage (the SQS split is 04), so this is one app
image plus backing services. Frontend containerization is out of scope — it stays a Vite dev/static
build.

**Precondition:** `praat-parselmouth` and `numpy` must resolve to Linux (manylinux) wheels inside
the image's base Python — verify at build time, since the Python 3.14 native-build risk applies to
the container's interpreter too. Pin the base image's Python to a version with those wheels
available; record it if 3.14 wheels force a different base.

**Blocked by:** 01 (compose runs Postgres), 02 (compose runs the S3 endpoint).

**Status:** ready-for-agent

- [ ] `docker build` produces a runnable backend image (uvicorn serves `/`)
- [ ] `.dockerignore` excludes `.venv`, `lecho.db`, and local `storage/`
- [ ] `docker compose up` boots app + Postgres + S3 endpoint; a recording scores end-to-end
- [ ] App reaches Postgres and S3 purely via compose-injected env vars (no hardcoded hosts)
- [ ] Image build verifies parselmouth/numpy import at build time
