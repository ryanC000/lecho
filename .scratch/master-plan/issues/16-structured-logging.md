# 16 — Structured logging

**What to build:** The job pipeline becomes observable from the console: standard-library logging with a consistent `job=` prefix covering job creation (job, practice, mode, duration), every status transition, every failure with its reason, DSP wall-clock timings (extract/align/score), upload validation rejections, and bleed detections. JSON log formatting is explicitly deferred to Phase 3.

**Blocked by:** None — can start immediately. (Bleed-detection log point activates when ticket 08 lands.)

**Status:** ready-for-agent

- [ ] A full job run reads as a coherent story in the console with a grep-able `job=` prefix
- [ ] Failures log the reason before the status flips
- [ ] DSP stage timings visible per job
- [ ] No new logging dependency
