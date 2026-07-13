# 05 — One API-client seam on the frontend

**What to build:** All HTTP calls cross one api-client interface: request, error unwrap (parse `.detail`, throw with status), and token attach live in a single module. The three router loaders stop bypassing the seam with raw unhandled `fetch`; register/login reuse the shared unwrap instead of their private copies (three copies → one). A failed loader surfaces an error like every other call instead of silently `.json()`-ing a non-OK response. No behaviour change beyond loaders gaining error handling.

**Blocked by:** None — can start immediately (frontend only, parallel to 01–04).

**Status:** done

- [ ] Loaders, register, login, and authenticated calls all go through the one interface
- [ ] Exactly one implementation of the error-unwrap logic remains
- [ ] `npm run build` green; app loads practices, login and job submission still work
- [ ] Behaviour otherwise unchanged (same endpoints, same token handling)

## Comments
Done 2026-07-11 in 9fa0f69 (subagent). request() core + apiGet for loaders; one unwrap copy remains; build green. Known micro-difference: register/login fallback error text is now statusText instead of hardcoded strings (backend always sends .detail).
