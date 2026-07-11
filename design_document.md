# Product Requirement Document (PRD) & Design Specification

**Product Name:** L'Écho
**Version:** 1.2.0-PRD (Revised — shadowing mode, rhythm scoring, word-anchored feedback)
**Author:** Technical Product Manager & Lead UX/UI Designer

**Revision Note (v1.1.0):** This revision resolves the three open questions from Section 8 of v1.0.0 and reconciles the PRD against the current state of the repository (see `master_implementation_plan.md` for the full audit and phased build-out). The biggest structural change: the PRD's target architecture (SQS/S3/Postgres/Terraform) is now explicitly framed as a **later phase**. The repository today is a local-first MVP (SQLite, in-process background tasks, local disk, a fully mocked worker), and the plan is to make that MVP *real* — real DSP, real audio persistence, real job status — before migrating to the AWS stack described in Section 4.

**Revision Note (v1.2.0):** This revision incorporates the SLA/shadowing research review (see `Shadowing Development Research.txt`) and resolves six new decisions, recorded in Sections 8.4–8.9:
1. **Word-anchored feedback (8.4):** feedback segments are mapped to transcript words via offline forced alignment of the *native* clips (Montreal Forced Aligner) — not raw timestamps, and not per-user phoneme classification (the PLS-SVM proposal is explicitly rejected).
2. **`LIAISON_MISSED` descoped (8.5):** liaison is a segmental phenomenon undetectable from F0/RMS; the tag is removed from FR-4 until a segmental engine exists (backlog, Section 9).
3. **Rhythm is scored from the DTW warping path (8.6):** DTW deliberately warps time away, so pitch/energy RMSE alone is blind to rhythm errors — the single biggest weakness of v1.1.0 given the product's "cadence and rhythm" claim. The warping path's local slope becomes a third scoring component and drives the `SYLLABLE_STRETCH` tag; pause structure is compared via voiced-mask runs.
4. **Simultaneous shadowing is the primary practice mode (8.7):** the v1.1.0 flow was delayed repetition, not shadowing. Playback and recording now run concurrently (headphones required, with a bleed check); the learner's natural ~250–500ms lag is tolerated by the pipeline, never enforced by the app.
5. **Native reference sourcing decided (8.8):** self-recorded native speakers + CC0/CC-BY corpora; no copyrighted film/YouTube audio; TTS for dev smoke tests only. This is the critical path — nothing downstream can be validated without it.
6. **Calibration protocol defined (8.9):** native-vs-native renditions must score high and monotone reads low before the placeholder scoring constants are considered real.

## 1. Overview & Objectives

### Main Goal
The primary objective of L'Écho is to break the "accent barrier" for advanced language learners by providing precise, acoustic-level feedback on speech prosody (intonation, cadence, rhythm, and pitch). Unlike standard speech-to-text engines, L'Écho focuses entirely on how a user speaks rather than just what words they articulate.

### Target User (Persona Profile)
*   **Advanced French Learners (B2–C2 Level):** Individuals who have strong grammatical foundations and rich vocabulary but struggle with non-native cadence, rhythm, or a flat accent.
*   **Academic & Professional Presenters:** Students preparing for rigorous oral examinations (e.g., French university oraux) or actors practicing script readings who need to master exact rhetorical pauses, breath groupings (groupes rythmiques), and trailing intonations.

### Problem Solved
Traditional language apps rely on Speech-to-Text APIs (e.g., Whisper, Google STT). If the user pronounces the correct words with an improper cadence, flat tone, or incorrect syllable stretching, the app marks it as "correct." Advanced learners plateau because they cannot visualize their pitch drift against a native reference. Manual "shadowing" (listening and mimicking) lacks an objective metric or a clear visual feedback loop.

