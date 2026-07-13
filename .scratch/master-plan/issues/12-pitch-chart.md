# 12 — Results-page pitch-overlay chart

**What to build:** The "insight consumption" step: on a successful job, Results renders a responsive hand-rolled SVG line chart (no new dependency) overlaying the native and user pitch contours against time. Lines go blank — never interpolate — wherever the respective voiced mask is false. User-line segments where the semitone gap ≥ 2.0 (the same constant that flags feedback segments) render in the warning color. Word labels on the x-axis come from the practice's alignment when it exists and degrade gracefully when it doesn't. For accessibility, a rendered text list summarizes each flagged region, reusing the segments data.

**Blocked by:** 11 (coordinates endpoint). Word labels improve with 06 but don't require it.

**Status:** ready-for-agent

- [ ] Chart renders on a real job: two contours, unvoiced gaps blank, deviations colored
- [ ] No new chart library added
- [ ] Alignment 404 → chart renders without word labels
- [ ] Screen-reader text list of flagged regions present
- [ ] Fixture-based render test once the vitest scaffolding (ticket 01) exists
