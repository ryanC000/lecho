# L'Écho — Master Implementation Plan (end-to-end monolith)

**Companion to:** `design_document.md` (PRD v1.2.0), `implementation_plan.md`, `worker_plan.md`
**Status:** live execution document — supersedes the phase breakdown in `implementation_plan.md` Parts 2–5.
**Audience:** coding agents executing tasks step by step. Each task is self-contained: Goal / Files / Steps / Contracts / Verify / Complications. Do not start a task whose dependencies (listed per task or in the execution-order section at the bottom) are unfinished.

## How to use this file

- Work one task at a time, in the order given by the **Suggested execution order** section (parallel tracks allowed).
- **🧑 HUMAN GATE** sections are tasks only the project owner can do (voice recordings, cloud-console setup). Agents must stop at a gate for the tasks that depend on it and pick up an independent track instead.
- **Stage 6 is SPEC-ONLY**: fully specified but must not be executed until the owner explicitly triggers it.
- When a task changes a placeholder constant or resolves a decision, append a line to the **Decision log** at the bottom.
- Follow `CLAUDE.md` (surgical changes, simplicity first, conventional commits).

## Current state (verified audit, commit `426e41c`, 2026-07-07)

Already working — do not rebuild:
- Full core loop: register/login (JWT in localStorage) → record (`Recorder.jsx`, capture constraints off: `echoCancellation/noiseSuppression/autoGainControl: false`) → client WAV transcode (`utils/audio.js::blobToWav`) → multipart `POST /jobs` (auth, ±20% relative gate, absolute 2–15s gate on server-derived duration, WAV check, 10MB cap) → `AudioAsset` persisted (sha256, 30-day expiry) → in-process `BackgroundTasks` `worker_task` → `Results.jsx` polls `GET /jobs/{id}` every 2s (score, segments, FAILED + retryable states).
- **`dsp-2` is implemented** in `backend/dsp.py`: joint DTW cost (`|Δsemitone| + 0.5·|Δenergy_norm| + diag-pull`, Sakoe-Chiba 15%, step penalty), timing score from warping-path local slope, `score()` returns `(overall, pitch, timing, energy)`, weights 0.55/0.25/0.20, all six tags (`INTONATION_DROP`, `ENERGY_FLAT`, `EMPHASIS_MISSED`, `SYLLABLE_STRETCH`, `PAUSE_MISSED`, `PAUSE_EXTRA`). `ALGO_VERSION = "dsp-2"` lives in `backend/main.py` (~line 102).
- `backend/ingest_native.py` CLI (16k mono conversion, 2.5–12.5s window, `native/{practice_id}.wav`, sets `Practice.audio_url` + `duration`); `GET /practices/{id}/audio` serves clips; mock-tone trap removed; stale `worker/main.py` deleted.
- `backend/test_dsp.py`: 6 passing dsp-1 synthetic tests. `backend/test_dsp2.py`: 6 dsp-2 tests **written but never run/verified** (Task 0.1).

Known-missing (what this plan builds): test_dsp2 reconciliation, per-axis score persistence, calibration harness + human corpus (PRD 8.9), MFA word alignment (PRD 8.4), shadow mode + bleed gate (PRD 8.7 / Edge Case 3), `GET /jobs/{id}/coordinates` + pitch visualizer, logout, Google OAuth, env config, logging, noise pipeline, API/frontend tests, job history, a11y, Phase 3 cloud.

Binding decisions (owner, 2026-07-07): Phase 3 spec-only; human recordings via explicit gates; MFA via its own conda env; real self-hosted Google OAuth (custom JWT stays, no Firebase).

## Conventions

