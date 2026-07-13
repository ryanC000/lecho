# 14 — Google OAuth (self-hosted GIS ID-token flow)

**What to build:** Real "Sign in with Google" replacing the mock button. The frontend loads the Google Identity Services script, renders the official button, and posts the returned ID-token credential to a new auth endpoint. The backend verifies it with the pure-Python `google-auth` library (pre-check the wheel installs binary-only first) against the configured client ID, requires a verified email, finds-or-creates the user, and returns the app's own JWT — same token schema, no Firebase, no redirect flow. Password hash becomes nullable with an `auth_provider` column; password login must 401 cleanly on a null hash *before* any hash verification. 🧑 Embedded human step: create the OAuth client ID in the Google Cloud console and register the dev origin — documented in the env examples.

**Blocked by:** None — can start immediately (the human console step gates only live verification, not the code).

**Status:** ready-for-agent

- [ ] Google sign-in end-to-end: button → credential → app JWT → authenticated requests work
- [ ] Unverified-email credentials rejected
- [ ] Google-created user attempting password login gets a clean 401, no server error
- [ ] Existing password users unaffected; migration adds the provider column idempotently
