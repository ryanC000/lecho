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

- [ ] Contour draws continuously through unvoiced consonants; breaks only at real pauses
- [ ] median-3 smoothing on drawn geometry; warn/deviation still from raw tracks
- [ ] Octave spikes no longer punch holes; robust percentile y-domain
- [ ] Target band renders behind the lines; "In range" in the legend
- [ ] Word-aware bridging: within-word gap bridged, inter-word pause broken (test)
- [ ] Target-band render test; existing continuity + warn tests still green
