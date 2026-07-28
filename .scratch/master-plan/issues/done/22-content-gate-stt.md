# 22 — Content gate v2: recognize the words (STT) instead of MFA alignment likelihood

**Context (2026-07-21):** Ticket 20 shipped a content gate that force-aligns the practice transcript against the user's take with MFA and rejects on a low per-utterance `speech_log_likelihood`. Calibration on freshly-recorded gibberish takes proved that signal **does not discriminate content** — a threshold cannot be chosen. This ticket replaces the likelihood signal with actual speech-to-text: recognize what was said and compare it to the practice transcript.

**Measured (owner recorded `native_audio/gibberish{1..4}.wav`; each take force-aligned via the ticket-20 gate, `speech_log_likelihood`):**

| correct-words take (must PASS) | speech_ll | | gibberish take (must FAIL) | speech_ll |
|---|---|---|---|---|
| p7 emulation | -47.92 | | gibberish1 vs p7 | -49.54 |
| p7 monotone | -49.32 | | gibberish2 vs p7 | **-47.90** |
| p7 low_effort | -51.10 | | gibberish3 vs p7 | -52.83 |
| p2 emulation | -47.07 | | gibberish4 vs p7 | -58.50 |
| p2 monotone | -47.57 | | | |
| p2 low_effort | -47.75 | | | |

The distributions overlap: gibberish2 (-47.90) beats three genuine takes; gibberish1 (-49.54) sits inside the genuine cluster. No threshold passes all six correct takes and rejects all four gibberish takes.

**Root cause:** `mfa align` is *forced* alignment — it maps the transcript we hand it onto the audio no matter what was actually said, so it never "recognizes" content. The remaining likelihood is dominated by the cross-speaker acoustic floor, not by whether the right words were spoken (the same wall the MFCC segmental axis hit — ADR 0003 NO-GO). Prosody can't gate content (ticket 20) and neither can forced-alignment likelihood; the only thing that can is **recognizing the words**.

**Fix direction (owner steer 2026-07-21): a lightweight local STT, not MFA.**
- Transcribe the user take with a small offline ASR, normalize both sides (reuse `content_gate.normalize_transcript` / `align_natives` rules), and reject when the recognized text diverges too far from the practice transcript — word-error-rate (or token overlap) above a threshold → "we couldn't make out the line". WER separates cleanly (gibberish ≈ 100% WER vs the target; genuine takes low), unlike acoustic likelihood.
- **Model choice (open — owner deferred):** owner wants lightweight. Candidates: **faster-whisper `base`** in a subprocess env (recommended — strong French accuracy so real accented learners aren't wrongly rejected; CPU ~2-5s/clip; ~140MB; local), **vosk** French small model (lightest, ~50MB, but lower accuracy → higher false-reject risk), or a cloud STT (rejected: breaks local-first, sends audio off-machine). MFA *transcribe* is technically available (`french_mfa_lm` LM now downloaded) but slow (>2 min for 5 short clips) and clunky — not the path.
- **Architecture:** run the ASR as a subprocess in a dedicated env (reuse the conda-run pattern `content_gate.assess` already has — install the model into the `mfa` conda env or a sibling env) so the Windows/3.14 dependency rule is untouched. Keep the pure/orchestration split and fail-open-on-infra-error behavior from ticket 20.
- **Watch:** Whisper can hallucinate fluent text on noise/gibberish — validate on the four gibberish takes that recognized text still diverges from the target (it should: it invents *different* words, not the target sentence). Calibrate the WER threshold on the genuine-vs-gibberish set above before enabling rejection.

**Supersedes the ticket-20 gate.** The committed likelihood gate (`content_gate.assess` in `worker_core.run`) is always-on but measure-only (`CONTENT_GATE_MIN_SPEECH_LOGLIK = None`, never rejects) and costs **~45s/job** for a signal now known to be dead. When this lands, replace it; until then consider disabling it (short-circuit `assess`) so real jobs aren't paying 45s for nothing.

**Corpus assets ready:** `native_audio/gibberish{1..4}.wav` (recorded 2026-07-21) + the six correct-words takes above are the calibration set for the WER threshold.

- [x] Lightweight STT chosen + installed in a subprocess env (dep pre-checked per the plan's wheel rule; env documented) — faster-whisper `base` in a new user-scope `stt` conda env (`conda create -n stt python=3.11`, `pip install faster-whisper`; `ctranslate2` has no cp314 wheel → out of `backend/.venv`, `requirements.txt` untouched). Env + calibration documented in `scripts/README_STT.md`.
- [x] `content_gate` recognizes the take's words and rejects on high WER vs the practice transcript (pure WER/decision unit-tested; ASR integration opt-in like the MFA test) — `assess` shells `conda run -n stt python stt_runner.py`; `word_error_rate`/`decide`/`normalize_transcript` unit-tested; STT integration opt-in via `RUN_STT_TESTS=1`.
- [x] WER threshold graduated on the gibberish-vs-correct set (all six correct takes PASS, all four gibberish FAIL); Decision log updated — measured (faster-whisper base): correct WER 0.13–0.60, gibberish 1.00–1.40 (clean [0.60, 1.00] gap); `CONTENT_GATE_MAX_WER = 0.80` → 6/6 correct PASS, 4/4 gibberish FAIL. Decision log entry added (2026-07-28). Whisper hallucination-on-gibberish risk validated benign (invents *different* words, never the target).
- [x] Ticket-20 likelihood gate replaced/removed; ~45s/job MFA-in-worker cost retired — MFA constants, `parse_analysis_csv`, `_write_wav_16k`, `CONTENT_GATE_MIN_SPEECH_LOGLIK`, the `dsp`/`numpy` imports and the `RUN_MFA_TESTS` test all removed; recognition now ~2–5s/clip.
- [x] End-to-end: a gibberish take is rejected with "we couldn't make out the line" before scoring; a genuine take scores as before — verified through the real conda-run `assess` path: `gibberish1` → `assessed=True, passed=False` (WER 1.50) → worker `fail_job(REJECT_MESSAGE)`; `napoleon_emulation` → `assessed=True, passed=True` (WER 0.30) → scores. 🧑 A full worker-level job E2E (real gibberish job through `worker_core.run`) is not automated — the worker branch (`assess` → `fail_job`) is unchanged from ticket 20, which was validated E2E.

---

**Status: done — 2026-07-28, commit `c2efeb2`.** STT content gate implemented, calibrated (6/6 correct PASS, 4/4 gibberish FAIL at `CONTENT_GATE_MAX_WER = 0.80`), and wired into the worker; ~45s/job MFA cost retired. faster-whisper `base` quarantined in the `stt` conda env (wheel rule honored). Full backend suite green (52 passed, 1 STT integration skipped by default; 9/9 with `RUN_STT_TESTS=1`).
