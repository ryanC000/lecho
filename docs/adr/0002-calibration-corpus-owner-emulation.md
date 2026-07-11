# ADR 0002 — Calibration corpus is owner-emulation takes, not native-vs-native

**Date:** 2026-07-11
**Status:** accepted

## Context

PRD 8.9 calibration originally gated on "native-vs-native ≥ 85" — a second native
rendition per practice. No second native speaker is available, and none is coming.
The product's premise is that learners *emulate* a specific native clip, so the
meaningful question is "does a sincere emulation score well and a monotone score
badly," not "do two natives agree."

## Decision

Per calibration entry, the owner records against the native reference:

- an **emulation take** — best-effort imitation, recorded *shadow-style*: listening to
  the native clip on headphones while speaking along (matches the app's default mode;
  headphones keep playback bleed out of the corpus);
- a **monotone take** — deliberate flat read of the same line;
- optionally (≥1 practice) a **low-effort take** — mumbled/careless, as a
  *diagnostic row only* (Phase 1R found a low-effort take once outscored a
  mid-effort one).

**Graduation gates:** emulation ≥ **75** overall; monotone at least **20 points
below** the emulation take. `--tune` maximizes the emulation–monotone margin
subject to the emulation gate. Leniency is a tuning *outcome constrained by
discrimination* — never a blanket softening, or the monotone rides up with it.

## Consequences

- Constants are calibrated to a single voice (the owner's). Accepted: the owner is
  also the primary user. Cross-speaker robustness is untested and out of scope.
- Manifest keys change: `rendition_b` → `emulation`; optional `low_effort`.
- Diagnostic rows (low-effort, `PITCH_FLOOR_HZ` sweep) inform the Decision log but
  never constrain the tuner.
