# L'Écho — Implementation Plan

> **Superseded for execution (2026-07-07):** the live, task-by-task execution document is now `master_implementation_plan.md` (repo root). This file remains as the audit/rationale record behind it.

**Companion to:** `design_document.md` (v1.2.0), `worker_plan.md` (dsp-1, shipped)
**Purpose:** (1) audit what the codebase actually does today, (2) lay out the phased build-out to the PRD's target, incorporating the v1.2.0 decisions (PRD Sections 8.4–8.9).

Decisions this plan assumes (PRD v1.2.0, Section 8): word-anchored feedback via offline MFA alignment of native clips (8.4); `LIAISON_MISSED` descoped (8.5); rhythm scored from the DTW warping path with a joint alignment cost and pause tags — `dsp-2` (8.6); simultaneous shadowing as the default capture mode with headphone/bleed gating (8.7); native references self-recorded + open-licensed, no film audio, TTS dev-only (8.8); native-vs-native calibration protocol as the definition of done for scoring (8.9). Plus the v1.1.0 decisions: F0 + RMS speaker-normalized, prosody-only scope, local-first with AWS deferred to the final phase.

---

## Part 1 — Current State Audit (refreshed 2026-07-05)

*The previous audit (written against the pre-`08b0c2b` tree) described a demo where the frontend and backend were never connected and the worker was fully mocked. That is no longer true — most of the original Phase 1 has shipped. This section replaces it.*

### What actually works end-to-end
- **The full core loop is real:** register/login (`AuthModal.jsx`, `utils/auth.js`, JWT in localStorage) → record (`Recorder.jsx`, MediaRecorder → client-side WAV transcode via `blobToWav`) → real multipart `POST /jobs` with the Bearer token (`Practice.jsx`) → server-side validation (auth, ±20% relative gate, absolute 2–15s gate on *server-derived* duration, WAV readability, size cap) → persisted `AudioAsset` with sha256/metadata and a 30-day `expires_at` → real DSP in the background task → `Results.jsx` polls `GET /jobs/{id}` every 2s and renders the real score, real segments, and failure states with a retryability distinction.
- **Real DSP (`backend/dsp.py`, algo `dsp-1`):** Parselmouth F0 + windowed RMS on a shared 10ms grid, unvoiced-gap interpolation with a preserved voiced mask, semitone/z-score speaker normalization per PRD FR-3, silence trimming, hand-rolled Sakoe-Chiba-banded DTW on the pitch contour, 3:1 length-ratio abort, exp-mapped 70/30 pitch/energy score, threshold-based `INTONATION_DROP` / `ENERGY_FLAT` / `EMPHASIS_MISSED` segments, and the JSON coordinate archive. Six passing synthetic-audio tests in `backend/test_dsp.py`.
- **Storage seam (`storage.py`)**, authoritative audio metadata extraction (`audio_meta.py`), seeded dev user with a real bcrypt hash (the old `dummy_hash` bug is fixed).

### What's missing or wrong (in order of impact)

1. **No native reference audio exists — every job fails.** All seeded practices have `audio_url = null`; the worker fails these loudly by design (`main.py`, worker_plan §0). This is the hard blocker: scoring calibration, segment-threshold tuning, and all of `dsp-2` are unvalidatable until clips exist. Now decided (PRD 8.8) and scheduled as the first item of Phase 1R.
2. **The scoring algorithm is blind to rhythm (PRD 8.6).** `dsp-1` scores pitch/energy RMSE *after* DTW has warped timing differences away, and `align()` uses pitch alone, so pause structure never influences alignment or score. The warping path is archived but unused. `SYLLABLE_STRETCH` is in the PRD but never emitted. Addressed by `dsp-2` (Phase 1.5).
3. **Feedback isn't linguistically anchored (PRD 8.4).** Segments say "2.1s–2.8s", not "on *les amis*". Needs the per-clip MFA word-timing asset (Phase 2).
4. **The practice UX is delayed repetition, not shadowing (PRD 8.7).** No simultaneous playback, no headphone/bleed handling, no clock-synced capture. Phase 2.
5. **Mock-tone trap:** `Practice.jsx` falls back to `generateMockAudioBlob` (a synthetic beep) when a practice has no `audio_url` — the user records against a beep and the backend then correctly fails the job. Should render "reference audio not yet available" and disable recording. Phase 1R.
6. **Capture constraints are browser defaults:** `getUserMedia({ audio: true })` leaves AGC/noise-suppression/echo-cancellation on in most browsers; AGC's time-varying gain distorts the exact RMS contour the system scores. One-line fix per FR-1. Phase 1R.
7. **`worker/main.py` is a stale, misleading mock** — the pre-dsp fake worker still sits at the repo root, never imported, fabricating scores if run by hand. Delete it; the Phase 3 SQS entrypoint will be written fresh, importing `backend/dsp.py` (worker_plan §2). Phase 1R.
8. **No coordinates endpoint / pitch-overlay visualizer.** The worker writes the aligned-curve archive, but nothing serves it (`GET /jobs/{id}/coordinates`) and the Results page has no pitch chart — the PRD's core "Insight Consumption" step. Phase 2.
9. **Hardening gaps (unchanged from v1.1.0):** no `/auth/logout` despite `revoked_tokens` being checked on every request; CORS origin and JWT secret hardcoded/defaulted with no `.env.example`; no structured logging around job transitions and DSP failures; the ambient-noise pipeline (bandpass + `noisereduce` + SNR check, PRD §6.1) is still only a graceful-failure stub; no frontend tests and no backend tests beyond `test_dsp.py`.

