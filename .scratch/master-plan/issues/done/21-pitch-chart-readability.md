# 21 — Pitch chart readability: continuous contour + target band

**What to build:** Repair the Results pitch overlay so it reads as a melodic
line and teaches range. The backend semitone tracks are already gap-interpolated;
the frontend fragments them. Draw each contour continuously from the interpolated
track, breaking only at genuine inter-word pauses (word-aware when the alignment
is present, time-threshold fallback otherwise). De-spike/de-jitter drawn geometry
with a median-3 pass (not 5 — preserves real 2-frame peaks) and use a robust
percentile y-domain, replacing the octave-exclusion that punches holes. Keep
deviation coloring computed from the RAW tracks so it stays in sync with the
backend's segment flags. Add a shaded native ± DEVIATION_SEMITONES "target band"
behind the lines, plus an "In range" legend entry. No new chart dependency; keep
the hand-rolled SVG. Coordinates archive contract unchanged.

**Blocked by:** None (12 shipped the chart; this supersedes its blank-at-unvoiced
rule).

- [x] Contour draws continuously through unvoiced consonants; breaks only at real pauses
- [x] median-3 smoothing on drawn geometry; warn/deviation still from raw tracks
- [x] Octave spikes no longer punch holes; robust percentile y-domain
- [x] Target band renders behind the lines; "In range" in the legend
- [x] Word-aware bridging: within-word gap bridged, inter-word pause broken (test)
- [x] Target-band render test; existing continuity + warn tests still green

---

**Status: done** — commit `f6cba6d` (2026-07-21)

The first pass (d2ae770) implemented the ticket text but the chart still read as
fragmented and spiky with an invisible band. Diagnosed against the real archives
in `backend/storage/analysis/`:

- **Fragmented** — geometry was gated on the voiced mask and bridged gaps with
  straight chords; native unvoiced runs (up to 29 frames / 290 ms) exceeded the
  200 ms fallback and broke the line mid-utterance even though `native_semitone`
  is interpolated everywhere. Fix: draw *through* the interpolated track, break
  only at genuine pauses. Word-aware path now yields one continuous contour.
- **Spiky** — the user track carries multi-frame ±12/±24 st harmonic-locking
  errors (adjacent-frame jumps up to 22 st) that median-3 can't remove. Added an
  octave-unwrap pass before median-3 (jumps drop to ≤5.5 st).
- **Band invisible** — `opacity 0.1 → 0.18`, and it's now continuous behind the
  line.
- Follow-up from `/code-review`: octave-unwrap folded a spike flat inside the
  band while the raw-based warn still coloured it "off pitch" (12 frames / 10
  clips). Octave-reduced the raw deviation used for colouring so an octave-class
  gap isn't painted warm — cuts the residual to 7 frames, the inherent
  smoothed-geometry-vs-raw-colouring tolerance the ticket's "warn from raw"
  requirement accepts.

Verified by `frontend` vitest (19 green, incl. new continuity / octave-fold /
warn-coherence / re-anchor tests) and by simulating the draw logic over all 10
real archives. Final on-screen appearance is a human check (not screenshotted).
