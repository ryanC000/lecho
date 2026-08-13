# 24 — 🧑 Create the Google OAuth client ID and verify sign-in live

**What to build:** The console half of ticket 14. The code is merged and test-covered, but no
OAuth client ID exists, so the button is hidden and `POST /auth/google` returns 503. The owner
configures the OAuth consent screen, creates a Web-application client ID, registers
`http://localhost:5173` as an authorised JavaScript origin (no redirect URI — the app uses the
ID-token flow), and pastes the same ID into `backend/.env` and `frontend/.env`. Then the one
acceptance criterion ticket 14 could not verify — a real Google account reaching a real app JWT —
gets checked by hand. Full step-by-step lives in `backend/.env.example`.

**Blocked by:** None — 14 landed the code; this is console work only.

**Status:** ready-for-human

- [ ] OAuth consent screen configured (External audience; own account added as a test user)
- [ ] Web-application client ID created with `http://localhost:5173` as an authorised JS origin
- [ ] Same ID in `backend/.env` (`GOOGLE_CLIENT_ID`) and `frontend/.env` (`VITE_GOOGLE_CLIENT_ID`)
- [ ] Backend started with `--env-file .env`; button renders instead of being hidden
- [ ] Real Google account signs in, gets an app JWT, and can post a job — 14's first box ticks

- [ ] **`http://localhost` (no port) also registered** — the Kubernetes deployment serves the
      bundle through the Ingress on port 80, and Google treats that as a **different origin** from
      the Vite dev server's `http://localhost:5173`. Both must be listed or sign-in works in dev
      and 400s in the cluster.
- [ ] Same ID passed to the frontend image at build time —
      `docker build --build-arg VITE_GOOGLE_CLIENT_ID=... ./frontend`. Vite inlines it at build,
      so it cannot come from the k8s ConfigMap; the backend's copy does come from the Secret.

**Note for deployment:** the client ID's origin list is per-environment and per-port. Whatever host
the frontend ends up on has to be added here too, or sign-in breaks in production while working
fine locally. See `k8s/README.md` §5.
