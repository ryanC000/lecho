# 04 — Run calibration and graduate the constants

**What to build:** The dsp-2 placeholder constants become calibrated values. Run the harness on the recorded corpus, apply the recommended constants deliberately, confirm the graduation gates hold, re-run the whole test suite (updating synthetic-test thresholds only if constants shifted them), bump the algorithm version, and record the final values in the master plan's Decision log.

**Blocked by:** 02 (calibration harness — done), 03 (recorded corpus — done).

**Status:** done (2026-07-13, commit `9d15fbe`)

**First calibration run (2026-07-12):** no feasible constants exist for the current corpus — practice 7's monotone outscores its emulation on pitch (64.1 vs 50.8) at every pitch floor and every grid point, so the worst-case margin is negative regardless of tuning. Root cause is the clip, not the take (the emulation was recorded shadow-style, owner confirmed; bleed check clean, NCC ≤ 0.08 on all six takes): practice 7's native line is nearly flat — 2.1 st semitone std vs 3.8 for practice 2 — so a deliberate monotone genuinely resembles the reference; even shape-normalized (z-scored) pitch RMSE cannot separate its emulation (0.75) from its monotone (0.72). Practice 2 orders correctly in both raw and z-scored space. This also retroactively explains Phase 1R's low-effort > mid-effort inversion (same clip). Also observed: timing RMSE ~1.9 on all real takes. Pitch-floor sweep showed no octave/creak signal (learner median F0 stable ~110–120 Hz at floors 60/65/75).

**Resolution (2026-07-13):** the owner reframed the blocker — French content is typically flat-pitched, so the clip-swap unblock was replaced by the dsp-3 track (ADR 0003): timing-axis repair (`SLOPE_WINDOW_S` 0.15 → 0.30; the ~1.9 timing RMSE was a window-shorter-than-path-runs artifact), MFCC axis measured NO-GO (`--probe-mfcc`), per-entry bad take (flat natives gate on low_effort, not monotone), and honest gates (emulation ≥ 70 / margin ≥ 3 — the measured frontier caps the worst-case margin at ~4–5 points on this corpus). Graduated: λ = 1.0, `K_PITCH` = 8.0, `K_TIMING` = 4.0, `K_ENERGY` = 3.0, weights 20/60/20 (timing-led).

- [x] Harness table shows all entries passing both gates with the applied constants (emulation 73.1/70.1, margins 3.9/4.0)
- [x] Pitch-floor diagnostic outcome recorded in the Decision log (2026-07-12 entry; floor stays 75)
- [x] Full pytest suite green after constant changes (32 passed, graduation test de-xfail'd)
- [x] `ALGO_VERSION` bumped to `dsp-3`; new jobs carry it
- [x] Decision log lists every graduated constant with its value
