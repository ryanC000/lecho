# 17 — Ambient-noise pipeline

**What to build:** User recordings get cleaned before scoring: a bandpass (80–4000 Hz Butterworth) plus spectral noise reduction using the first 300ms as the noise profile, and an SNR estimate persisted to the recording's asset row (the column exists, never populated). Applied to the user clip only, and only from the worker orchestrator — the pure DSP pipeline and its deterministic tests stay untouched, because denoising changes RMS contours.

**Precondition:** scipy and noisereduce must install as prebuilt cp314 wheels (`--only-binary :all:`). If they don't, set this ticket's Status to `needs-info`, record the blocker in the master plan's Decision log, and stop — the no-speech graceful failure already covers the UX.

**Blocked by:** None — can start immediately.

**Status:** done — commit `a449200` + review fixes, 2026-08-03

- [x] Wheel pre-check performed and outcome recorded before any requirements change — `pip download --only-binary :all:` resolved `scipy 1.18.0` + `noisereduce 3.0.3` **and their full transitive closure** as prebuilt wheels before `requirements.txt` was touched. ⚠️ Resolved for **cp312**, not cp314: the project venv is Python 3.12.4, so the ticket's cp314 stop-condition was never actually exercised. Outcome recorded in the Decision log (2026-08-03).
- [x] Denoise applied only in the orchestrator; dsp test suite untouched and green — `dsp.denoise_clip` is called from `worker/core.py` only, on the user clip, after the bleed gate. `features.py`, `test_dsp.py` and `test_dsp2.py` are unmodified. Full suite: 70 passed, 1 skipped.
- [x] SNR persisted on the user recording's asset row — `worker/core.py` writes `user_asset.snr_db`, whether or not reduction ran. Asserted end-to-end in `test_snr_is_persisted_on_the_user_recording_asset` (the column is written nowhere else, so the test fails if the worker drops it).
- [x] A deliberately noisy recording scores without a hard failure — `test_noisy_recording_scores_without_a_hard_failure` (ambient lead-in → reduction runs), `test_noisy_take_that_starts_mid_speech_still_scores` (gated branch), and `test_reduction_failure_falls_open_and_still_scores` (broken noisereduce still scores).

## Notes

- **Spec deviation, owner-approved:** spectral reduction is gated on `MIN_PROFILE_SNR_DB = 6.0` instead of running unconditionally. Applying it literally is unsafe when the user starts speaking immediately — the "first 300ms noise profile" is then their own voice, and subtracting it stripped 82% of clip energy, dropping the identical-clip lifecycle score from ~100 to 89.8 (energy axis 67.4) and breaking the regression net. Measured separation is clean: ~0.17 dB starting mid-speech vs 11–27 dB with a genuine ambient lead-in. The bandpass stays unconditional. Threshold is a **placeholder pending graduation on real noisy recordings** — it was set from synthetic takes.
- **Synthetic audio cannot validate quality here.** On tone+white-noise, bandpass-only outscores full reduction at every noise level, because spectral gating is tuned for speech. So the tests establish only what the ticket asked — no hard failure — never that denoising *improves* scores.
- The STT content gate still sees the **raw** clip (ASR is trained on natural audio; routing it through the cleaned signal would mean materializing a temp WAV). Flagged, not changed.
- 🧑 **HUMAN:** the real-audio pass — record a genuinely noisy take (fan/street noise) and confirm the cleanup helps rather than hurts, then graduate `MIN_PROFILE_SNR_DB`. Not verifiable synthetically.
- 🧑 **Pre-existing doc drift, not fixed here:** `master_implementation_plan.md` §Conventions states the backend venv is "Python 3.14" and mandates cp314 wheels, but the venv is Python 3.12.4. This predates the ticket; left alone rather than silently rewritten.
- `noisereduce` pulls matplotlib/pillow/fonttools (~50 MB) transitively for a spectral-gating call that never plots — worth revisiting if image size matters in Phase 3.
