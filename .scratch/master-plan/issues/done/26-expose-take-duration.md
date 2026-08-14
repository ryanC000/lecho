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

**Status:** done

- [x] `GET /jobs` (or a new endpoint) exposes enough to compute minutes
      practiced per day for the trailing 7 days
- [x] Enough to compute total shadow-mode minutes practiced (for "min
      shadowed")
- [x] `frontend/src/pages/Dashboard.jsx`'s `week-placeholder` and the
      "min shadowed" stat note are wired to real data, placeholders removed
- [x] `npm test` and `npm run build` still green afterwards; backend tests
      cover the new field/endpoint

Done 2026-08-14. Chose the field on `JobListItem` over a `/me/practice-summary`
endpoint: the dashboard already fetches `GET /jobs?limit=100` for per-clip
progress, so both figures come off that one request with no new endpoint.
`list_jobs` adds one grouped `AudioAsset` lookup for the page's job ids
(nullable — a take rejected by a gate is persisted FAILED but its asset never
is). No migration: `duration_seconds` already existed on `audio_assets`.
Frontend derives the 7-day series and the all-time shadow total in
`Dashboard.jsx`; `useJobHistory` now also keeps the unfiltered `takes`, since
minutes practiced counts a take whether or not it scored. Tests: 3 backend
(`test_api.py`), 6 frontend (`Dashboard.test.jsx`). Revisit if `RECENT_JOBS_LIMIT`
(100) ever truncates a real week — that's the trigger for the summary endpoint.

## Notes
- Per `.scratch/dashboard-redesign/spec.md`: per-clip progress and the
  clips-open/mastered counters are already computed client-side from
  `GET /jobs?limit=100` and are out of scope here — only duration is missing.
- `AudioAsset.duration_seconds` is authoritative (server-derived at ingest,
  not the client-reported one) — join on `AudioAsset.job_id` filtered to
  `role == "USER_RECORDING"`.