- Repo root: `c:\Users\ryanc\lecho`. Backend venv: `backend/.venv` (Python 3.14, Windows). Frontend: Vite (`cd frontend && npm run dev`).
- **Windows / Python 3.14 dependency rule:** only deps with prebuilt cp314 wheels or pure-Python (this is why DTW is hand-rolled and `bcrypt==4.0.1` is pinned). Check every new dep first: `pip install --only-binary :all: <pkg>` in a throwaway; if it fails, stop and record the blocker.
- **Schema changes (no Alembic until Phase 3):** all column additions go through `backend/migrations.py` (created in Task 0.2) — an idempotent list of `(table, column, DDL)` applied at app startup via `PRAGMA table_info` checks. Never solve a schema change by deleting `lecho.db` — that destroys ingested native-clip rows.
- Run backend: `cd backend && .venv\Scripts\uvicorn main:app --reload`. Backend tests: `cd backend && .venv\Scripts\python -m pytest -x -q`.
- Storage keys (local seam `backend/storage/`, S3-swappable in Phase 3): `uploads/{YYYY}/{MM}/{asset_id}.wav`, `native/{practice_id}.wav`, `analysis/{job_id}.json`, **new** `alignments/{practice_id}.json`.

---

## Stage 0 — dsp-2 reconciliation & repo hygiene *(do first; everything downstream trusts these)*

### Task 0.1 — Verify and reconcile `test_dsp2.py`
- **Goal:** the 6 dsp-2 tests pass and describe reality; dsp-2 is confirmed working.
- **Files:** `backend/test_dsp2.py`, possibly `backend/dsp.py`.
- **Steps:** run `pytest test_dsp.py test_dsp2.py -v`. Fix any failures (the tests: identical-clips all 4 components >95; 500ms shadow-lag overall/timing ≥85; uniform 1.15× tempo not penalized; internal 2× stretch penalized + `SYLLABLE_STRETCH`; `PAUSE_MISSED`; `PAUSE_EXTRA`). Rewrite the stale module docstring (~lines 9–15), which still claims dsp-2 "does not exist yet". If a test fails, fix `dsp.py` constants/logic only if the test's physical claim is sound — otherwise fix the test and record why in the commit message.
- **Verify:** all 12 tests green.
- **Complications:** the shadow-lag test gates Stage 3's Sakoe-Chiba assumption (15% band tolerates 500ms lag). If it fails, widen `SAKOE_CHIBA_BAND_FRAC` — the documented remedy (PRD 8.7) — never relax the test.

### Task 0.2 — Persist per-axis scores + startup migrations
- **Goal:** `pitch_score`/`timing_score`/`energy_score` (computed in `worker_task`, currently discarded) are stored and served.
- **Files:** new `backend/migrations.py`; `backend/models.py` (3 nullable `Float` columns on `ProsodyJob`); `backend/main.py` (worker_task persists them, rounded 1dp; call `migrations.run(engine)` at startup); `backend/schemas.py` (`JobStatusResponse` gains the three fields); `frontend/src/pages/Results.jsx` (three small sub-score stats under the AccuracyRing).
- **`migrations.py` shape:** `MIGRATIONS = [("prosody_jobs", "pitch_score", "FLOAT"), ...]`; `run(engine)` checks `PRAGMA table_info(<table>)` and executes `ALTER TABLE <table> ADD COLUMN <col> <ddl>` for missing columns only.
- **Contract:** `GET /jobs/{id}` SUCCESS payload adds `"pitch_score": float|null, "timing_score": float|null, "energy_score": float|null` (null for pre-existing rows).
- **Verify:** pytest passes; a manual job run shows sub-scores in the API response and the UI.

### Task 0.3 — Repo hygiene
- **Steps:** `git rm --cached backend/lecho.db` (tracked despite `*.db` in `.gitignore`); commit. In `frontend/src/App.jsx`, the three route loaders (~lines 108/112/118) hardcode `http://localhost:8000` — import `API_BASE` from `utils/auth.js` instead (env-var-ification comes in Task 5.3; this just removes the duplication).
- **Verify:** `git ls-files | findstr lecho.db` empty; app still loads practices.

---

## Stage 1 — Calibration (PRD 8.9) — definition of done for dsp-2 scoring

