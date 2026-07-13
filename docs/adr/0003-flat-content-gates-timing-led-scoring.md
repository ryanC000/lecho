# ADR 0003 — Flat-content gates, timing-led scoring, MFCC no-go (dsp-3)

**Date:** 2026-07-13
**Status:** accepted

## Context

The first calibration run (2026-07-12) found practice 7's near-flat native
clip (≈2 st semitone std) cannot discriminate emulation from monotone: pitch
RMSE against a flat reference *rewards* flatness, so the monotone wins the
pitch axis at every grid point. The planned unblock was to swap the clip for
an expressive one. The owner then reframed the problem: the content is
French, a flat-intonation, syllable-timed language — near-flat native clips
are the *norm*, not a corpus defect. The scorer must discriminate imitation
quality when the pitch contour carries little signal.

Two further 2026-07-13 measurements shaped the decision:

- **Timing axis repaired** (see `SLOPE_WINDOW_S` in dsp.py): the old 0.15 s
  slope window was shorter than real-speech DTW path runs, clamping 8–10% of
  frames to slope 0.05 and inflating timing RMSE to ~1.9 on every take. At
  0.30 the axis discriminates: low_effort sits 0.4–0.95 log2-RMSE above
  emulation on both corpus entries. Rhythm is the discriminating axis for
  flat content.
- **Segmental (MFCC) axis is a no-go** (`calibrate.py --probe-mfcc`): 12
  CMVN'd MFCCs projected through the scorer's DTW path give a cross-speaker
  spectral floor of ~1.3–1.4 z-RMSE vs a take-level spread of ≤ 0.09 (p2's
  low_effort is *closer* than its emulation). All takes articulate the same
  words, so spectral distance cannot rank their quality. Criterion to
  revisit: integrate MFCC only if every bad-take gap vs emulation is ≥ 0.15
  on a future corpus.

## Decision

1. **Per-entry bad take.** An entry whose native clip has semitone std
   (voiced frames) ≥ `FLAT_NATIVE_ST_STD = 3.0` gates on **monotone**; below
   it, on **low_effort** — against a genuinely flat native, an articulate,
   rhythm-correct deliberate monotone *is* a faithful imitation and cannot be
   the discrimination target. Monotone remains a diagnostic row for flat
   entries. Flat entries must record a low_effort take.
2. **Honest gates.** The measured frontier on the single-voice corpus caps
   the worst-case margin at ~4–5 points at *any* constants (~3.3 if every
   emulation must reach 75). ADR 0002's 75/20 gates are unachievable by 4–6×.
   Gates now encode achieved reality: every emulation ≥ **70**, every margin
   vs the entry's bad take ≥ **3** (`GATE_MARGIN_MIN` and
   `GATE_MARGIN_FLAT_MIN`). The tuner maximizes worst-case margin *slack*
   (margin minus the entry's gate) so heterogeneous gates stay comparable.
3. **Timing-led weights.** Graduated constants (owner-approved, tuner
   recommendation on the full corpus): λ = 1.0, K = (8 st, 4.0, 3.0 z),
   weights **pitch 0.20 / timing 0.60 / energy 0.20**. Known risk: fitted to
   6 takes from one voice.
4. `ALGO_VERSION` = **dsp-3**.

## Consequences

- Absolute scores land in a narrow band (bad takes ~62–69, emulations
  ~70–73): the scorer ranks correctly but does not spread. Widening the
  spread needs a better corpus (e.g. a faithful *flat* emulation of practice
  7 — the current emulation take measures *more* expressive than its native,
  pitch RMSE 3.2 vs the low_effort take's 1.5 on jointly-voiced frames) or a
  second voice; gates tighten only when measurement says they can.
- Pitch demoted to 0.20 means expressive clips lean on a weaker pitch signal;
  the tuner still found practice 2's monotone margin (3.9) via pitch (60.2 vs
  74.5). An adaptive per-clip pitch weight was considered and deferred: one
  global vector passes both entries.
- `test_corpus_passes_graduation_gates` is de-xfail'd and now the standing
  definition of done for scoring changes.
