# 15 — Environment/config consolidation

**What to build:** All deploy-varying values move to environment variables with documented examples on both sides: backend JWT secret (dev default stays but logs a loud warning when unset), CORS origins (comma-separated, defaulting to the Vite dev origin), Google client ID; frontend API base URL and Google client ID. Backend reads plain env vars (no dotenv dependency — the uvicorn `--env-file` flag is the documented mechanism). The frontend API base falls back to localhost for dev.

**Blocked by:** None — can start immediately.

**Status:** done — `be990fb`, 2026-08-08

- [x] Both env example files exist and every variable is commented — `backend/.env.example`
  covers all seven vars the backend reads; `frontend/.env.example` covers `VITE_API_BASE`.
- [x] Backend boots with zero env vars set (dev defaults) and logs the JWT-secret warning —
  booted with a clean environment; warning printed, CORS defaulted to the Vite origin.
  Known wart: `SECRET_KEY = jwt_secret()` runs at import, before the lifespan calls
  `logs.configure()`, so that one line prints unformatted via `logging.lastResort`.
- [x] CORS origins configurable without code changes — `cors_origins()` reads `CORS_ORIGINS`;
  covered by `backend/tests/test_config.py`.
- [x] Frontend respects the API base env var in a production build — `VITE_API_BASE=https://api.lecho.example
  npx vite build` baked that origin into the bundle, with no `localhost:8000` left in it.

**Deferred:** `GOOGLE_CLIENT_ID` / `VITE_GOOGLE_CLIENT_ID` are documented in both example
files but read by no code — Google sign-in is ticket 14, which owns the plumbing.