### Task 1.1 — Build the calibration harness (before the recordings exist)
- **Goal:** a CLI that, given a corpus manifest, checks owner-emulation ≥ 75 and monotone ≥ 20 points lower, and helps tune constants (ADR 0002 — no second native speaker exists; leniency is bounded by the discrimination margin).
- **Files:** new `backend/calibrate.py`; new `backend/test_calibration.py` (pytest, `skipif` manifest missing).
- **Manifest contract** — `native_audio/calibration/manifest.json` (dir already gitignored), paths relative to the manifest, ≥3 entries required for graduation:
  ```json
  [{"practice_id": 7, "reference": "p7_native.wav", "emulation": "p7_emulation.wav", "monotone": "p7_monotone.wav", "low_effort": "p7_low_effort.wav"}]
  ```
  `low_effort` is optional (≥1 entry should have it) and is a diagnostic row only — printed in the table, never a tuning constraint.
- **Steps:** `calibrate.py` runs the pure dsp pipeline (no HTTP/DB): `load_mono_16k → extract_features → trim_silence → align → score` for (emulation vs reference), (monotone vs reference), and any (low_effort vs reference) per entry; prints a table of all four score components. `--tune` grid-searches `SCORE_K_PITCH_SEMITONES`, `SCORE_K_TIMING`, `SCORE_K_ENERGY_Z`, `DTW_ENERGY_LAMBDA`, and the weights, maximizing the emulation-vs-monotone margin subject to emulation ≥ 75; prints recommended constants (a human applies them to `dsp.py` deliberately — no auto-edit). `--smoke` runs on synthetic WAVs (reuse `test_dsp.py` helpers) so the harness is testable before the corpus exists.
- **Verify:** `python calibrate.py --smoke` runs end to end.
- **Complications:** the Phase 1R real-audio finding (low-effort take outscored mid-effort; learner median F0 ~115Hz near the 75Hz pitch floor → creak/octave-error risk) means `--tune` should also try `PITCH_FLOOR_HZ` ∈ {60, 65, 75} as a diagnostic. Record the outcome in the Decision log.

### 🧑 HUMAN GATE H1 — record the calibration corpus
- **Owner must record, for ≥3 practices:** a best-effort **emulation take** — recorded shadow-style, listening to the native clip on headphones while speaking along — and a deliberate **monotone take** of the same line (plus one **low-effort take** for at least one practice), as WAVs in `native_audio/calibration/`, and fill `manifest.json` (ADR 0002). Headphones are mandatory: these WAVs bypass the app's bleed gate. Practice 7's original reference may need re-ingesting first (no `storage/` dir exists on this machine — re-run `ingest_native.py` for practice 7).
- **Blocks:** Task 1.2 only. All other tracks proceed.

### Task 1.2 — Run calibration, graduate the constants *(blocked on H1)*
- Run the harness, apply tuned constants to `dsp.py`, re-run all pytest (update `test_dsp2.py` thresholds if constants shifted), bump `ALGO_VERSION` to `dsp-2.1`, record final values in the Decision log.

### 🧑 HUMAN GATE H2 — record/collect native clips for remaining practices
- Ingest each via `python ingest_native.py --practice-id N path.wav`. Blocks nothing in code; blocks only "all practices usable" acceptance.

---

## Stage 2 — Word alignment (MFA, PRD 8.4)

### Task 2.1 — MFA environment + alignment script
- **Goal:** `storage/alignments/{practice_id}.json` word timings for every ingested native clip.
- **Files:** new `scripts/align_natives.py` (repo-root `scripts/`); new `scripts/README_MFA.md` (conda setup).
- **Setup (documented, one-time):** install Miniconda → `conda create -n mfa -c conda-forge montreal-forced-aligner` → `mfa model download acoustic french_mfa` + `mfa model download dictionary french_mfa`. **Never pip-install MFA into the 3.14 venv.** Owner-approved 2026-07-11: the agent performs this install itself (user-scope Miniconda) when Track B starts — not a human gate.
- **Steps:** the script reads the DB for practices with `audio_url`, builds a temp MFA corpus dir (`{id}.wav` copied from storage + `{id}.txt` transcript, normalized: lowercase, strip punctuation except apostrophes/hyphens, spell out digits), shells out `conda run -n mfa mfa align <corpus> french_mfa french_mfa <out> --clean`, parses each output TextGrid with a small pure-Python parser (~40 lines; "words" tier only; skip empty/`<eps>` intervals), writes via the `storage.py` seam.
- **Alignment JSON contract (fixed — hand-authored files must be drop-in identical):**
  ```json
  {"practice_id": 7, "source": "mfa", "model": "french_mfa",
   "words": [{"word": "on", "start": 0.31, "end": 0.42}]}
  ```
  `words` sorted by `start`, non-overlapping, seconds on the native clip's timeline (which is the analysis timeline — DTW projects the user onto it).
