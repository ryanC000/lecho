# 13 — Logout with server-side token revocation

**What to build:** Logging out actually kills the token. A logout endpoint decodes the presented token and inserts its `jti` into the revoked-token table (which the per-request check already consults), returning 204. The frontend navbar logout calls it best-effort and clears the stored token even if the call fails. At startup, expired revocation rows are deleted so the table can't grow unbounded.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] Token works → logout → the same token gets 401 on any authenticated route
- [x] Frontend clears its token even when the endpoint is unreachable
- [x] Startup housekeeping removes only expired revocation rows

Done 2026-08-14. `POST /auth/logout` depends on `get_current_user` as well as the
raw token, so invalid and already-revoked tokens are turned away before the
insert — a second logout with the same token returns 401 and the unique `jti`
index can't collide. `security.revoke_token` stores `expires_at` from the JWT's
own `exp` (past that the token fails signature checking anyway, making the row
dead weight); `security.purge_expired_revocations` deletes those rows and runs
in the app lifespan after migrations. Frontend `logout()` in `api/auth.js`
swallows any error from the call and always `clearToken()`s. Tests: 3 backend
(`test_api.py`), 2 frontend (`src/api/auth.test.jsx`).
