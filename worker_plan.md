# L'Écho — Worker Core Algorithm (Phase 1.2)

**Companion to:** `design_document.md` (v1.2.0), `implementation_plan.md`
**Status:** Implemented — this doc describes the shipped **`dsp-1`** algorithm. The **`dsp-2`** revision (joint DTW cost, timing score from the warping path, `SYLLABLE_STRETCH` / `PAUSE_MISSED` / `PAUSE_EXTRA` tags, calibration protocol) is specced in PRD §8.6/§8.9 and `implementation_plan.md` Phase 1.5; the §6 "stretch" items and §8 open items below are superseded by those decisions (`LIAISON_MISSED` is descoped entirely, PRD §8.5).

The worker takes a `job_id`, loads the user recording and the practice's native reference, and produces an overall score (0–100), feedback segments, and a coordinate archive for the pitch-overlay visualizer. It runs in-process via FastAPI `BackgroundTasks` today; the algorithm is factored so the Phase 3 SQS/container split is a transport swap.

---

## 0. Prerequisite — native reference audio

DTW compares **two** signals. Every seeded `Practice` currently has `audio_url = null` and no native clips exist in the repo, so **prosody scoring is blocked until each practice has a real native reference clip**. The worker fails such jobs loudly (§7) rather than fabricating a score; this is expected until references are sourced.

Requirement on each reference (sourcing method — record, license, or TTS — is out of scope for this doc):

- Stored as a real WAV through the `storage.py` seam.
- Linked to its `Practice` via `Practice.audio_url` set to the storage key. (An `AudioAsset` row with `role = NATIVE_REFERENCE` is optional bookkeeping; the worker resolves the path from `Practice.audio_url`.)
- One reference per `Practice`.

---

## 1. Library choices

