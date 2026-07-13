# 13 — Logout with server-side token revocation

**What to build:** Logging out actually kills the token. A logout endpoint decodes the presented token and inserts its `jti` into the revoked-token table (which the per-request check already consults), returning 204. The frontend navbar logout calls it best-effort and clears the stored token even if the call fails. At startup, expired revocation rows are deleted so the table can't grow unbounded.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Token works → logout → the same token gets 401 on any authenticated route
- [ ] Frontend clears its token even when the endpoint is unreachable
- [ ] Startup housekeeping removes only expired revocation rows