### The Engineering Justification
Extracting fundamental pitch frequencies ($F_0$ curves), computing amplitude envelopes, and executing Dynamic Time Warping (DTW) algorithms to warp and match misaligned audio signals are computationally heavy tasks. This processing takes anywhere from 10 to 45 seconds per sample. Running this synchronously on a web server would cause immediate network timeouts. This necessitates an asynchronous, decoupled microservices architecture using an API gateway, a message broker, and a dedicated worker.

## 2. Core User Flows & Personas

### Key Personas
| Persona | Language Level | Core Need | Primary Goal |
| :--- | :--- | :--- | :--- |
| **Julien (The Academic)** | C1 (Advanced) | Prepping for a 20-minute master's thesis defense on Albert Camus. | Eliminate English speech rhythm patterns and master native French rhetorical intonation. |
| **Clara (The Actor/Improviser)** | B2 (Upper-Intermediate) | Preparing a monologue for an indie short film. | Perfect the phonetic liaisons between words and manage authentic breathing points. |

### Step-by-Step User Journey
1.  **Selection:** The user browses a list of high-quality native audio snippets (sorted by difficulty, literary style, or film genre) and selects a 5-second target clip.
2.  **Review:** The user listens to the native speaker and reads the corresponding transcript text along with linguistic notes (e.g., indicating a subjonctif verb context or a specific liaison rule).
3.  **Recording (Shadow mode, default):** The user confirms they are wearing headphones, then starts a *shadow take*: the native clip plays while the user speaks over it, trailing naturally by a fraction of a second. Recording auto-starts with playback and auto-stops at clip end plus a short tail, then submits the `.wav` file. A *Solo mode* (listen first, then record alone) remains available as a fallback for users without headphones. See Section 8.7.
4.  **Ingestion & Deferral:** The UI immediately informs the user that their audio is safely queued for matching. The user is redirected back to their practice history or allowed to try another clip.
5.  **Notification & Review:** Once the background task completes, an alert points the user to their finalized Prosody Analysis Dashboard.
6.  **Insight Consumption:** The user interacts with the generated pitch chart, visually identifying exactly where their rhythm expanded or where their pitch failed to match the target curve.

## 3. Functional Requirements

### FR-1: Audio Capture & Ingestion
*   The system must record high-quality uncompressed audio via the browser's Web Audio API.
*   **Capture constraints must be set explicitly for analysis, not left at browser defaults:** `getUserMedia` is called with `echoCancellation: false`, `noiseSuppression: false`, `autoGainControl: false`. Browser AGC applies *time-varying* gain that distorts the RMS contour the system scores, and noise suppression can distort F0. (Headphone-based shadowing makes echo cancellation unnecessary; see Section 8.7.)
*   **Two capture modes** (Section 8.7): *Shadow* (default) — recording is clock-synced to native playback on one `AudioContext`, auto-starting with playback and auto-stopping at `native_duration + 1.0s` tail; *Solo* — user-triggered record after listening.
*   The system must enforce a strict absolute duration boundary (minimum 2 seconds, maximum 15 seconds) to prevent buffer overruns on the background processing cluster. The *relative* gate is per-mode: Solo keeps the ±20%-of-native bound; Shadow takes are app-timed, so the expected duration is `native_duration + tail` within a ±0.5s tolerance.

### FR-2: Asynchronous Job Lifecycle Management
*   The web layer must acknowledge an upload instantly, returning an HTTP status code `202 Accepted` along with a unique tracking ID (`job_id`).
*   The system must isolate the heavy computing task from the live web instance via an isolated background processing microservice.

