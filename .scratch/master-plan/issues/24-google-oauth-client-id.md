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

**Note for deployment:** the client ID's origin list is per-environment. Whatever host the
frontend ends up on (ticket 15 / phase3-deploy) has to be added here too, or sign-in breaks in
production while working fine locally.
