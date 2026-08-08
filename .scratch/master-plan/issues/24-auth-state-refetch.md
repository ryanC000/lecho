# 24 — Token-gated pages recover when auth state changes

**What to build:** A 401 on a token-gated page is currently a dead end. `History` and `Results` both catch the 401, render "Please log in…", and never try again — so a visitor who logs in through the navbar modal keeps staring at the login prompt until they reload by hand. The plumbing already exists: `utils/auth` dispatches `lecho-auth-changed` on login and logout, and `App.jsx` already listens to it to swap the navbar buttons. Make both pages subscribe too: on an auth change, clear the error and re-run their fetch. Logging out while on either page should drop back to the login prompt rather than leaving the previous user's data on screen.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Logging in from the modal while sitting on `/history` loads the history in place, no reload
- [ ] Same on `/results/:jobId` — the poll restarts rather than staying on the error
- [ ] Logging out on either page returns to the login prompt instead of stale data
- [ ] Both behaviours covered by vitest

## Notes

- Found while building ticket 18: `History.jsx` reproduced the pattern already in `Results.jsx:35`, so fixing them together is the point of the ticket — don't fix only one.
- The shared shape is "authenticated fetch that re-runs on `lecho-auth-changed`". If it wants to be a small hook, fine; if two `useEffect` subscriptions read clearer, that's fine too — this is two pages, not a framework.
