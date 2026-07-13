# 15 — Environment/config consolidation

**What to build:** All deploy-varying values move to environment variables with documented examples on both sides: backend JWT secret (dev default stays but logs a loud warning when unset), CORS origins (comma-separated, defaulting to the Vite dev origin), Google client ID; frontend API base URL and Google client ID. Backend reads plain env vars (no dotenv dependency — the uvicorn `--env-file` flag is the documented mechanism). The frontend API base falls back to localhost for dev.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Both env example files exist and every variable is commented
- [ ] Backend boots with zero env vars set (dev defaults) and logs the JWT-secret warning
- [ ] CORS origins configurable without code changes
- [ ] Frontend respects the API base env var in a production build