### FR-3: Digital Signal Processing (DSP) & Signal Alignment
*   The processing service must compute the fundamental frequency ($F_0$ contour) **and** the RMS amplitude (energy) envelope of both audio sources. Resolved — see Section 8.1: both signals are needed because prosody comprises pitch *and* emphasis/pause structure, and RMS is what lets the system flag missed liaisons or cut-short syllables that a pitch-only model would miss.
*   **Speaker normalization (mandatory, precedes alignment):** Raw Hz and raw RMS are never compared directly, because they encode voice identity (a bass voice and a soprano voice can have identical *accent* while differing by an octave in absolute pitch; recording gain/mic distance changes absolute loudness independent of speech). Before DTW runs, both signals are converted to speaker-relative, unit-free representations:
    *   **Pitch → semitones relative to the speaker's own median $F_0$:** `semitone_offset = 12 * log2(f0 / speaker_median_f0)`, computed independently for the native clip and the user clip, each using its own median as the zero point. This is the standard measure used in prosody research (it's how linguists compare intonation across speakers of different vocal range) and is invariant to absolute voice pitch.
    *   **Energy → per-clip z-score:** `rms_z = (rms - clip_mean) / clip_std`, computed independently per clip. This makes the energy contour comparable regardless of recording volume, mic gain, or distance from the mic — only the *shape* of loudness over time (where it rises/falls) is scored.
    *   Only after this normalization step does the system run DTW alignment and scoring. This directly targets "comparing accents, not voices."
*   The system must apply a Dynamic Time Warping (DTW) mathematical alignment model to the normalized arrays to warp the user's speaking rate onto the native speaker's timeline.
*   **Joint alignment cost (v1.2.0, Section 8.6):** the DTW frame distance is a weighted combination of pitch and energy — `d = |Δsemitone| + λ·|Δrms_z|` (λ = 0.5, placeholder) — rather than pitch alone. Silences and energy dips then anchor the alignment, so pause placement (breath groups / *groupes rythmiques*) influences where frames match instead of being interpolated away.
*   **The warping path is a scoring output, not a discard (v1.2.0, Section 8.6):** the path's local slope (how much the user stretched or compressed time relative to the native speaker) is retained and scored as the rhythm/timing component. This is what makes the system sensitive to English stress-timing transfer — the dominant error class for anglophone French learners — which pitch/energy RMSE alone cannot see, because DTW's warping absorbs it.

### FR-4: Scoring & Insight Generation
*   The system must output an absolute percentage matching score as a weighted combination of **three** components (v1.2.0): **55% pitch / 25% timing / 20% energy** (placeholders, tunable, pending the Section 8.9 calibration protocol). Pitch and energy scores derive from RMSE over the aligned, **normalized** arrays; the timing score derives from the DTW warping path's local slope deviation (Section 8.6). *The shipped `dsp-1` algorithm uses 70/30 pitch/energy with no timing component; `dsp-2` (implementation plan Phase 1.5) adds timing and rebalances.*
*   The system must isolate intervals where deviation exceeds threshold and generate contextual improvement tips (tags: `INTONATION_DROP`, `SYLLABLE_STRETCH`, `ENERGY_FLAT`, `EMPHASIS_MISSED`, `PAUSE_MISSED`, `PAUSE_EXTRA`). `LIAISON_MISSED` is **removed** from this list — see Section 8.5.
*   **Word anchoring (v1.2.0, Section 8.4):** feedback segments must reference transcript words ("on *les amis*"), not just raw timestamps. Native clips are force-aligned against their known transcripts offline (once per clip); because the analysis re-expresses the user onto the native timeline, every segment's native-timestamp range maps directly to words.
*   Scope is strictly prosody (pitch, rhythm, cadence, emphasis). The system does **not** perform word-correctness checking (Section 8.2) or per-phoneme classification of user audio (Section 8.4).

## 4. Technical Architecture & Constraints

**Phasing note:** the stack below is the **Phase 3 (cloud) target**, not the current state. The repository today runs a local-first MVP: SQLite instead of PostgreSQL, in-process FastAPI `BackgroundTasks` instead of SQS + a separate worker container, and local disk instead of S3. See `master_implementation_plan.md` for the phase-by-phase migration path and why local-first comes first (faster iteration on the DSP algorithm itself, no AWS spend, before paying the infra cost of the queue/object-store split).

