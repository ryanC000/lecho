# 09 — Frontend shadow capture

**What to build:** The full shadow experience: a mode toggle on the practice page (Shadow default, Solo fallback, persisted per session). Before the first shadow take of a session, a headphones confirmation modal ("Shadowing plays the native clip while you record — use headphones so your mic only hears you"), remembered for the session. A shadow take decodes the native clip into an AudioBuffer, starts playback and recording back-to-back on the same audio-context clock, auto-stops at native duration + 1.0s, and uploads through the existing WAV path with the mode attached. The client duration gate mirrors the per-mode server numbers. Solo mode is untouched. Never route mic input to the audio output (feedback loop).

**Blocked by:** 08 (server accepts shadow jobs and bleed-rejects bad ones — the UX depends on that rejection round-trip).

**Status:** done (commit `74b8dd8` + button-color follow-up `8dd7e17`, 2026-07-12) — the two real-audio checks below still need a human pass (mic + speakers)

- [ ] Headphones shadow take end-to-end: modal → synced playback+record → auto-stop → upload → score *(modal flow, synced start, per-mode gate, and mode-tagged upload are vitest-covered; the real-audio pass needs the owner)*
- [ ] Laptop-speaker take surfaces the worker's bleed rejection with the retryable message on Results *(the rejection round-trip is API-tested end-to-end in `test_api.py`; Results already renders `error_message` + retryable for FAILED jobs — needs the owner's real-speaker confirmation)*
- [x] Mode toggle persists across pages within a session (sessionStorage); solo path byte-identical to today
- [x] MediaRecorder start latency is not compensated for (silence-trim + DTW absorb it)
