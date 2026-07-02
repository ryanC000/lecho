# L'Écho — Worker Core Algorithm Plan (Phase 1.2)

**Companion to:** `design_document.md` (v1.1.0), `implementation_plan.md` (Part 2, §1.2)
**Status:** Planning only — no code, no audio sourced yet.
**Purpose:** Define the real DSP worker: the algorithm, the concrete library choices, where the code lives, how data flows frontend → backend → worker, and the improvements this plan makes over `implementation_plan.md` §1.2 as originally written.

This plan assumes the Phase 1.1 work already in the repo: multipart `POST /jobs`, the `storage.py` seam, the `AudioAsset` table, and a `worker_task(job_id)` orchestrator dispatched via FastAPI `BackgroundTasks` that currently returns a placeholder score.

---

## 0. Hard prerequisite — native reference audio (unresolved)

DTW compares **two** signals. Today every seeded `Practice` has `audio_url = null` and there are no native clips anywhere in the repo (the frontend fabricates a synthetic tone via `generateMockAudioBlob`). **The worker cannot be built or validated until each practice has a real native reference clip**, and the Phase 1 acceptance test ("score differs between a good and a bad recording") is physically impossible without one.

**This plan reclassifies native-audio sourcing as a Phase 1.2 prerequisite, not a Phase 2 follow-up** (correcting `implementation_plan.md`, which defers it). The *how* (record a native speaker, license clips, or generate via TTS as a flagged placeholder) is **left open here by decision** — this document plans the algorithm only. Whatever the source, the requirement on it is fixed:

- Stored as a real WAV through the existing `storage.py` seam.
- Represented as an `AudioAsset` with `role = NATIVE_REFERENCE` (and/or `Practice.audio_url` set to its storage key).
- One reference per seeded `Practice`.

Everything below assumes such a reference exists and is reachable given a `job_id`.

---

## 1. Library decisions

The PRD offers "Parselmouth **or** Librosa" and "dtaidistance **or** hand-rolled." Concrete MVP picks:

| Concern | Choice | Rationale |
| :--- | :--- | :--- |
| F0 / pitch tracking | **praat-parselmouth** (`Sound.to_pitch_ac`) | Praat is the prosody-research standard (cf. the ProsodyPro reference in the plan). Librosa's `pyin` is music-tuned and pulls in **numba**, a heavy compile-prone dependency. |
| RMS energy | **numpy** | `sqrt(mean(frame²))` — no library needed. |
| Load / resample / mono | **parselmouth** (`Sound(path).resample(16000)`, `.convert_to_mono()`) | Avoids `soundfile`/`librosa`. We control the WAV format at ingest, so the native reader is safe. |
| DTW alignment | **Hand-rolled constrained DTW in numpy** (~40 lines) | For 500–1500 frames the O(n·m) matrix is ~2M cells → milliseconds. Hand-rolling returns the **warping path** (needed to map feedback to timestamps) and gives full control of the 3:1 abort and Sakoe-Chiba band. Avoids another C-extension install (we already hit a native-dep issue with bcrypt on Windows). |

**New dependencies for Phase 1 (added to `backend/requirements.txt`, since the worker runs in-process):** `praat-parselmouth`, `numpy`. **`scipy` is deferred to Phase 2** (Butterworth/noise pipeline) — it is not needed for the MVP algorithm. This is leaner than the plan's "parselmouth + numpy + scipy."

**Performance expectation:** the PRD's "10–45s per sample" is pessimistic. Parselmouth F0 on a 15s clip is <1s, RMS is instant, DTW is milliseconds → **~1–3s total**, well under the 12s KPI. The mock's `time.sleep(5)` should be removed.

---

## 2. Code organization

`implementation_plan.md` §1.2 says "rewrite `worker/main.py`'s `process_audio()` and wire it into `backend/main.py`." That entangles the algorithm with DB/storage I/O and creates an awkward `worker/` ↔ `backend/` import cycle. Instead:

- **`backend/dsp.py` — pure, DB-free, stateless functions.** Inputs are paths/arrays; outputs are arrays/scores/segment dicts. No SQLAlchemy, no storage calls. Directly unit-testable with a synthetic sine-wave pair.
- **Orchestrator stays in the worker task** (`backend/main.py`'s existing `worker_task`, optionally extracted to `backend/job_runner.py`): opens the DB session, resolves paths, calls `dsp`, writes `AnalysisSegment` rows + the JSON archive + the score, and handles failures. The current try/except → `FAILED` + `error_message` plumbing is reused.
- **`worker/main.py` becomes a thin standalone entrypoint** for Phase 3 that imports the *same* `dsp` module and consumes from SQS — no algorithm duplication.

**Continuity decision:** the worker's only input is `job_id`; it fetches everything else (user path, native path, native duration) from the DB. That is exactly the shape of a future SQS message, so the Phase 3 split becomes a transport swap rather than a rewrite. The current `worker_task(job_id)` already follows this.

---

## 3. Data flow: frontend → backend → worker

Most of the path exists after Phase 1.1; the worker leg is the new part.

```
BROWSER                          BACKEND (FastAPI)                     WORKER (in-process now)
───────                          ─────────────────                     ──────────────────────
record → transcode to    POST /jobs (multipart)
16-bit mono WAV  ───────► validate (auth, ±20%, 2–15s, WAV)
(blobToWav)               store user WAV → AudioAsset(USER_RECORDING)
                          create ProsodyJob(PENDING)
                          BackgroundTasks.add_task(run_job, job_id) ──► run_job(job_id):
                          return 202 {job_id}                              fetch job → practice → native path
                                                                           fetch AudioAsset(USER_RECORDING) → user path
   poll GET /jobs/{id} ◄─ status PENDING/SUCCESS/FAILED                    dsp: load+extract(user), load+extract(native)
   every 2s (built)                                                        normalize → DTW(pitch) → apply path to both
                                                                           score() → segments() → archive JSON
                          ◄──────────────────────────────────────────── write AnalysisSegment rows,
                          GET /jobs/{id} returns real score,               storage/analysis/{job_id}.json,
                          segments, transcript                             job.status=SUCCESS, score, algo_version
```

**Downstream gap (out of scope for the worker, flagged):** the PRD's pitch-overlay visualizer needs the aligned curves. A `GET /jobs/{id}/coordinates` endpoint (serving the archive JSON) will be required for that chart. The worker's job is only to **produce** the archive; serving it belongs with the visualizer work.

---

## 4. The algorithm (MVP)

Pure functions in `dsp.py`, on one canonical timeline (the native clip's).

1. **Load & standardize** both clips → mono, 16 kHz. Defensive: native source may be stereo/44.1k; the user clip is mono but typically 48k.
2. **Extract per 10 ms frame:** F0 via `to_pitch_ac` (yields Hz + voiced/unvoiced); RMS via numpy over ~25 ms windows on the same hop so the two feature streams share a frame grid.
3. **Trim** leading/trailing silence by an RMS threshold, so dead air doesn't dominate alignment. The 3:1 ratio safety check operates on the **trimmed** lengths.
4. **Interpolate F0 across unvoiced gaps** (linear) to produce a continuous contour for alignment; retain the voiced mask separately for tagging. *(Raw F0 has holes at consonants/pauses that would corrupt DTW — this is the standard prosody fix and was unspecified in the original plan.)*
5. **Normalize per clip** (PRD FR-3, computed independently for each clip):
   - `semitone = 12 · log2(f0 / median_voiced_f0)`
   - `rms_z = (rms − mean) / std`
6. **Align once on the pitch (semitone) contour** → a single warping path; **apply that same path to both** the pitch and RMS arrays. *(Clarifies the plan: aligning the two signals independently would yield two different time-warps and make a coherent "you diverged at time T" story impossible. Pitch is the reliable alignment cue; energy rides the same path.)* Enforce a Sakoe-Chiba band and the **3:1 length-ratio abort** (PRD §6).
7. **Score:**
   - `pitch_score  = map(RMSE of aligned semitone arrays)`
   - `energy_score = map(RMSE of aligned rms_z arrays)`
   - `overall = 0.7 · pitch_score + 0.3 · energy_score` (weight is a named constant, tunable)
8. **Segments:** slide over the aligned timeline, find contiguous frames where deviation exceeds a threshold, map those indices back to **native timestamps** via the warping path, and tag them.
9. **Archive:** write `{times, native_f0_hz, user_f0_hz_aligned, native_semitone, user_semitone_aligned, native_rms, user_rms_aligned, voiced_masks}` to `storage/analysis/{job_id}.json`. Store both Hz (the visualizer shows Hz) and the normalized arrays (for deviation coloring). `AnalysisSegment.s3_coordinates_json_path` points to this file.

### Proposed `dsp.py` surface (illustrative)

```python
FRAME_HOP_S = 0.01
TARGET_SR   = 16000
PITCH_WEIGHT, ENERGY_WEIGHT = 0.7, 0.3
MAX_LENGTH_RATIO = 3.0

@dataclass
class ProsodyFeatures:
    times: np.ndarray        # frame-center times
    f0_hz: np.ndarray        # 0 where unvoiced
    voiced: np.ndarray       # bool mask
    f0_semitone: np.ndarray  # normalized, gap-interpolated
    rms: np.ndarray
    rms_z: np.ndarray

def load_mono_16k(path) -> tuple[np.ndarray, int]: ...
def extract_features(samples, sr) -> ProsodyFeatures: ...
def trim_silence(feat) -> ProsodyFeatures: ...
def align(native, user) -> "Aligned": ...          # DTW on semitone; raises LengthRatioError
def score(aligned) -> tuple[float, float, float]:   # overall, pitch, energy
def make_segments(aligned) -> list[dict]: ...
def build_archive(aligned) -> dict: ...
```

---

## 5. Scoring calibration (the real empirical unknown)

Mapping an RMSE distance to a 0–100% is a judgment call — e.g. `score = 100 · exp(−rmse / K)`. `K` cannot be derived on paper; it is tuned by running the **good-vs-bad harness** (an expressive read must score clearly above a monotone read of the same line) and picking a constant that separates them.

**This plan moves the scoring-calibration harness into 1.2**, not Phase 2:
- A synthetic **sine-wave pair with a known pitch offset** → assert the scorer produces the expected relative score (deterministic unit test).
- A **good/bad differentiation check** on a real practice line → the definition of done for the worker.

Until real users generate real recordings, thresholds and `K` are informed guesses; the harness is what keeps them honest.

---

## 6. Feedback tagging: MVP subset vs. stretch

- **MVP (ship in 1.2):**
  - `INTONATION_DROP` — pitch deviation where the user contour sits below the native rise.
  - `ENERGY_FLAT` / `EMPHASIS_MISSED` — native energy peak the user flattens.
  - Both fall directly out of per-frame deviation thresholds on the aligned arrays.
- **Stretch (needs voiced-mask reasoning, don't block MVP):**
  - `LIAISON_MISSED` — native voiced-continuous where the user has a gap.
  - `SYLLABLE_STRETCH` — warping path shows strong local time compression/expansion.

Thresholds are deliberately not over-tuned now; they are guesses until real recordings exist.

---

## 7. Failure modes (MVP subset of PRD §6)

- **No detectable speech** (silent/garbled → F0 all-unvoiced): `FAILED`, `error_message = "No speech detected — please record in a quieter space."` (Full bandpass + `noisereduce` + SNR pipeline stays Phase 2; this is the graceful-degradation stub.)
- **3:1 length ratio after trim:** abort → `FAILED` with the duration-mismatch message.
- **Native reference missing:** `FAILED` with a loud internal error (should not occur once §0 is resolved).

The existing `worker_task` try/except → `FAILED` + `error_message` already provides this envelope.

---

## 8. Summary of improvements over `implementation_plan.md` §1.2

1. **Native audio is a Phase 1.2 prerequisite, not Phase 2** (sourcing method left open here).
2. **Pure `dsp.py` split from the DB orchestrator** — testable, and clean for the Phase 3 container split.
3. **Worker input = `job_id` only** (fetch state from DB) → Phase 3 SQS becomes a transport swap.
4. **Drop `scipy` and any C-extension DTW from the MVP** — `parselmouth` + `numpy` + hand-rolled DTW only; fewer Windows install landmines.
5. **Specify the two under-defined DSP steps:** unvoiced-gap interpolation, and "align on pitch, apply the path to both signals."
6. **Scoring-calibration harness moves into 1.2** — it is the definition of done, not a deferred Phase 2 test.
7. **Correct the performance expectation** (~1–3s, not 10–45s) and delete the `time.sleep`.
8. **Name the downstream gap:** a `GET /jobs/{id}/coordinates` endpoint is needed for the visualizer; the worker only produces the archive.

---

## 9. Open questions / assumptions log

- **Native-audio sourcing method (§0):** unresolved by decision; blocks any real DSP validation.
- **Scoring map `score = f(rmse)` and constant `K`:** placeholder; requires the good/bad harness to fix.
- **Feedback thresholds:** guesses until real recordings exist.
- **Frame hop (10 ms) and silence-trim threshold:** reasonable defaults, revisit against real clips.
- **Pitch floor/ceiling for `to_pitch_ac`:** should be set to a speech range (e.g. 75–500 Hz) rather than Praat defaults; confirm during implementation.
```