### Tech Stack Specifications
*   **Frontend Framework:** React (Single Page Application architecture).
*   **API Microservice Gateway:** Python powered by FastAPI leveraging asynchronous execution paths (async/await).
*   **Message Broker / Throttling Layer:** AWS SQS (Simple Queue Service) to guarantee message durability and handle traffic spikes gracefully.
*   **Processing Engine (Worker):** A headless containerized Python environment leveraging `Parselmouth` (a native wrapper for Praat acoustic processing software) or `Librosa` for signal parsing.
*   **Persistent Storage Database:** PostgreSQL configured with relational tables tracking user metrics and pitch coordinate arrays.
*   **Object Store Caching:** AWS S3 to hold raw and processed audio assets.
*   **Infrastructure Provisioning:** Terraform configurations ensuring automated, declarative cloud deployments.
*   **Container Layer & CI/CD:** Docker environments deployed via automated Git pipelines.

### Relational Schema Blueprint
`[Users] 1 ------- * [ProsodyJobs] 1 ------- * [AnalysisSegments]`

```sql
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE prosody_jobs (
    job_id UUID PRIMARY KEY,
    user_id INT REFERENCES users(user_id),
    native_sample_id INT NOT NULL,
    status VARCHAR(50) NOT NULL, -- PENDING, PROCESSING, SUCCESS, FAILED
    native_s3_path TEXT NOT NULL,
    user_s3_path TEXT NOT NULL,
    overall_match_score INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE analysis_segments (
    segment_id SERIAL PRIMARY KEY,
    job_id UUID REFERENCES prosody_jobs(job_id) ON DELETE CASCADE,
    timestamp_start FLOAT NOT NULL,
    timestamp_end FLOAT NOT NULL,
    feedback_tag VARCHAR(100), -- INTONATION_DROP, SYLLABLE_STRETCH, ENERGY_FLAT, EMPHASIS_MISSED, PAUSE_MISSED, PAUSE_EXTRA (LIAISON_MISSED descoped, see §8.5)
    explanation TEXT,
    coordinates_path TEXT -- pointer to the raw aligned/normalized F0+RMS arrays (see note below)
);
```

**Schema note (reconciled with current code):** the full-resolution aligned pitch/RMS arrays are **not** stored as `FLOAT[]` columns in the row. A single 5–15 second clip at typical F0 frame rates produces thousands of points per array; storing that inline bloats the relational table and is expensive to query. Instead, each job's raw aligned+normalized arrays are dumped once as a JSON blob (locally: a file under `backend/storage/analysis/{job_id}.json` in Phase 1; on S3 under `archives/` in Phase 3), and `analysis_segments.coordinates_path` just points to it. This "hybrid archive" pattern is already what `worker/main.py`'s mock implementation assumes (`s3_coordinates_json_path`) — this PRD revision just makes it the documented schema instead of an implementation detail that silently diverged from the PRD.

### Constraints & Performance Thresholds
*   **Gateway Response Limit:** The FastAPI backend must hand off the job to SQS and return the initial tracking state payload within < 50 milliseconds.
*   **Worker Resource Sandbox:** The Docker configuration for the processing worker must allocate appropriate CPU blocks to support rapid Fourier Transform math functions efficiently.
*   **Storage Cycle:** Uploaded client recordings should leverage an S3 Lifecycle rule to auto-expire or move to archival tiers after 30 days to optimize database costs.

## 5. UX/UI Specifications & Aesthetics

### Aesthetics & Visual Style
*   **Design Philosophy:** Clean, distraction-free minimalist dark mode layout. This mimics premium audio workstations or modern coding tools, framing the application as a precision utility rather than a gamified app.
*   **Typography:** Clean sans-serif headings for readability during real-time speech practice.
*   **Color Hierarchy (Agnostic Design Principles):**
    *   Base canvas background: Dark, low-contrast tone to maintain focus.
    *   Native timeline layer: Soft neutral color representing stability and correctness.
    *   User comparison layer: Interactive accent color that changes based on deviation thresholds (e.g., blends into a distinct warning layout in areas where the voice curves diverge significantly).