- **Verify:** run against practice 7; word count matches transcript; spot-check timings by ear.
- **Complications:** MFA on Windows is conda-only. If MFA misbehaves on short conversational clips, hand-author the JSON (`"source": "manual"`) — every downstream consumer is coupled to the contract, not to MFA.

### Task 2.2 — Serve alignments + word-anchor the feedback segments
- **Files:** `backend/main.py` (new `GET /practices/{practice_id}/alignment` — no auth, like the audio route; 404 if missing. In `worker_task`, after `make_segments`, load the alignment if present and attach words); `backend/models.py` + `migrations.py` (`AnalysisSegment.words` — `Text`, JSON-encoded list of strings, nullable); `backend/schemas.py` (`SegmentResponse.words: Optional[List[str]]`); `frontend/src/pages/Results.jsx` (segment cards show "on **les amis**" — words joined, timestamps demoted to secondary text; unchanged rendering when `words` is null).
- **Word-mapping rule (worker):** a word belongs to a segment iff `word.start < seg.timestamp_end and word.end > seg.timestamp_start` (interval overlap). No overlapping words → `words = null`.
- **Verify:** re-run a job on practice 7 post-alignment; segments carry words; old jobs still render.

---

## Stage 3 — Shadow mode (PRD 8.7 + Edge Case 3)

### Task 3.1 — Backend: `mode` field + per-mode duration gates
- **Files:** `backend/main.py`; `backend/models.py` + `migrations.py` (`ProsodyJob.mode`, String, default `"solo"`); `backend/schemas.py` (expose `mode` in `JobStatusResponse`).
- **Contract:** `POST /jobs` gains `mode: str = Form("solo")`, allowed `{"solo","shadow"}` (400 otherwise). Gates — applied to the client-reported duration as fast-fail, then re-applied to the server-derived duration as authoritative (the existing two-layer pattern):
  - solo: within ±20% of `practice.duration` (unchanged);
  - shadow: `|duration − (practice.duration + 1.0)| ≤ 0.5` — constants `SHADOW_TAIL_S = 1.0`, `SHADOW_TOLERANCE_S = 0.5` in `main.py`. The absolute 2–15s gate is unchanged for both.
- **Verify:** pytest cases for both gates (use Task 5.6 scaffolding if it exists; otherwise a minimal `TestClient` test here).

### Task 3.2 — Worker bleed gate (hard gate — a bled take must never be scored)
- **Files:** `backend/dsp.py` (new `BleedDetectedError(DspError)`; new pure fn `detect_bleed(native_samples, user_samples, sr) -> float` returning peak NCC; constants `NCC_BLEED_THRESHOLD = 0.5`, `BLEED_MAX_LAG_S = 1.5`); `backend/main.py` (`worker_task`: when `job.mode == "shadow"`, run `detect_bleed` on the raw 16k mono arrays **before** feature extraction; peak > threshold → FAILED, retryable, message: "It sounds like the native audio was picked up by your microphone. Please use headphones for shadow takes, or switch to Solo mode.").
- **Algorithm (numpy only — scipy is not yet a dep):** zero-mean both signals; cross-correlate via FFT (`np.fft.rfft`, zero-padded to `len(a)+len(b)-1`); for lags in `[0, BLEED_MAX_LAG_S·sr]`, normalize each lag's correlation by the product of the L2 norms of the overlapping windows (from cumulative-sum-of-squares arrays — O(n log n) total); return the max. Rationale for 0.5: a learner *imitating* the clip correlates weakly in the raw waveform domain (different voice/phase); actual playback leakage correlates strongly.
- **Verify:** unit tests in `test_dsp2.py`: (a) user = native mixed at −10dB into noise ⇒ detected; (b) independent synthetic speech-like signal ⇒ not detected.

