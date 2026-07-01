# Product Requirement Document (PRD) & Design Specification

**Product Name:** L'Écho
**Version:** 1.1.0-PRD (Revised — gaps resolved, phased against actual codebase)
**Author:** Technical Product Manager & Lead UX/UI Designer

**Revision Note (v1.1.0):** This revision resolves the three open questions from Section 8 of v1.0.0 and reconciles the PRD against the current state of the repository (see `implementation_plan.md` for the full audit and phased build-out). The biggest structural change: the PRD's target architecture (SQS/S3/Postgres/Terraform) is now explicitly framed as a **later phase**. The repository today is a local-first MVP (SQLite, in-process background tasks, local disk, a fully mocked worker), and the plan is to make that MVP *real* — real DSP, real audio persistence, real job status — before migrating to the AWS stack described in Section 4.

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
3.  **Recording:** The user clicks the record button, performs the line using the shadowing technique, and submits their `.wav` file.
4.  **Ingestion & Deferral:** The UI immediately informs the user that their audio is safely queued for matching. The user is redirected back to their practice history or allowed to try another clip.
5.  **Notification & Review:** Once the background task completes, an alert points the user to their finalized Prosody Analysis Dashboard.
6.  **Insight Consumption:** The user interacts with the generated pitch chart, visually identifying exactly where their rhythm expanded or where their pitch failed to match the target curve.

## 3. Functional Requirements

### FR-1: Audio Capture & Ingestion
*   The system must record high-quality uncompressed audio via the browser's Web Audio API.
*   The system must enforce a strict duration boundary (minimum 2 seconds, maximum 15 seconds) to prevent buffer overruns on the background processing cluster.

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

### FR-4: Scoring & Insight Generation
*   The system must output an absolute percentage matching score calculated by computing the Euclidean distance between the aligned, **normalized** pitch and RMS arrays (weighted combination — default weighting 70% pitch / 30% energy, tunable; see `implementation_plan.md` Phase 1).
*   The system must isolate intervals where variance drops below an acceptable threshold and map these frames to specific timestamps to generate contextual improvement tips (tags: `INTONATION_DROP`, `LIAISON_MISSED`, `SYLLABLE_STRETCH`, plus new `ENERGY_FLAT` / `EMPHASIS_MISSED` tags enabled by RMS analysis).
*   Scope is strictly prosody (pitch, rhythm, cadence, emphasis). The system does **not** perform word-correctness checking — resolved, see Section 8.2.

## 4. Technical Architecture & Constraints

**Phasing note:** the stack below is the **Phase 3 (cloud) target**, not the current state. The repository today runs a local-first MVP: SQLite instead of PostgreSQL, in-process FastAPI `BackgroundTasks` instead of SQS + a separate worker container, and local disk instead of S3. See `implementation_plan.md` for the phase-by-phase migration path and why local-first comes first (faster iteration on the DSP algorithm itself, no AWS spend, before paying the infra cost of the queue/object-store split).

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
    feedback_tag VARCHAR(100), -- LIAISON_MISSED, INTONATION_DROP, SYLLABLE_STRETCH, ENERGY_FLAT, EMPHASIS_MISSED
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
*   **Top Area:** Context Banner containing the French text sentence with accent tags highlighting liaison rules.
*   **Middle Area:** The Pitch Interactive Visualizer. A timeline tracking frequency in Hertz (Hz) against time in seconds.
*   **Bottom Area:** Floating Action Tray containing the single mic control trigger, audio replay options, and detailed metric breakdown cards.

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

### 3. Sudden Network Disconnection Post-Upload
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

These three questions blocked moving from PRD to sprint in v1.0.0. All three are now resolved; each entry keeps the original question for traceability.

### 8.1 Signal Comparison Depth — **Resolved: F0 + RMS, both speaker-normalized**
*Original question: pitch alone, or also energy/volume?*

Pitch alone would miss syllable emphasis, breath-group pauses, and liaison drops — all core to the "cadence and rhythm" half of the product's value prop, not just intonation. So both signals are in scope. The complexity concern in the original question was really about comparability across voices, not algorithmic cost — RMS extraction is cheap once F0 extraction is already happening (same framing, same STFT machinery in Parselmouth/Librosa). The real fix is normalization, not omission: see the new methodology in FR-3 above (semitone-relative F0, per-clip z-scored RMS). Default scoring weight is 70% pitch / 30% energy; this weight is a tunable parameter, not hardcoded, so it can be adjusted after real user testing.

### 8.2 Linguistic Scope Control — **Resolved: prosody only, no word-correctness checking**
*Original question: pure prosody, or also flag wrong words via STT?*

Scope stays strictly prosodic (pitch, rhythm, cadence, emphasis). Adding a Whisper/STT word-alignment step would meaningfully expand infrastructure (hosting an STT model, handling recognition errors/confidence thresholds, a second scoring axis with its own UX) for a feature that's adjacent to, not central to, the "accent barrier" problem this product targets. If word-correctness checking becomes a priority later, it should be scoped as its own feature addition (Phase 4+), not folded into the current DSP pipeline.

### 8.3 Multi-User Scaling Budget — **Resolved (default, pending real usage data): defer autoscaling to the cloud migration phase; cap at 5 concurrent worker instances**
*Original question: how should the worker cluster scale under classroom-sized load, and what's the instance cap?*

This entire question is moot until Phase 3 (AWS migration) — the current local-first MVP has one worker process and no SQS. For planning purposes, Phase 3's Terraform config should default to an SQS-queue-depth-triggered autoscaling policy with a **hard cap of 5 EC2 worker instances**, which comfortably covers a class-sized burst (~20-30 students) processing sequentially within the KPI target (<12s wall clock) without material AWS billing risk. This default is a placeholder — it should be revisited once there's real usage data from the local-first MVP (Phase 1/2) showing actual concurrent submission patterns.

## 9. Additional Features (Backlog — not scheduled in Phases 1-3)
1. Chatbot that recommends practice cases based on your preferences / level.

## 10. Implementation Roadmap
See `implementation_plan.md` for the current-state code audit and the phased plan (Phase 1: finish the local MVP for real — real DSP, real audio persistence, real job polling; Phase 2: harden auth/observability/testing; Phase 3: migrate to the AWS stack described in Section 4).