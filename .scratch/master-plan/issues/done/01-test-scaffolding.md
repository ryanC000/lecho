# 01 — Test scaffolding: backend lifecycle + frontend vitest

**What to build:** A regression net proving the whole core loop works without a human: a backend test that registers a user, logs in, ingests a synthetic sine "native" clip for a practice, submits a solo job with the same audio, watches the worker run inline, and reads back a near-100 score with per-axis sub-scores — plus per-mode gate rejections and logout revocation. On the frontend, a vitest setup where the Recorder, Results polling (score + segments + words), and PitchChart render correctly against mocked APIs.

**Blocked by:** None — can start immediately. (Work this first: every later ticket lands on this net. The coordinates-shape and logout assertions activate once tickets 11 and 13 exist — write them alongside those tickets if this one lands earlier.)

**Status:** done

- [x] Backend lifecycle test runs against a temp DB and temp storage root, never the dev `lecho.db`
- [x] Register → login → solo job on synthetic audio → SUCCESS with score ≈ 100 and non-null pitch/timing/energy sub-scores
- [x] Solo ±20% gate rejection asserted (shadow-length gate deferred — see Comments)
- [x] `npm test` runs vitest green: Recorder duration-gate error, Results PENDING→SUCCESS polling render
- [x] Full backend suite (`pytest -q`) and frontend suite both green in one run

Done 2026-07-11. backend/test_api.py (8 tests: lifecycle scoring >=95 with sub-scores, solo relative gate, absolute gate on real bytes, unreadable audio, auth required, ownership 404, duplicate register, wrong password) + vitest setup (Recorder x4, Results x3). Deferred until their features exist, extending the Blocked-by note: shadow-length gate (ticket 07), segment words assertion (06), PitchChart.test.jsx (12) — add them here when those land, alongside coordinates (11) and logout (13). Deviation: "test" script is "vitest run" (deterministic) with "test:watch" for watch mode. Code-review: no hard findings; extra auth/failure-path tests kept as regression-net thickening.
