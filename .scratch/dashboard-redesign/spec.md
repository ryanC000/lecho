# Dashboard redesign

Source: external design handoff (`design_handoff_dashboard_redesign`, synced
2026-08-12) — two-column dashboard replacing the single-column `Bienvenue` /
level-pills / practice-grid page. Full spec (colors, spacing, copy, SVG paths)
lived in that bundle's `README.md`; the essentials are captured here since the
bundle itself isn't checked into the repo.

**Landed in this pass (frontend-only):**
- Two-column layout (`frontend/src/pages/Dashboard.jsx`): left rail (last
  take + accuracy ring, stat notes, performance breakdown), right column
  (pencil-circled level filter, "Continue shadowing" clip grid, minutes/recent-takes
  row, new-clips banner).
- New shared primitives: `SketchPanel` (`components/core/SketchPanel.jsx`),
  `LevelFilterInk` (`components/LevelFilterInk.jsx`).
- Global nav restyle (`App.jsx` header): serif links, no pill background,
  underline active state — this changes every page's header, not just the
  dashboard's.
- New `--color-ink-mid` (#6B5C4A) and `--shadow-sticker` tokens in `index.css`.

**Landed since:**
- "minutes this week" bar chart and the "min shadowed" stat note are live off
  `JobListItem.duration_seconds` (master-plan ticket 26, done 2026-08-14) —
  placeholders removed.

**Deferred — no data source exists yet:**
- Per-clip progress and the clips-open/clips-mastered counters are computed
  client-side from `GET /jobs?limit=100` (newest-first, reduced to latest
  score per practice) rather than a real aggregate endpoint — fine at today's
  volume, but won't scale indefinitely. Worth a backend summary endpoint if
  job history grows large; not filed as a ticket since it isn't broken yet.
- Mastery threshold for "clips mastered": score ≥ 70 (owner decision,
  2026-08-13) — independent of the existing ≥75/≥50/else color-band
  thresholds used elsewhere (`AccuracyRing`).
- The "new clips added" banner has no real trigger condition in the data
  model (no "added this week" signal on `Practice`). Shipped as a static,
  always-shown banner with generic copy rather than the mock's fabricated
  "14 new C1 clips" line.

## Comments
- 2026-08-13 — owner chose frontend-only with placeholders + a follow-up
  ticket over adding a backend aggregation endpoint now.
- 2026-08-13 — owner had the duration-tracking ticket promoted to
  `.scratch/master-plan/issues/26-expose-take-duration.md` (main backlog)
  rather than left as a feature-local ticket; `issues/01` here now just
  points to it.
