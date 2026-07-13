# 18 — Job history page + UI cleanup

**What to build:** Users can revisit past attempts: a paginated, owner-scoped job list endpoint (newest first: id, practice, title, status, score, mode, created time, total count) and a history page routed from the navbar (replacing the dead Settings link), each row linking to its results page — which already renders any status. Cleanup rides along: drop the register form's name field (no backing column), remove the dead "Forgot password?" button, and add a spacebar record toggle with the matching ARIA keyboard-shortcut annotation.

**Blocked by:** None — can start immediately. (`mode` in the payload is null-tolerant until ticket 07 lands.)

**Status:** ready-for-agent

- [ ] History lists only the caller's jobs, newest first, with pagination
- [ ] Every row navigates to a working results view regardless of status
- [ ] Navbar shows History; dead Settings link and dead auth UI removed
- [ ] Spacebar toggles recording when the recorder is visible, with `aria-keyshortcuts`
