# 18 — Job history page + UI cleanup

**What to build:** Users can revisit past attempts: a paginated, owner-scoped job list endpoint (newest first: id, practice, title, status, score, mode, created time, total count) and a history page routed from the navbar (replacing the dead Settings link), each row linking to its results page — which already renders any status. Cleanup rides along: drop the register form's name field (no backing column), remove the dead "Forgot password?" button, and add a spacebar record toggle with the matching ARIA keyboard-shortcut annotation.

**Blocked by:** None — can start immediately. (`mode` in the payload is null-tolerant until ticket 07 lands.)

**Status:** done (commit `e18f99b`, 2026-08-08)

- [x] History lists only the caller's jobs, newest first, with pagination *(`GET /jobs?limit&offset` → `{jobs, total}`; owner-scoping, ordering, paging and the 401 covered in `test_api.py`. `id` breaks `created_at` ties so pages can't repeat or skip same-second takes.)*
- [x] Every row navigates to a working results view regardless of status *(rows are `Link`s to `/results/{id}`; History.test.jsx asserts a FAILED, score-less job still gets a row and Results already renders any status)*
- [x] Navbar shows History; dead Settings link and dead auth UI removed *(`/history` route replaces `to="#"`; register `name` field and "Forgot password?" button gone, along with the now-orphaned `.auth-forgot` rule)*
- [x] Spacebar toggles recording when the recorder is visible, with `aria-keyshortcuts` *(Recorder.test.jsx covers the toggle, the annotation, and the ignore-while-typing guard)*

## Notes

- `mode` never actually arrives null: `migrations.py` backfills legacy rows with `NOT NULL DEFAULT 'solo'`, so the payload declares `mode: str = "solo"` like `JobStatusResponse` rather than an optional.
- `created_at` is UTC-tagged in the serializer — SQLite returns it naive, and an offset-less ISO string is parsed as *local* time by the browser, which showed every row hours off.
- Not fixed (pre-existing pattern, out of scope): logging in from the modal while sitting on `/history` leaves the "Please log in" message until a reload. `Results.jsx` behaves the same way; a shared `lecho-auth-changed` refetch would fix both together.