---

## Part 2 — Phase 1R: Unblock & Fix (small, do first) — **DONE except real-clip verification (2026-07-05)**

**Goal:** real native audio in the system and the known traps removed, so everything downstream has something to validate against.

1. **Source native reference audio (PRD 8.8) — the critical path.** *Tooling done; clips pending.*
   - ✅ `backend/ingest_native.py`: converts any Praat-readable file to canonical 16kHz mono PCM WAV, sanity-checks it with the real DSP pipeline (voiced speech must survive silence trim), enforces the native-duration window **2.5–12.5s** (so user recordings at ±20% stay inside the absolute 2–15s gate; `--force` to override), stores via the `storage.py` seam under `native/{practice_id}.wav`, writes a `NATIVE_REFERENCE` `AudioAsset` (no expiry), and sets `Practice.audio_url` + real `duration`. Can attach to an existing practice (`--practice-id`) or create a new one (`--title`/`--transcript`).
   - ✅ `GET /practices/{practice_id}/audio` serves the ingested clip to the frontend (404 when no reference).
   - ✅ Raw clip sources live in `native_audio/` (gitignored — may contain licensed material or personal voice recordings).
   - ✅ First real clip ingested: practice 7 ("Napoléon Film Review Intro", 4.85s, 66% voiced). ⬜ Calibration corpus still to record: a **second native rendition** and a **deliberate monotone read** per PRD 8.9 (the low/mid-effort learner takes below are learner data, not the native-vs-native pair the protocol needs).
2. ✅ **Mock-tone trap removed:** `Practice.jsx` shows "This practice isn't ready yet — reference audio coming soon" and hides the recorder when `audio_url` is null; `generateMockAudioBlob` deleted from `utils/audio.js`.
3. ✅ **Capture constraints set** in `Recorder.jsx`: `{ echoCancellation: false, noiseSuppression: false, autoGainControl: false }` (FR-1).
4. ✅ **`worker/main.py` deleted** (stale mock; git history preserves it).
5. **Verification:** ✅ synthetic end-to-end smoke passed (ingest → audio endpoint → register → multipart `POST /jobs` → real DSP → `SUCCESS`, identical-clip score = 100.0, temp rows/files cleaned up). ✅ Real-audio run (2026-07-05, practice 7): the score genuinely varies with input — low-effort take 46.4 (10 segments), mid-effort take 40.2 (6 segments), vs. the pre-Phase-1 constant 85.5 — so the core criterion (score reflects the actual recording) is met. **First calibration finding, feeding Phase 1.5:** the overall score ranked the low-effort take *above* the mid-effort one (46.4 > 40.2), while segment count ranked them correctly. Diagnostics: both learner takes had ~2× the native's pitch variability (5.2 / 4.4 st std vs. native 2.3 st), and the learner's median F0 (~115Hz, male) sits near the 75Hz pitch floor where creak/octave artifacts are likely — supporting the planned work on the timing component, K-constant calibration, and possibly per-speaker pitch-floor handling. A 6-point gap on an uncalibrated scorer is not yet meaningful; the 8.9 harness is what makes it so.

---

## Part 3 — Phase 1.5: Scoring v2 (`dsp-2`) + Calibration

**Goal:** the score measures what the product claims — rhythm and pauses included — and the constants stop being guesses. All changes live in `dsp.py` + `test_dsp.py`; no API or schema changes beyond new tag values.

