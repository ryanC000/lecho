# 08 — Worker bleed gate for shadow takes

**What to build:** A bled take must never be scored. For shadow jobs, before any feature extraction, the worker cross-correlates the raw native and user signals (normalized cross-correlation via FFT, lags 0–1.5s, per-lag normalization by overlapping-window norms); a peak above the bleed threshold (placeholder 0.5, graduates later) hard-fails the job as retryable with the message: "It sounds like the native audio was picked up by your microphone. Please use headphones for shadow takes, or switch to Solo mode." Rationale: a learner *imitating* correlates weakly in the waveform domain; playback leakage correlates strongly. Numpy only — scipy is not a dependency at this point.

**Blocked by:** 07 (mode field exists so the worker knows the take is shadow).

**Status:** done (commit `7b3acf2`, 2026-07-12)

- [x] Unit test: native mixed into noise at −10dB ⇒ bleed detected (leaked native over 10dB-down room noise: NCC 0.95)
- [x] Unit test: independent synthetic speech-like signal ⇒ not detected (NCC 0.003; same-register imitation measured at 0.23, still well under 0.5)
- [x] Shadow job with bleed → FAILED, retryable, exact headphones message; solo jobs never run the check (the solo lifecycle test submits the native bytes themselves and still scores SUCCESS)
- [x] Detection runs on raw arrays before feature extraction; threshold and max-lag are named constants
