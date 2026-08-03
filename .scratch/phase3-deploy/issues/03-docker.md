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

**Status:** ready-for-agent

- [ ] `docker build` produces a runnable backend image (uvicorn serves `/`)
- [ ] `.dockerignore` excludes `.venv`, `lecho.db`, and local `storage/`
- [ ] `docker compose up` boots app + Postgres + S3 endpoint; a recording scores end-to-end
- [ ] App reaches Postgres and S3 purely via compose-injected env vars (no hardcoded hosts)
- [ ] Image build verifies parselmouth/numpy/scipy import at build time
- [ ] Base image Python recorded; ARM64 build outcome recorded if an ARM host is under consideration