1. **Joint DTW cost (PRD 8.6.3):** frame distance `|Δsemitone| + λ·|Δrms_z|`, `λ = 0.5` placeholder, so silences anchor the alignment.
2. **Timing component (PRD 8.6.1):** per-native-frame local slope of the warping path over a ~150ms window; deviation `|log2(slope)|`; aggregate → `timing_score = 100·exp(−x/K_TIMING)`. Overall = `0.55·pitch + 0.25·timing + 0.20·energy`. Bump `ALGO_VERSION` to `dsp-2` (the column exists for exactly this).
3. **New segment tags:** `SYLLABLE_STRETCH` from slope runs (>1.5× or <0.67× for ≥ min run length); `PAUSE_MISSED` / `PAUSE_EXTRA` from comparing unvoiced runs ≥150ms between native and aligned user.
4. **Shadow-lag regression test:** synthetic pair where the "user" signal is the native contour delayed 500ms — must align and score high with the 15% Sakoe-Chiba band. Widen the band only if this fails. (Prerequisite for Phase 2's shadow mode.)
5. **Calibration harness (PRD 8.9):** using the Phase 1R corpus — native-vs-native ≥ 85, monotone ≥ 20 points lower. Tune `K_pitch` / `K_timing` / `K_energy`, `λ`, weights, and segment thresholds against it. **This is the definition of done for `dsp-2`.**

---

## Part 4 — Phase 2: Shadowing Mode, Word Anchoring & Hardening

**Goal:** the practice experience becomes actual shadowing, feedback speaks in words, and the app is solid enough for real test users.

### 2.1 Word-timing asset (PRD 8.4) — do first; 2.2 and 2.3 both consume it
- `scripts/align_natives.py`: run Montreal Forced Aligner (`french_mfa` model + dictionary) over each native clip + transcript → `storage/alignments/{practice_id}.json` (`[{word, start, end}]`). Offline, once per clip, re-run on new clips.
- Worker: map each feedback segment's native-timestamp range to words; add a `words` field to `AnalysisSegment` rows and surface it in `Results.jsx` ("on *les amis*" instead of "2.1s–2.8s").

### 2.2 Shadow mode (PRD 8.7, Edge Case 3)
- `Practice.jsx` / `Recorder.jsx`: mode toggle (Shadow default, Solo fallback). Shadow take: session-remembered headphones prompt → playback + capture started on one `AudioContext` clock → auto-stop at `native_duration + 1.0s` → existing WAV transcode/upload.
- **Bleed gate:** normalized cross-correlation of the recording against the reference; NCC peak > 0.5 (placeholder) at plausible lag ⇒ reject client-side with the headphones message. Worker re-checks as defense-in-depth (never score a bled take).
- `POST /jobs`: `mode` form field; per-mode duration gates (Solo ±20%; Shadow `native + tail ± 0.5s`).
- Karaoke transcript highlighting during playback, driven by the 2.1 word timings.

### 2.3 Pitch-overlay visualizer
- `GET /jobs/{job_id}/coordinates` serving the archive JSON (owner-scoped, like the status endpoint).
- Results-page chart: native vs. aligned user contour (Hz), deviation-colored via the normalized arrays, word labels on the time axis from 2.1. Text-based descriptions alongside, per the PRD's a11y requirement.

### 2.4 Hardening (carried from v1.1.0)
- `POST /auth/logout` writing to `revoked_tokens`; `.env.example` (`JWT_SECRET_KEY`, CORS origins from env); structured logging for job transitions and DSP failures.
- Ambient-noise pipeline (PRD §6.1): Butterworth bandpass + `noisereduce` + SNR check (adds `scipy` — deliberately deferred until now).
- Tests: backend job-lifecycle pytest (create → process → fetch); frontend component test for `Recorder` gating and an integration test for record→submit→poll→result.

---

## Part 5 — Phase 3: Cloud Migration (unchanged from v1.1.0)

Done last, once DSP and UX are validated locally: S3 behind the `storage.py` seam (pre-signed uploads), SQS + a fresh containerized worker entrypoint importing `backend/dsp.py`, SQLite → PostgreSQL, Terraform (RDS, SQS, S3 with the 30-day lifecycle rule, worker autoscaling on queue depth capped at 5 instances pending real usage data), CI/CD via GitHub Actions.

---

## Part 6 — Backlog (not scheduled)
- **Segmental engine** (PRD 9.2): wav2vec2 XLSR phoneme recognition + Needleman-Wunsch vs. the canonical phoneme sequence. The designated approach if phoneme-level feedback is prioritized — **PLS-SVM explicitly rejected** (PRD 8.4).
- **Liaison heuristic** (PRD 9.3): voicing/energy continuity across known liaison boundaries via the word timings; would partially restore `LIAISON_MISSED`.
- Chatbot practice recommendations (PRD 9.1); STT word-correctness checking (out of scope per PRD 8.2).

---

## Open Assumptions Log
- **Scoring constants are placeholders until the 8.9 harness runs:** `λ = 0.5`, `K_TIMING`, 55/25/20 weights, slope thresholds (1.5×/0.67×), pause-run minimum (150ms), NCC bleed threshold (0.5), native-vs-native target (≥85).
- **Sakoe-Chiba band at 15%** is assumed to tolerate a 500ms shadow lag after silence trim — verified by the Phase 1.5 regression test, widened only if it fails.
- **MFA French model quality** on short conversational clips is assumed adequate; if alignment is poor on real clips, fall back to word-level-only anchoring (no syllables).
- **Native speaker recruitment** (Phase 1R) assumes access to at least two native/near-native speakers; the calibration protocol depends on it.
- **JWT in localStorage** (XSS caveat) and the **5-instance autoscaling cap** carry over from v1.1.0 unchanged.

https://www.homepages.ucl.ac.uk/~uclyyix/ProsodyPro/