### Interface Layout Structure
*   **Top Area:** Context Banner containing the French text sentence with accent tags highlighting liaison rules. During a Shadow take, the current word is highlighted in sync with playback (karaoke-style), driven by the same per-clip word timings produced by the Section 8.4 forced alignment.
*   **Middle Area:** The Pitch Interactive Visualizer. A timeline tracking frequency in Hertz (Hz) against time in seconds.
*   **Bottom Area:** Floating Action Tray containing the single mic control trigger, audio replay options, and detailed metric breakdown cards.
*   **Shadow pre-roll:** before the first Shadow take of a session, a headphones confirmation prompt ("Shadowing plays the native clip while you record — use headphones so your mic only hears you"). Remembered for the session; Solo mode is offered as the no-headphones alternative.

### Accessibility Requirements (a11y)
*   Provide visible, text-based descriptions alongside all graphical charts so that users with red-green color deficiencies can interpret mistakes through descriptive flags.
*   All microphone control points must support standard keyboard navigation mapping (e.g., Spacebar to toggle recording).

## 6. Edge Cases & Error Handling

### 1. Excessive Background Ambient Noise
*   **Scenario:** The user records their session in a crowded cafe, introducing high ambient noise that prevents the pitch tracking algorithm from extracting a clear $F_0$ fundamental frequency line.
*   **System Behavior (The DSP Pipeline):** Rather than dropping the execution block, the containerized Python background worker routes both the User Recording (Source) and the Native Clip (Reference) through an automated three-stage digital signal processing pipeline before performing the alignment math:
    *   **Bandpass Filtering (SciPy):** The worker applies a 4th-order Butterworth bandpass filter (`scipy.signal.butter`) to both audio tracks. The filter cuts off all frequencies below $80\text{ Hz}$ (eliminating subsonic traffic rumble and AC hums) and all frequencies above $4000\text{ Hz}$ (eliminating high-frequency electronic hiss), isolating the core human vocal spectrum.
    *   **Spectral Subtraction (Noise Profiling):** Using the `noisereduce` library, the worker samples the initial 300ms silent buffer of the user's recording to profile the stationary ambient noise floor. This spectral signature is mathematically subtracted across the Fast Fourier Transform (FFT) matrix of the entire sample, cleanly isolating the voice.
    *   **Signal-to-Noise Ratio (SNR) Verification:** Following sanitization, the worker calculates the final Signal-to-Noise Ratio and pitch tracking confidence interval.

### 2. Radical Execution Time Deviation
*   **Scenario:** The user speaks incredibly slow, causing a 3-second native phrase to stretch across a 14-second recording window.
*   **System Behavior — two layers of defense (reconciled with current code):**
    1.  **UX-level gate (capture time, strict):** The recorder and the `POST /jobs` endpoint both reject recordings whose duration falls outside **±20%** of the native clip's duration, before any upload or DSP work happens. This is intentionally tighter than the DTW safety limit below — most users who drift this far need to just retry the clip, and it's cheaper to catch it client-side than to burn a worker cycle.
    2.  **DTW-level safety net (worker, permissive):** Even within the ±20% UX gate, frame-level silence trimming or clock drift could in principle still produce a pathological length ratio. As defense-in-depth, the DTW matrix calculation still checks if the length ratio between the two *trimmed* arrays exceeds $3:1$ and aborts early rather than risk runaway memory use. In practice, given gate #1 exists, this should almost never trigger — it exists to make the worker itself robust to bad input, not to be the primary UX guardrail.
    *   If either layer rejects the recording, the interface outputs: "Your recording duration differs significantly from the target clip. Try keeping your pace closer to the native speaker's speed."

