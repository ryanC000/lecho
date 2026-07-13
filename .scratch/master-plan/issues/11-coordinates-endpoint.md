# 11 — Coordinates endpoint for the pitch visualizer

**What to build:** An authenticated, owner-scoped endpoint that returns a successful job's coordinate archive verbatim (404 for another user's job, matching the job-status route; 409 while the job isn't SUCCESS). The archive shape is already produced by the worker and is a fixed contract — `times`, native/user F0 in Hz, native/user semitone tracks, native/user RMS, and per-track voiced masks, all arrays equal in length (≲1500 points). Do not change the keys.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Owner of a SUCCESS job receives equal-length arrays under the contract keys
- [ ] Non-owner gets 404; non-SUCCESS job gets 409
- [ ] Payload is the stored archive verbatim — no recomputation