| Concern | Choice | Justification |
| :--- | :--- | :--- |
| F0 / pitch tracking | **praat-parselmouth** (`Sound.to_pitch_ac`) | Praat is the prosody-research standard. Librosa's `pyin` is music-tuned and pulls in **numba**, a heavy compile-prone dependency. |
| RMS energy | **numpy** | `sqrt(mean(frame²))` — no library needed. |
| Load / resample / mono | **parselmouth** (`Sound(path).resample(16000)`, `.convert_to_mono()`) | Avoids `soundfile`/`librosa`. We control the WAV format at ingest, so the reader is safe. |
| DTW alignment | **Hand-rolled banded DTW in numpy** (~40 lines) | Not a capability gap — `dtw-python` also returns the warping path and supports a Sakoe-Chiba band. The reason is dependency risk: `dtw-python` ships **C + Cython extensions**, and on Python 3.14 (this project's interpreter) a missing prebuilt wheel forces a source build needing MSVC — the same class of failure already hit with `bcrypt`. The problem is tiny (a few hundred to ~1500 frames per side → a ~2M-cell O(n·m) matrix → milliseconds), so a hand-rolled version costs nothing in performance and stays fully transparent for score tuning. |

**Dependencies added to `backend/requirements.txt`:** `praat-parselmouth`, `numpy` (both installed from prebuilt cp314 wheels — no compiler needed). **`scipy` is deferred to Phase 2** (Butterworth/noise pipeline); it is not needed for the MVP algorithm.

**Performance:** Parselmouth F0 on a 15s clip is <1s, RMS is instant, DTW is milliseconds → **~1–3s total**, well under the 12s KPI.

---

## 2. Code organization

- **`backend/dsp.py` — pure, DB-free, stateless functions.** Inputs are paths/arrays; outputs are arrays/scores/segment dicts. No SQLAlchemy, no storage calls. Directly unit-testable with a synthetic sine-wave pair (`test_dsp.py`).
- **Orchestrator lives in `backend/main.py::worker_task`:** opens the DB session, resolves the user and native paths, calls `dsp`, writes `AnalysisSegment` rows + the JSON archive + the score, and maps `dsp.DspError` subtypes to `FAILED` + `error_message`.
- **`worker/main.py`** stays a thin Phase 3 entrypoint that will import the *same* `dsp` module and consume from SQS — no algorithm duplication.

The worker's only input is `job_id`; everything else (user path, native path) is fetched from the DB — the shape of a future SQS message, so Phase 3 is a transport swap, not a rewrite.

---

## 3. Data flow: frontend → backend → worker

```
BROWSER                          BACKEND (FastAPI)                     WORKER (in-process now)
───────                          ─────────────────                     ──────────────────────
record → transcode to    POST /jobs (multipart)
16-bit mono WAV  ───────► validate (auth, ±20%, 2–15s, WAV)
(blobToWav)               store user WAV → AudioAsset(USER_RECORDING)
                          create ProsodyJob(PENDING)
                          BackgroundTasks.add_task(worker_task, job_id) ─► worker_task(job_id):
                          return 202 {job_id}                              resolve user path (AudioAsset)
                                                                           resolve native path (Practice.audio_url)
   poll GET /jobs/{id} ◄─ status PENDING/SUCCESS/FAILED                    dsp: load+extract(native), load+extract(user)
   every 2s                                                                trim → DTW(pitch) → project user onto native
                                                                           score() → segments() → archive JSON
                          ◄──────────────────────────────────────────── write AnalysisSegment rows,
                          GET /jobs/{id} returns real score,               storage/analysis/{job_id}.json,
                          segments, transcript                             job.status=SUCCESS, score, algo_version
```

**Downstream gap (out of scope for the worker):** the pitch-overlay visualizer needs the aligned curves. A `GET /jobs/{id}/coordinates` endpoint (serving the archive JSON) is required for that chart. The worker only **produces** the archive; serving it belongs with the visualizer work.

---

## 4. The algorithm

Pure functions in `dsp.py`, on one canonical timeline — **the native clip's**.

1. **Load & standardize** both clips → mono, 16 kHz. Defensive: the native source may be stereo/44.1k; the user clip is mono but typically 48k. Resampling to a shared rate is what makes frame `i` of one clip comparable to frame `i` of the other.
2. **Extract per 10 ms frame:** F0 via `to_pitch_ac` (Hz + voiced/unvoiced), pitch floor/ceiling set to a speech range (75–500 Hz), not Praat defaults. RMS via numpy over ~25 ms windows centered on the same frame times, so F0 and RMS share one frame grid without a second resampling step.
3. **Trim** leading/trailing silence by an RMS threshold (frames below 10% of peak RMS), so dead air doesn't dominate alignment. The 3:1 length-ratio check runs on the **trimmed** lengths.
4. **Interpolate F0 across unvoiced gaps** (linear). Raw F0 has holes at consonants/pauses; a 0 Hz frame reads as a huge pitch drop and corrupts DTW distance. The voiced mask is retained separately so tagging never mistakes an interpolated frame for a real measurement.
5. **Normalize per clip, independently** (PRD FR-3):
   - `semitone = 12 · log2(f0 / median_voiced_f0)` — reference is the clip's own median **voiced** F0. This deliberately removes absolute pitch level, so two speakers with different natural registers saying the same line with the same intonation both score well; what's compared is contour *shape*, not Hz.
   - `rms_z = (rms − mean) / std`
6. **Align on the pitch (semitone) contour** → one warping path (banded DTW). **Project the user's arrays (f0, semitone, rms, rms_z, voiced) onto the native timeline** using that same path — a native frame that matched several user frames takes their mean. Aligning pitch and energy independently would yield two different time-warps and make a coherent "you diverged at time T" story impossible; pitch is the reliable alignment cue and energy rides the same path. Enforce a Sakoe-Chiba band and the **3:1 length-ratio abort** (PRD §6).
7. **Score** (each 0–100):
   - `pitch_score  = 100 · exp(−RMSE(native, user semitone) / K_pitch)`
   - `energy_score = 100 · exp(−RMSE(native, user rms_z) / K_energy)`
   - `overall = 0.7 · pitch_score + 0.3 · energy_score` — pitch weighted higher because intonation is the dominant accent cue; weights are named constants.
8. **Segments:** contiguous runs on the native timeline where deviation exceeds a threshold, mapped to native timestamps and tagged (§6).
9. **Archive:** write `{times, native_f0_hz, user_f0_hz_aligned, native_semitone, user_semitone_aligned, native_rms, user_rms_aligned, voiced_masks}` to `storage/analysis/{job_id}.json`. Both Hz (the visualizer shows Hz) and the normalized arrays (for deviation coloring) are stored. `AnalysisSegment.s3_coordinates_json_path` points to this file.

**Scope:** this measures **prosody** (pitch contour, energy, rhythm), not **segmental pronunciation** (individual phonemes — nasal vowels, /ʁ/). Segmental scoring would need formants/MFCCs or an ASR phoneme aligner and is out of scope for the MVP.

### `dsp.py` surface

```python
FRAME_HOP_S = 0.01
TARGET_SR   = 16000
PITCH_FLOOR_HZ, PITCH_CEILING_HZ = 75.0, 500.0
PITCH_WEIGHT, ENERGY_WEIGHT = 0.7, 0.3
MAX_LENGTH_RATIO = 3.0
SAKOE_CHIBA_BAND_FRAC = 0.15
SILENCE_RMS_FRAC = 0.1
SCORE_K_PITCH_SEMITONES, SCORE_K_ENERGY_Z = 4.0, 1.5   # placeholder, tuned by the harness

@dataclass
class ProsodyFeatures:
    times: np.ndarray; f0_hz: np.ndarray; voiced: np.ndarray
    f0_semitone: np.ndarray; rms: np.ndarray; rms_z: np.ndarray

def load_mono_16k(path) -> parselmouth.Sound: ...
def extract_features(snd) -> ProsodyFeatures: ...
def trim_silence(feat) -> ProsodyFeatures: ...            # raises NoSpeechDetectedError
def align(native, user) -> Aligned: ...                   # DTW on semitone; raises LengthRatioError
def score(aligned) -> tuple[float, float, float]: ...     # overall, pitch, energy
def make_segments(aligned) -> list[dict]: ...
def build_archive(aligned) -> dict: ...
```

---

## 5. Scoring calibration

Mapping RMSE → 0–100% is a judgment call: `score = 100 · exp(−rmse / K)`. `K` cannot be derived on paper; it is tuned so an expressive read scores clearly above a monotone read of the same line. The calibration harness lives in `test_dsp.py`:

- A **synthetic pair** (rising-intonation chirp vs. flat tone at the same average pitch) → asserts the deliberate contour difference produces a clearly, deterministically lower score. This is the deterministic unit test.
- A **good/bad differentiation check on a real practice line** is the eventual definition of done — deferred until native reference audio exists (§0).

`K_pitch`, `K_energy`, and the segment thresholds are informed guesses until real recordings exist; the harness is what keeps them honest.

---

## 6. Feedback tagging

- **MVP (shipped):**
  - `INTONATION_DROP` — user contour sits ≥2 semitones below the native rise.
  - `ENERGY_FLAT` / `EMPHASIS_MISSED` — native energy peak (≥1σ) the user flattens; tagged `EMPHASIS_MISSED` when the native run is a local peak, else `ENERGY_FLAT`.
  - Both fall out of per-frame deviation thresholds on the aligned arrays (min run length 3 frames).
- **Stretch (deferred, needs voiced-mask reasoning):**
  - `LIAISON_MISSED` — native voiced-continuous where the user has a gap.
  - `SYLLABLE_STRETCH` — warping path shows strong local time compression/expansion.

Thresholds are deliberately not over-tuned; they are guesses until real recordings exist.

---

## 7. Failure modes (MVP subset of PRD §6)

- **No detectable speech** (silent/all-unvoiced after trim): `FAILED`, `NoSpeechDetectedError`. Full bandpass + `noisereduce` + SNR pipeline stays Phase 2; this is the graceful-degradation stub.
- **3:1 length ratio after trim:** abort → `FAILED`, `LengthRatioError`.
- **Native reference missing:** `FAILED` with a user-facing message (expected until §0 is resolved; not the user's fault, not fixed by re-recording).

`worker_task`'s try/except → `FAILED` + `error_message` provides the envelope; `dsp.DspError` subtypes carry the specific reason.

---

## 8. Open items

- **Native-audio sourcing (§0):** blocks any real DSP validation.
- **Scoring constants `K_pitch` / `K_energy` and segment thresholds:** placeholders until the good/bad harness runs on real recordings.