### 3. Reference Audio Bleed During a Shadow Take (v1.2.0)
*   **Scenario:** The user starts a Shadow take on laptop speakers instead of headphones. The native clip plays into the microphone, so the recording contains two overlapping voices. Praat's autocorrelation pitch tracker on a two-voice mixture produces a garbage F0 contour — the score would be meaningless, and worse, *plausible-looking*.
*   **System Behavior:** After the take, the client (or worker) computes the normalized cross-correlation between the recording and the reference clip. A correlation peak above threshold (placeholder 0.5) at a plausible lag means the reference leaked into the mic; the take is rejected before scoring with: "It sounds like the native audio was picked up by your microphone. Please use headphones for shadow takes, or switch to Solo mode." This is a hard gate — a bled recording must never reach the scorer.

### 4. Sudden Network Disconnection Post-Upload
*   **Scenario:** The client internet cuts out exactly as the recording finishes uploading, meaning the frontend misses the live confirmation state update.
*   **System Behavior:** Because state is safely saved inside PostgreSQL, when the client's network recovers and reconnects, the application executes a structural status synchronization query on mounting. The user's dashboard seamlessly reflects the processing job's latest real-time status.

## 7. Success Metrics & KPIs

### System Performance KPIs
*   **Queue Latency Time:** The average duration a job sits inside AWS SQS before a container worker pulls it down for execution (Target: < 1.5 seconds under typical load profiles).
*   **Total Processing Cycle:** The wall-clock time from when a user clicks submit to the final visibility of the analysis graph (Target: < 12 seconds for a standard 5-second speech snippet).

### User Experience KPIs
*   **Stickiness / Return Rate:** The percentage of users who return to practice the exact same sentence structure within a 48-hour window, proving they are actively engaging with the corrective feedback loop.
*   **Acoustic Metric Progression:** The statistical increase in the overall alignment match score for an individual user after practicing a single sentence 5 or more times.

## 8. TPM & Architectural Clarification Check (Resolved)

Sections 8.1–8.3 resolved the three questions that blocked v1.0.0. Sections 8.4–8.9 record the v1.2.0 decisions from the shadowing-research review. Each entry keeps the original question for traceability.

### 8.1 Signal Comparison Depth — **Resolved: F0 + RMS, both speaker-normalized**
*Original question: pitch alone, or also energy/volume?*

Pitch alone would miss syllable emphasis, breath-group pauses, and liaison drops — all core to the "cadence and rhythm" half of the product's value prop, not just intonation. So both signals are in scope. The complexity concern in the original question was really about comparability across voices, not algorithmic cost — RMS extraction is cheap once F0 extraction is already happening (same framing, same STFT machinery in Parselmouth/Librosa). The real fix is normalization, not omission: see the new methodology in FR-3 above (semitone-relative F0, per-clip z-scored RMS). Default scoring weight is 70% pitch / 30% energy; this weight is a tunable parameter, not hardcoded, so it can be adjusted after real user testing.

### 8.2 Linguistic Scope Control — **Resolved: prosody only, no word-correctness checking**
*Original question: pure prosody, or also flag wrong words via STT?*

Scope stays strictly prosodic (pitch, rhythm, cadence, emphasis). Adding a Whisper/STT word-alignment step would meaningfully expand infrastructure (hosting an STT model, handling recognition errors/confidence thresholds, a second scoring axis with its own UX) for a feature that's adjacent to, not central to, the "accent barrier" problem this product targets. If word-correctness checking becomes a priority later, it should be scoped as its own feature addition (Phase 4+), not folded into the current DSP pipeline.

### 8.3 Multi-User Scaling Budget — **Resolved (default, pending real usage data): defer autoscaling to the cloud migration phase; cap at 5 concurrent worker instances**
*Original question: how should the worker cluster scale under classroom-sized load, and what's the instance cap?*

This entire question is moot until Phase 3 (AWS migration) — the current local-first MVP has one worker process and no SQS. For planning purposes, Phase 3's Terraform config should default to an SQS-queue-depth-triggered autoscaling policy with a **hard cap of 5 EC2 worker instances**, which comfortably covers a class-sized burst (~20-30 students) processing sequentially within the KPI target (<12s wall clock) without material AWS billing risk. This default is a placeholder — it should be revisited once there's real usage data from the local-first MVP (Phase 1/2) showing actual concurrent submission patterns.