### Task 3.3 — Frontend: shadow capture
- **Files:** `frontend/src/pages/Practice.jsx`, `frontend/src/components/Recorder.jsx`.
- **Steps:** mode toggle (Shadow default, Solo fallback), persisted in `sessionStorage`. Before the first shadow take of a session: headphones confirmation modal (PRD §5 copy: "Shadowing plays the native clip while you record — use headphones so your mic only hears you"), remembered in `sessionStorage`. Shadow take: fetch+decode the native clip into an `AudioBuffer` on one `AudioContext`; on Start, `AudioBufferSourceNode.start(t0)` and `mediaRecorder.start()` back-to-back on the same context clock; auto-stop (checked against context time) at `native_duration + 1.0`; then the existing `blobToWav → onUpload` path unchanged. Client duration gate switches per mode (mirror Task 3.1 numbers). `handleUpload` appends `formData.append('mode', mode)`. **Solo mode is untouched.**
- **Verify:** manual — a headphones shadow take succeeds; a laptop-speaker take gets the worker's bleed rejection and Results shows the retryable message.
- **Complications:** MediaRecorder start latency (~tens of ms) is absorbed by silence-trim + DTW — do not compensate. Do **not** route mic input to the AudioContext output (feedback loop); the existing AnalyserNode tap for LiveWaveform is fine.

### Task 3.4 — Karaoke transcript highlighting *(depends on Task 2.2)*
- **Files:** `Practice.jsx` + new `frontend/src/components/TranscriptKaraoke.jsx`, consuming `GET /practices/{id}/alignment` (fetched in the route loader alongside the practice; tolerate 404 → feature off).
- **Steps:** during native playback (both modes — wavesurfer emits `timeupdate`/`audioprocess` with `currentTime`; in shadow mode use `audioContext.currentTime − t0`), highlight the word whose `[start, end)` contains the current time. Match transcript tokens to alignment words by normalizing both the same way as Task 2.1 and matching sequentially, skipping punctuation-only tokens.

---

## Stage 4 — Pitch-overlay visualizer (the PRD's "Insight Consumption" step)

