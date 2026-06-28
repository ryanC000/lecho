# Product Requirement Document (PRD) & Design Specification

**Product Name:** L'Écho
**Version:** 1.0.0-PRD
**Author:** Technical Product Manager & Lead UX/UI Designer

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
*   The processing service must compute the fundamental frequency ($F_0$ contour) map and amplitude values of both audio sources.
*   The system must apply a Dynamic Time Warping (DTW) mathematical alignment model to normalize the user's speaking rate to match the native speaker's timeline.

### FR-4: Scoring & Insight Generation
*   The system must output an absolute percentage matching score calculated by computing the Euclidean distance between the aligned pitch arrays.
*   The system must isolate intervals where variance drops below an acceptable threshold and map these frames to specific timestamps to generate contextual improvement tips.

## 4. Technical Architecture & Constraints

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
    native_pitch_values FLOAT[] NOT NULL,
    user_pitch_values FLOAT[] NOT NULL,
    feedback_tag VARCHAR(100), -- LIAISON_MISSED, INTONATION_DROP, SYLLABLE_STRETCH
    explanation TEXT
);
```

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
*   **System Behavior:** The DTW matrix calculation checks if the length ratio between the two arrays exceeds a $3:1$ scale. If it does, the mathematical alignment drops early before throwing memory leaks. The database flags this error, and the user interface outputs: "Your recording duration differs significantly from the target clip. Try keeping your pace closer to the native speaker's speed."

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

## 8. TPM & Architectural Clarification Check (Gaps to Resolve)

Before moving this PRD directly into an engineering sprint, we need to clarify three key technical boundaries:

1.  **The Choice of Signal Comparison Depth:** Should the background worker analyze Pitch/Intonation ($F_0$) alone, or should we also measure Energy/Volume ($RMS$ amplitude)? Measuring energy captures syllable emphasis and structural pauses, which adds depth to the feedback but increases the algorithmic complexity of the worker container.
2.  **Linguistic Scope Control:** Are we strictly evaluating prosody (the cadence, rhythm, and melody), or do we want the worker to flag instances where the user says the completely wrong word? If we want to check for literal word errors, we would need to add an explicit Speech-to-Text alignment step (like Whisper) before running the DTW pitch analysis.
3.  **The Multi-User Scaling Budget:** Under a heavy testing environment (e.g., a whole class of language students submitting responses simultaneously), how do you want the worker cluster to handle scaling? We can write Terraform rules to autoscale our EC2 container fleet based on the SQS queue depth, but we need to set a maximum instance cap to keep your AWS billing safe.