### 8.4 Linguistic Feedback Anchoring — **Resolved: offline forced alignment of native clips; per-user phoneme classification rejected**
*Original question: DTW comparison yields acoustic feedback ("pitch dipped at 2.1s") but no linguistic feedback — how does the user learn* what *to fix?*

**Decision: Montreal Forced Aligner (MFA, `french_mfa` acoustic model + dictionary) is run offline, once per native clip, against the clip's known transcript**, producing word (and syllable, where the dictionary allows) timestamps on the native timeline. Stored as a precomputed asset per practice (`storage/alignments/{practice_id}.json`). Because DTW already re-expresses the user's recording on the native timeline, every feedback segment's timestamp range maps directly to transcript words with zero request-time ML inference and zero changes to the user-audio pipeline. The same asset drives the karaoke transcript highlighting in Section 5.

**Explicitly rejected: the PLS-SVM phoneme-classification framework** (from the research survey). It comes from a single paper trained on a non-distributed labeled corpus (no pretrained model exists), it presupposes phoneme segmentation of the user's audio — the actual hard problem — and it is superseded by pretrained wav2vec2 XLSR phoneme recognition, which is the designated approach *if* a segmental engine is ever prioritized (Section 9 backlog). Segmental analysis of user audio remains out of scope.

### 8.5 `LIAISON_MISSED` Tag — **Resolved: descoped from FR-4**
*Original question: the PRD promised a liaison-failure tag — can the prosody pipeline deliver it?*

No. Liaison is a **segmental** phenomenon — the presence or absence of a specific consonant (/z/, /t/, /n/) — and is not detectable from F0 and RMS envelopes. The shipped DSP correctly never emitted it; the PRD was promising something the architecture cannot honestly produce. The tag is removed from FR-4. A future heuristic (checking user voicing/energy continuity across *known* liaison boundaries located via the 8.4 word timings) is recorded in the Section 9 backlog alongside the segmental engine; either would reopen this decision.

### 8.6 Rhythm & Pause Scoring — **Resolved: score the DTW warping path; joint alignment cost; pause tags**
*Original question: DTW warps time to align signals — so doesn't the score ignore exactly the timing errors ("cadence and rhythm") the product claims to correct?*

