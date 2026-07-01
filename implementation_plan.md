# L'Écho — Implementation Plan

**Companion to:** `design_document.md` (v1.1.0)
**Purpose:** (1) audit what the codebase actually does today against the PRD, (2) lay out a phased build-out from the current local MVP to the PRD's full target architecture.

Decisions this plan assumes (from PRD v1.1.0, Section 8): F0 + RMS, both speaker-normalized (semitones / z-score) before scoring; prosody-only scope, no STT word-checking; local-first now, AWS migration deferred to Phase 3; Phase 3 autoscaling defaults to a 5-instance cap pending real usage data.

---

## Part 1 — Current State Audit

This is what the repository does today, verified against the code (not assumed).

### What actually works end-to-end
- **Practice catalog:** `GET /practices`, `GET /practices/{id}` (backend/main.py) backed by real SQLite rows, seeded via `backend/seed.py`. Dashboard and Library pages fetch this via React Router loaders (`frontend/src/App.jsx`) and render real data.
- **Auth (backend only):** `POST /auth/register`, `POST /auth/login` are real — bcrypt password hashing (`auth.py`), JWT issuance with a `jti` claim and a `revoked_tokens` table for future logout support.
- **Recording capture:** `Recorder.jsx` genuinely captures microphone audio via `MediaRecorder`, does a client-side silence check, and enforces the ±20% duration bound before calling `onUpload`.

### What's mocked, disconnected, or missing (in order of impact)

1. **The audio never leaves the browser.** `Practice.jsx`'s `handleUpload` takes the recorded `Blob`, does `URL.createObjectURL(audioBlob)` for local playback, and then just `setTimeout(... navigate('/results/:id'), 1500)`. It never calls `fetch('/jobs', ...)`. So FR-2 (async job lifecycle) and FR-1 (ingestion) are unimplemented on the client side, despite the backend having real endpoints for it.
2. **There is no login/register UI at all.** No `/login` or `/register` route in `App.jsx`, no form components in `frontend/src/pages`, and no token storage (no `localStorage`/cookie code anywhere in the frontend). This means even if step 1 were wired up, `POST /jobs` would 401 immediately — it requires `Depends(auth.get_current_user)`, a Bearer JWT the frontend has no way to obtain or attach.
3. **Results page shows fabricated data, and its own data-loading is wired to the wrong resource.** `Results.jsx` hardcodes `results = { score: 85.5, segments: [...] }` directly in the component (lines 10–27) — it never calls `GET /jobs/{job_id}`. Separately, its router loader (`App.jsx` line 82) fetches `/practices/${params.jobId}` — i.e., it treats a job UUID as if it were a practice's integer primary key. Against real data this would 404. Right now it "works" only because the mocked job ID happens to collide with a valid practice ID during manual testing.
4. **The worker is fully mocked, twice, in two disconnected places.** `backend/main.py`'s `mock_worker_task` sleeps 5s and hardcodes `overall_match_score = 85.5` — every job gets the identical score regardless of input audio. Separately, `worker/main.py` has its own `process_audio()` that also fabricates F0/RMS arrays and writes a local JSON file — but it is **never imported or called by the backend.** It's a standalone test script (its `if __name__ == "__main__"` block is the only thing that runs it). No real DSP library (Parselmouth, Librosa, SciPy, NumPy, noisereduce) appears in `backend/requirements.txt`, and `worker/` has no requirements file of its own — consistent with no real signal processing existing yet anywhere in the repo.
5. **No audio is ever stored anywhere.** `JobCreate` (schemas.py) only carries `practice_id` and `user_audio_duration` — never the audio file itself. `ProsodyJob.user_s3_path` is hardcoded to the literal string `"mock-s3-upload-path/audio.wav"` on every job (main.py line 98) — it isn't a real path, a real upload, or even a unique value per job.
6. **The PRD's absolute duration bound (FR-1: 2s–15s) isn't implemented.** Only the *relative* ±20%-of-native-clip bound exists (`Recorder.jsx` and `main.py`, matching PRD v1.1.0's Section 6 edge case now that it's reconciled). If a native clip itself is very short, ±20% of it could still permit a sub-2-second recording. Worth an explicit backend check.
7. **`seed.py`'s test user can't actually log in.** It inserts `password_hash="dummy_hash"` directly (seed.py line 86) instead of a real bcrypt hash. `passlib`'s `verify_password` will fail to identify this as a valid hash scheme rather than gracefully rejecting it — this is a seed bug, not a design gap, but it means "log in as the seeded user" doesn't work out of the box.
8. **No reconnect/resync behavior.** PRD Section 6 edge case #3 (client reconnects after a dropped connection, dashboard should reflect the job's current status) has nothing implemented — no polling loop, no `errorElement` on the router, no status page.
9. **No tests anywhere** — no `pytest` files under `backend/`, no test runner configured in `frontend/package.json` beyond the default Vite/ESLint scaffold.
10. **Minor:** CORS is hardcoded to `http://localhost:5173` only (fine for now, flagged for Phase 2); no `/auth/logout` endpoint despite `RevokedToken` existing in the schema; JWT secret falls back to a hardcoded default string if `JWT_SECRET_KEY` isn't set, with no `.env.example` documenting required variables.

