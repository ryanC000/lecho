# 26 — Store and expose per-take audio duration for dashboard metrics

**What to build:** The redesigned dashboard (`frontend/src/pages/Dashboard.jsx`,
see `.scratch/dashboard-redesign/spec.md`) has a "minutes this week" bar chart
and a "min shadowed" stat note, both currently rendered as placeholders
because no endpoint exposes how long a take's audio was. `AudioAsset.duration_seconds`
(`backend/infra/models.py`) already has this for the `USER_RECORDING` asset on
each job, but it's never joined or serialized — `job_list_item` /
`job_status_payload` (`backend/api/serializers.py`) don't include it, and
`GET /jobs` doesn't compute anything from it.

Needed: expose a per-job duration (join `ProsodyJob` → its `USER_RECORDING`
`AudioAsset`) through `GET /jobs`, so the frontend can sum minutes practiced
per day for the last 7 days and per mode (`shadow` for "min shadowed").
Whether that's a new field on `JobListItem` or a small dedicated summary
endpoint (e.g. `GET /me/practice-summary` returning the 7-day series + the
shadowed-minutes total in one query) is an implementation choice — a
dedicated endpoint avoids the frontend re-deriving a weekly series from a
flat job list on every dashboard load.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `GET /jobs` (or a new endpoint) exposes enough to compute minutes
      practiced per day for the trailing 7 days
- [ ] Enough to compute total shadow-mode minutes practiced (for "min
      shadowed")
- [ ] `frontend/src/pages/Dashboard.jsx`'s `week-placeholder` and the
      "min shadowed" stat note are wired to real data, placeholders removed
- [ ] `npm test` and `npm run build` still green afterwards; backend tests
      cover the new field/endpoint

## Notes
- Per `.scratch/dashboard-redesign/spec.md`: per-clip progress and the
  clips-open/mastered counters are already computed client-side from
  `GET /jobs?limit=100` and are out of scope here — only duration is missing.
- `AudioAsset.duration_seconds` is authoritative (server-derived at ingest,
  not the client-reported one) — join on `AudioAsset.job_id` filtered to
  `role == "USER_RECORDING"`.