Yes, structurally — this was the largest gap in v1.1.0. When a learner applies English stress-timing to French (compressing unstressed syllables — the #1 anglophone error per the SLA research), DTW stretches their frames to fit and the pitch/energy RMSE barely moves. Three changes, versioned as `dsp-2`:
1.  **Timing component from the warping path.** Per native frame, compute the path's local slope over a ~150ms window; timing deviation = `|log2(slope)|`; aggregate RMSE-style and map through the same `100·exp(−x/K)` form (`K_TIMING` placeholder, calibrated per 8.9). Overall score becomes 55% pitch / 25% timing / 20% energy (FR-4).
2.  **`SYLLABLE_STRETCH` tag** (in the PRD since v1.0.0, never implemented): emitted for runs where local slope exceeds 1.5× or falls below 0.67× for at least the minimum run length.
3.  **Joint DTW cost + pause comparison** (FR-3): alignment distance includes energy (`λ = 0.5` placeholder) so silences anchor the warp, and unvoiced runs ≥150ms are compared between native and aligned user to emit `PAUSE_MISSED` / `PAUSE_EXTRA` — making breath-group structure (the *groupes rythmiques* from the research, and persona Clara's stated need) a first-class scored feature instead of interpolation fodder.

### 8.7 Practice Modes — **Resolved: simultaneous shadowing is the default; Solo is the fallback; the lag is tolerated, never enforced**
*Original question: the v1.1.0 flow (listen, then record alone) is delayed repetition — the exact technique the SLA research distinguishes from, and ranks below, true shadowing. Should recording happen over live playback with a 250–500ms shadow delay?*

**Shadow mode (default):** native playback and mic capture are started on the same `AudioContext` clock; recording auto-starts with playback and auto-stops at `native_duration + 1.0s` tail (the tail exists because the learner's final syllable lags the native clip's end). The learner's ~250–500ms trailing delay **emerges naturally and is never enforced or measured as a target** — the pipeline tolerates it via silence-trim + DTW. Guardrails: the Sakoe-Chiba band stays at 15% with a mandatory regression test simulating a 500ms lag (widen only if the test fails); `POST /jobs` gains a `mode` field (`shadow` | `solo`) with per-mode duration gates (FR-1); the headphones prompt and bleed check (Edge Case 3) gate every shadow take. **Solo mode** (the current listen-then-record flow) is retained: it's the no-headphones fallback and matches the research protocol's initial listening pass.

### 8.8 Native Reference Sourcing — **Resolved: self-recorded native speakers + open-licensed corpora; no film audio; TTS for dev only**
*Original question: where do the native clips come from? (Flagged in every prior doc revision, decided in none — while being the hard blocker: every job currently fails for lack of a reference.)*

Decision, in priority order: (1) **record native/near-native French speakers directly** for the seeded practices — highest quality, zero licensing risk, and doubles as the 8.9 calibration corpus; (2) **supplement from open-licensed speech corpora** (e.g., Mozilla Common Voice French, CC0) where clip style fits. **Ruled out:** copyrighted film/YouTube audio (the v1.0.0 "sorted by film genre" vision implied redistributing it — not defensible); **TTS** for any shipped practice or any calibration work (synthetic prosody as ground truth defeats the product) — permitted only as a dev-time pipeline smoke-test placeholder. Sourcing is the first work item of the next phase; it blocks everything in 8.6 and 8.9.

### 8.9 Score Calibration Protocol — **Resolved: native-vs-native must score high, monotone must score low, before any constant is trusted**
*Original question: the `exp(−rmse/K)` constants are admitted placeholders — what makes them real? And with a single reference rendition treated as ground truth, does the score punish valid prosodic variation?*

The product is framed (honestly) as **shadowing/imitation fidelity**, not absolute accent correctness — a single reference is the target *by design*. But that framing sets the calibration bar: for at least 3 practices, record **two different native renditions** plus **one deliberate monotone read**. Requirements before `K_pitch` / `K_timing` / `K_energy`, the component weights, and segment thresholds graduate from placeholders: native-vs-native scores ≥ 85 (placeholder target), and the monotone read scores at least 20 points below native-vs-native. If native-vs-native scores poorly, the constants — or the algorithm — are wrong, and no user-facing score is meaningful. This extends the existing synthetic-tone harness in `test_dsp.py`; it is the definition of done for `dsp-2`.

## 9. Additional Features (Backlog — not scheduled in Phases 1-3)
1. Chatbot that recommends practice cases based on your preferences / level.
2. **Segmental engine** (would reopen 8.2/8.5): pretrained wav2vec2 XLSR phoneme recognition on user audio + Needleman-Wunsch alignment against the canonical phoneme sequence, per the research survey. This — not PLS-SVM — is the designated approach for phoneme-level feedback (nasal vowels, /y/ vs /u/, true liaison detection) if ever prioritized.
3. **Liaison heuristic** (cheaper interim step): using the 8.4 word timings to locate obligatory liaison boundaries in the native clip, check user voicing/energy continuity across them. Imperfect but principled; would partially restore `LIAISON_MISSED`.

## 10. Implementation Roadmap
See `master_implementation_plan.md` for the current-state code audit and the phased plan (Phase 1: finish the local MVP for real — real DSP, real audio persistence, real job polling; Phase 2: harden auth/observability/testing; Phase 3: migrate to the AWS stack described in Section 4).