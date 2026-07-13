# 17 — Ambient-noise pipeline

**What to build:** User recordings get cleaned before scoring: a bandpass (80–4000 Hz Butterworth) plus spectral noise reduction using the first 300ms as the noise profile, and an SNR estimate persisted to the recording's asset row (the column exists, never populated). Applied to the user clip only, and only from the worker orchestrator — the pure DSP pipeline and its deterministic tests stay untouched, because denoising changes RMS contours.

**Precondition:** scipy and noisereduce must install as prebuilt cp314 wheels (`--only-binary :all:`). If they don't, set this ticket's Status to `needs-info`, record the blocker in the master plan's Decision log, and stop — the no-speech graceful failure already covers the UX.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Wheel pre-check performed and outcome recorded before any requirements change
- [ ] Denoise applied only in the orchestrator; dsp test suite untouched and green
- [ ] SNR persisted on the user recording's asset row
- [ ] A deliberately noisy recording scores without a hard failure
