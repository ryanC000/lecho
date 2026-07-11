# ADR 0001 — dsp-2 baseline frozen with trim-time re-normalization and median-slope tempo

**Date:** 2026-07-11
**Status:** accepted

## Context

Task 0.1 (reconcile `test_dsp2.py`) exposed two scoring defects in dsp-2:

1. `f0_semitone`/`rms_z` were normalized over the *untrimmed* clip, so lead-in/lead-out
   dead air skewed the mean/std — an identical delivery with 0.8s of silence scored ~61
   on energy.
2. The timing axis normalized local slope by the length ratio `len_u/len_n`, so the
   near-silent edge frames that energy trimming always leaves imposed a constant
   spurious deviation across the whole clip.

## Decision

Fix both in `dsp.py` (re-normalize inside `trim_silence`; estimate tempo as the median
raw slope with a length-ratio fallback for degenerate paths) and freeze the result,
commit `338eb58`, as **the dsp-2 baseline** that Stage 1 calibration tunes against.

## Consequences

- Energy and timing scores shift for real clips versus the previous behavior; no
  production scores existed to invalidate.
- Further scoring-quality judgments are deferred to the calibration harness (Task 1.1)
  on real audio — the baseline is falsified there, not by further synthetic reasoning.
- `test_dsp2.py` pins the fix (`energy_score >= 70` on the shadow-lag test); relaxing
  that assertion instead of fixing a regression is out of bounds.