**Bottom line:** the frontend and backend were built in parallel and never actually connected for the core recording→scoring loop. The demo currently "works" only because every screen either doesn't call the real API or the real API always returns the same hardcoded, non-representative result.

---

## Part 2 — Phase 1: Make the Local MVP Real

**Goal:** a user can record audio, have it genuinely processed (real F0/RMS extraction, real DTW, real normalized scoring against the actual native clip), and see a result that reflects their actual recording — all running locally, no AWS.

### 1.1 Backend: real audio ingestion
- Change `POST /jobs` to accept multipart file upload (`UploadFile`) alongside `practice_id`, not just a duration number.
- Store the uploaded file to local disk under `backend/storage/uploads/{job_id}.wav` (create a thin `storage.py` module with `save_upload()` / `get_path()` functions now, so Phase 3's swap to S3 is a one-file change behind the same interface).
- Replace the hardcoded `user_s3_path` literal with the real path returned by `storage.py`.
- Add the missing absolute 2s–15s duration check server-side (belt-and-suspenders alongside the ±20% relative check).

### 1.2 Worker: real DSP
- Add `parselmouth` (or `librosa`) + `numpy` + `scipy` to a new `worker/requirements.txt`.
- Rewrite `worker/main.py`'s `process_audio()` to:
  1. Load native clip (from `frontend/public` or wherever native samples live — confirm/introduce a native-audio storage convention; today `Practice.audio_url` is often null and the frontend falls back to `generateMockAudioBlob`, so real native audio files need to be sourced or recorded for at least the seeded practices) and the user's uploaded clip.
  2. Extract F0 via Parselmouth's pitch-tracking (`sound.to_pitch()`), extract RMS via short-time energy windows.
  3. Apply the semitone / z-score normalization from PRD FR-3.
  4. Run DTW (e.g. `dtaidistance` or a hand-rolled DP alignment) with the 3:1 length-ratio safety abort from PRD Section 6.
  5. Compute the weighted score (70/30 pitch/energy default) and derive feedback segments (threshold-based tagging: `INTONATION_DROP`, `SYLLABLE_STRETCH`, `ENERGY_FLAT`, `EMPHASIS_MISSED`).
  6. Write the aligned/normalized arrays to `backend/storage/analysis/{job_id}.json` (the "hybrid archive" pattern now documented in the PRD schema note), and return the score + segments.
- Wire this real `process_audio()` into `backend/main.py`, replacing `mock_worker_task` entirely. Keep using `BackgroundTasks` for now (Phase 3 replaces this with SQS + a separate container) but make it call the real function.
- Persist `AnalysisSegment` rows (currently defined in `models.py` but never written to by any code path).

### 1.3 Frontend: wire the actual loop
- Build `Login.jsx` / `Register.jsx` pages, add `/login` and `/register` routes, store the JWT (recommend an httpOnly-cookie pattern if the backend can set one, or `localStorage` as the pragmatic MVP choice with a documented XSS caveat), and attach `Authorization: Bearer <token>` to all authenticated fetches.
- `Practice.jsx`: replace the fake `setTimeout` in `handleUpload` with a real `fetch('/jobs', { method: 'POST', body: formData, headers: {Authorization} })`, then navigate to `/results/:jobId` using the **real job ID** returned from that call.
- `Results.jsx`: fix the router loader to call `GET /jobs/{job_id}` (not `/practices/{jobId}`), add a polling loop (e.g. `setInterval` every 2s while `status !== 'SUCCESS'/'FAILED'`) since the job is genuinely async now, and render the real score/segments instead of the hardcoded object.
- Add an `errorElement` to the router and a friendly "reconnecting…" / retry state, addressing PRD edge case #3.

### 1.4 Fix the seed bug
- `seed.py`: replace `password_hash="dummy_hash"` with `auth.get_password_hash("some_known_dev_password")` and document the dev login credentials in `README.md`.

**Acceptance criteria for Phase 1:** A fresh clone can `pip install -r backend/requirements.txt && python seed.py && uvicorn main:app`, `npm install && npm run dev` on the frontend, register a real account, record a real clip against a real native sample, and see a results page whose score and feedback segments visibly differ between a good recording and a deliberately bad one (e.g., flat monotone reading vs. an expressive one). That last part — score varying with actual input — is the single clearest signal Phase 1 is done, since today the score is a constant.

---

## Part 3 — Phase 2: Hardening

**Goal:** the local MVP is reliable enough to hand to real test users (a class, a few actors), not just a solo demo.

- **Testing:** backend `pytest` coverage for the job lifecycle (create → mock-free process → fetch status), and at least one DSP unit test with a synthetic sine-wave pair with a known pitch offset, asserting the scorer produces the expected relative score. Frontend: component tests for `Recorder` (duration validation logic) and an integration test for the record→submit→poll→result flow (e.g. Playwright/Cypress against the real backend, or MSW-mocked).
- **Auth completeness:** `POST /auth/logout` that actually inserts into `revoked_tokens` (the table exists and is checked on every request already — it's just never written to).
- **Config hygiene:** `.env.example` documenting `JWT_SECRET_KEY` and any storage paths; CORS origins read from an env var instead of hardcoded.
- **Native audio sourcing:** decide how real native reference clips get into the system for each seeded `Practice` row (record them, license them, or generate via TTS as a placeholder) — right now most fall back to `generateMockAudioBlob`, a synthetic tone, which cannot produce a meaningful prosody comparison.
- **Observability:** structured logging for job state transitions and DSP failures (today a DSP exception would just hang the background task silently).
- **Ambient-noise pipeline (PRD Section 6, edge case #1):** implement the bandpass filter + `noisereduce` spectral subtraction + SNR check described in the PRD — none of this exists yet even as a mock.

---

## Part 4 — Phase 3: Cloud Migration

**Goal:** the architecture described in `design_document.md` Section 4 — done last, once the DSP algorithm and UX are validated locally and don't need to keep changing.

- Swap `storage.py`'s local-disk implementation for S3 (pre-signed upload URLs for the frontend, so `POST /jobs` returns a real presigned URL instead of the current mock string — this is the point where `JobResponse.user_s3_path` finally means what the PRD says it means).
- Introduce SQS between the API and the worker; extract the worker into its own container (image already conceptually separate as `worker/`, just needs a `Dockerfile` and to actually consume from a queue instead of running in-process).
- Migrate SQLite → PostgreSQL (models are already SQLAlchemy, so this should mostly be a connection-string and dialect-specific-type change, e.g. confirm no SQLite-only column types are in use).
- Terraform for: RDS (Postgres), SQS queue, S3 buckets (with the 30-day lifecycle rule from PRD Section 4), ECS/EC2 worker fleet with autoscaling on queue depth, **capped at 5 instances by default** (PRD Section 8.3 — revisit once Phase 1/2 usage data exists).
- CI/CD: Docker images + a Git-triggered pipeline (GitHub Actions is the natural fit given the repo's already on GitHub).

---

## Part 5 — Backlog (not scheduled)
- Chatbot recommending practice clips by level/preference (PRD Section 9).
- Word-correctness checking via STT (explicitly out of scope per PRD Section 8.2 — would need its own phase if prioritized later).

---

## Open Assumptions Log
- **Autoscaling cap of 5 instances (Phase 3):** a placeholder default, not derived from real load data. Revisit once Phase 1/2 shows actual concurrent-submission patterns.
- **JWT storage strategy (Phase 1.3):** `localStorage` is the pragmatic default called out above; if this product ever handles more sensitive data, revisit in favor of httpOnly cookies + CSRF protection.
- **Native audio sourcing (Phase 2):** how real reference clips get produced/licensed is unresolved and blocks any meaningful DSP validation — flagged, not decided, in this plan.