### Task 4.1 — `GET /jobs/{job_id}/coordinates`
- **Files:** `backend/main.py`.
- **Contract:** auth-required, owner-scoped (404 if not the caller's job, matching `GET /jobs/{id}`), 409 if the job is not SUCCESS, else returns the archive JSON verbatim. Archive keys (produced by `dsp.build_archive`, `dsp.py` ~line 618 — **do not change them**): `times`, `native_f0_hz`, `user_f0_hz_aligned`, `native_semitone`, `user_semitone_aligned`, `native_rms`, `user_rms_aligned`, `voiced_masks: {native, user_aligned}`. All arrays share `len(times)` (≲1500 points).
- **Verify:** pytest — owner gets equal-length arrays; non-owner gets 404.

### Task 4.2 — Results-page pitch chart (hand-rolled SVG — no new dependency)
- **Files:** new `frontend/src/components/PitchChart.jsx`; `Results.jsx` fetches coordinates on SUCCESS.
- **Spec:** responsive SVG line chart, x = `times` (s), y = Hz. Native contour in the neutral color, user contour in the accent color; **blank (never interpolate) frames where the respective voiced mask is false**; color user-line segments by deviation `|native_semitone − user_semitone_aligned|` ≥ 2.0 semitones → warning color (same constant as `SEGMENT_PITCH_THRESHOLD_SEMITONES`); word labels on the x-axis from the alignment JSON (skip on 404); a11y: a rendered text list summarizing each flagged region (reuse the segments data), per PRD §5.
- **Depends on:** 4.1; word labels degrade gracefully without Stage 2.
- **Verify:** manual on a real job; vitest render test with fixture data once 5.6 exists.

---

## Stage 5 — Auth completion & hardening

### Task 5.1 — `POST /auth/logout`
- **Files:** `backend/main.py`; `frontend/src/utils/auth.js` + `App.jsx` navbar.
- **Steps:** the endpoint decodes the presented token (`jti` already exists in every token — `auth.py:36`; the `RevokedToken` table + per-request check are already live), inserts `RevokedToken(jti, expires_at=token exp)`, returns 204. Frontend logout calls it best-effort (still `clearToken()` on failure). Housekeeping: at startup, delete `RevokedToken` rows with `expires_at < now` so the table can't grow unbounded.
- **Verify:** pytest — token works → logout → same token 401s.

### Task 5.2 — Google OAuth (self-hosted, Google Identity Services ID-token flow)
- **Approach:** frontend loads the GIS script (`https://accounts.google.com/gsi/client`), renders the official button (replacing the mock at `AuthModal.jsx` ~156–164), receives an ID-token `credential`, and `POST /auth/google {"credential": "..."}`. Backend verifies with **`google-auth`** (pure-Python; confirm with `pip install --only-binary :all: google-auth` first): `google.oauth2.id_token.verify_oauth2_token(credential, requests.Request(), GOOGLE_CLIENT_ID)`; require `email_verified`; find-or-create `User`; return the same `Token` schema (app JWT). No redirect/callback flow to host; still fully self-hosted (no Firebase).
- **Files:** `backend/main.py` (+`/auth/google`); `backend/auth.py` (verification helper); `backend/models.py` (`User.password_hash` → nullable; `User.auth_provider` String default `"password"` via `migrations.py`); `backend/requirements.txt` (+`google-auth`); `frontend/src/components/AuthModal.jsx`; `frontend/.env.example` (`VITE_GOOGLE_CLIENT_ID`); backend env (`GOOGLE_CLIENT_ID`).
- **Complications:** `/auth/login` must 401 cleanly on a null hash **before** calling `verify_password` (Google-created users have no password). 🧑 **HUMAN:** create the OAuth client ID in the Google Cloud console and register the dev origin — document in `.env.example` comments. SQLite nullable quirk: dropping `nullable=False` in the model needs no DDL (SQLite doesn't enforce it for existing rows) — document this in `migrations.py`.

### Task 5.3 — Environment/config consolidation
- **Files:** new `backend/.env.example` (`JWT_SECRET_KEY`, `CORS_ORIGINS` comma-separated, `GOOGLE_CLIENT_ID`); `backend/main.py` (CORS origins from env, default `http://localhost:5173`); `backend/auth.py` (keep the dev default secret but log a loud warning when unset); new `frontend/.env.example` (`VITE_API_BASE`, `VITE_GOOGLE_CLIENT_ID`); `frontend/src/utils/auth.js` (`API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'`). Backend reads env via `os.getenv` + uvicorn `--env-file .env` (no python-dotenv dep; document the flag in `.env.example`).

### Task 5.4 — Structured logging
- **Files:** `backend/main.py` (`logging.basicConfig` + `logger = logging.getLogger("lecho")`).
- **Log points:** job created (job_id, practice_id, mode, duration); each status transition; every `_fail_job` with reason; DSP wall-clock timings (extract/align/score); upload validation rejections; bleed detections. Plain `logging` with a consistent `job=%s` prefix; JSON logging deferred to Phase 3.

### Task 5.5 — Ambient-noise pipeline (PRD §6.1)
- **Files:** `backend/dsp.py` (new `denoise(samples, sr) -> (samples, snr_db)`); `backend/requirements.txt` (+`scipy`, `noisereduce`); `backend/main.py` (apply to the **user** clip only in `worker_task`, persist `snr_db` to the user `AudioAsset` — the column exists, never populated).
- **Spec:** 4th-order Butterworth bandpass 80–4000 Hz (`scipy.signal.butter(..., output='sos')` + `sosfiltfilt`); `noisereduce.reduce_noise` with the first 300ms as the noise profile; `snr_db = 10·log10(speech_rms² / noise_profile_rms²)`.
- **Complications:** verify cp314 scipy wheels first (`pip install --only-binary :all: scipy`); if unavailable, **skip the task and record it as blocked** (the `NoSpeechDetectedError` graceful-failure stub already covers the UX). Denoising changes RMS contours, so call `denoise` only from the orchestrator (`worker_task`) — `dsp.extract_features` and the pure pipeline stay untouched so the pytest suite stays deterministic.

### Task 5.6 — Test scaffolding (backend lifecycle + frontend vitest) — *build early; it's the regression net*
- **Backend:** new `backend/test_api.py` — pytest + `TestClient` + tmp SQLite + tmp storage root (monkeypatch `storage.STORAGE_ROOT` and the DB URL): register → login → create a practice row + ingest a synthetic 3s sine "native" (reuse `test_dsp.py::_write_sine_wav`) → `POST /jobs` (solo) with the same WAV → worker runs synchronously under TestClient (`BackgroundTasks` executes inline) → `GET /jobs/{id}` SUCCESS with score ≈100 → `GET /jobs/{id}/coordinates` shape check → per-mode gate rejections (shadow wrong length, solo out of ±20%) → logout revocation.
- **Frontend:** add `vitest` + `@testing-library/react` + `jsdom` devDeps and a `"test": "vitest"` script; `Recorder.test.jsx` (renders; gate error on out-of-range duration — mock `getUserMedia`/`MediaRecorder`); `Results.test.jsx` (mock fetch: PENDING→SUCCESS polling renders score + segments + words); `PitchChart.test.jsx` (fixture render).
- **Verify:** `pytest -q` and `npm test` both green.

### Task 5.7 — Job history + UI cleanup
- **Backend:** `GET /jobs?limit=20&offset=0` (auth, owner-scoped, newest first) → `{"jobs": [{"id", "practice_id", "practice_title", "status", "score", "mode", "created_at"}], "total": int}`.
- **Frontend:** new `src/pages/History.jsx` (route `/history`; navbar link replacing the dead Settings link), each row linking to `/results/{id}` (Results already handles any status). Cleanup: remove the register `name` field (backend has no column), remove the dead "Forgot password?" button, add spacebar record toggle (keydown when the recorder is visible + `aria-keyshortcuts`, PRD a11y).

---

## Stage 6 — Phase 3: Cloud migration — **SPEC-ONLY, separately triggered. Do not execute in the main run.**

Order matters: storage → DB → queue/worker → containers → infra → CI.

1. **S3 storage backend:** implement the existing seam — `storage.py` gains an S3 implementation (`boto3`; `STORAGE_BACKEND=S3`, bucket/prefix envs) behind the same functions (`save_upload`, `save_text`, `delete`, real `presign_put`; `get_path` becomes a presigned-GET path for audio serving). `AudioAsset.storage_backend` column already exists. Audio-serving routes switch to `RedirectResponse` to presigned GETs.
2. **PostgreSQL:** `DATABASE_URL` env in `database.py` (psycopg3 binary wheels); introduce Alembic **here** (baseline autogenerated from models; `migrations.py` retired); a one-off SQLite→Postgres migration script for users/practices only — jobs are disposable dev data.
3. **SQS worker:** new `worker/` package — `worker/main.py` long-polls SQS (message: `{"job_id": "..."}`), importing `backend/dsp.py` and a refactored `backend/worker_core.py` (extract `worker_task`'s body out of the FastAPI module so both transports share it); visibility timeout 120s; DLQ after 3 receives. The API's `BackgroundTasks.add_task` swaps to `sqs.send_message` behind a `QUEUE_BACKEND` env.
4. **Containers:** `backend/Dockerfile` (uvicorn) + `worker/Dockerfile` (python entrypoint). Pin the image Python to a minor version with full wheel coverage (3.12/3.13 in-container is fine; it need not match the Windows dev 3.14).
5. **Terraform:** modules for S3 (30-day lifecycle rule on `uploads/`), SQS + DLQ, RDS Postgres (smallest instance), ECS Fargate (api ×1; worker autoscaled on `ApproximateNumberOfMessagesVisible`, **max 5** per PRD 8.3), secrets in SSM Parameter Store (`JWT_SECRET_KEY`, `GOOGLE_CLIENT_ID`, DB creds).
6. **CI/CD (GitHub Actions):** PR — `pytest` + `npm test` + `npm run build`; main — build/push images to ECR + `terraform plan` with a manual apply gate.

---

## Cross-module integration contracts (single source of truth)

| Contract | Shape | Producer → Consumers |
|---|---|---|
| `POST /jobs` form | `file, practice_id, user_audio_duration, mode ∈ {solo, shadow}` | Practice.jsx → main.py |
| `GET /jobs/{id}` | adds `pitch_score`, `timing_score`, `energy_score`, `mode`; `segments[].words: string[] \| null` | main.py → Results.jsx |
| Alignment JSON | `{practice_id, source, model, words: [{word, start, end}]}` — native-timeline seconds | align_natives.py → worker word-mapper, karaoke, chart labels |
| Archive JSON | `times, native_f0_hz, user_f0_hz_aligned, native_semitone, user_semitone_aligned, native_rms, user_rms_aligned, voiced_masks{native, user_aligned}` — all `len == len(times)` | dsp.build_archive → `/coordinates` → PitchChart.jsx |
| Storage keys | `uploads/…`, `native/{practice_id}.wav`, `analysis/{job_id}.json`, `alignments/{practice_id}.json` | storage.py seam (S3-swappable) |
| Calibration manifest | Task 1.1 | human → calibrate.py |

## Complications register (anticipated, with mitigations)

1. **Python 3.14 / Windows wheels** — pre-check every new dep with `--only-binary :all:`; scipy task explicitly skippable; MFA quarantined in conda; container Python may differ from dev Python.
2. **No Alembic until Phase 3** — idempotent startup ALTERs via `migrations.py`; SQLite nullable-column quirk documented (Task 5.2).
3. **Local DB/storage fragility** — `lecho.db` untracked after Task 0.3; practice 7's clip must be re-ingested (H1); `seed.py` wipes ingested natives — never run it after ingestion without re-ingesting.
4. **Constants are placeholders until Task 1.2** — every new threshold (NCC 0.5, shadow ±0.5s, slope 1.5×) is a named constant; graduated values go in the Decision log.
5. **Bleed-check false positives/negatives** — threshold tunable; the worker gate is authoritative; test both directions (Task 3.2). A client-side pre-check is deliberately **omitted** (heavy DSP in JS for marginal UX gain; the worker's rejection round-trip is seconds).
6. **Denoising changes scored contours** — applied only in the orchestrator, keeping `dsp.py`'s pure functions and tests deterministic (Task 5.5).
7. **Shadow lag vs. Sakoe-Chiba band** — the regression test exists (`test_dsp2.py`); widening the band is the sanctioned fix, never relaxing the test.
8. **MFA quality on short clips** — contract-first design makes hand-authored JSON a drop-in fallback.
9. **Google OAuth needs a console-registered client ID** — one-time human task, documented in `.env.example`.

## Suggested execution order & parallelism

`0.1 → 0.2 → 0.3` (serial, small), then four largely independent tracks:

- **Track A:** 1.1 → 🧑 H1 → 1.2
- **Track B:** 2.1 → 2.2 → 3.4
- **Track C:** 3.1 → 3.2 → 3.3
- **Track D:** 4.1 → 4.2 (word labels degrade without Track B)

Stage 5 tasks are mutually independent; do **5.6 early** (regression net for everything else). 🧑 H2 is ongoing and blocks nothing in code. Stage 6 only on explicit owner trigger.

## Decision log

*(Append a dated line whenever a placeholder constant graduates or a decision is resolved.)*

- 2026-07-07 — Plan created. Owner decisions: Phase 3 spec-only; human recording gates; MFA via conda; real Google OAuth (GIS ID-token flow).
- 2026-07-11 — Task 0.1 done (`338eb58`): dsp-2 baseline frozen with trim-time re-normalization of `f0_semitone`/`rms_z` and median-slope tempo estimate (ADR 0001).
- 2026-07-11 — Calibration corpus redefined (ADR 0002): owner emulation + monotone (+ low-effort diagnostic); gates emulation ≥ 75, margin ≥ 20. No second native speaker available. Emulation takes recorded shadow-style with headphones.
- 2026-07-11 — Agent may install Miniconda (user-scope) + mfa conda env + French models for Task 2.1; owner approved.
