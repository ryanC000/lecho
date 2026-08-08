# 25 — Get `npm run lint` to green so it can gate

**What to build:** `npm run lint` exits non-zero on a clean tree (27 errors, 3 warnings), which means it gates nothing and a genuinely new error is invisible — proving a change added none currently takes a `git stash -u` baseline diff by hand. Clear the backlog so the script can be trusted, and so CI can eventually run it. The errors are almost all mechanical: 14 unused `React` imports (React 19's JSX transform makes the default import unnecessary — the named hook imports stay), 5 `'global' is not defined` in test files (the eslint config needs the vitest/node globals rather than per-file disables), 5 unused `err` catch bindings (optional catch binding, `catch { }`), and two dead locals (`id` in `Practice.jsx`, `extent` in `PitchChart.jsx`). One error is not mechanical and deserves a real look: `AuthModal.jsx:18` calls setState synchronously inside an effect, which the React Compiler flags as cascading-render risk.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `npm run lint` exits 0 on a clean tree
- [ ] The `AuthModal` setState-in-effect finding is actually fixed, not suppressed with a disable comment
- [ ] `npm test` and `npm run build` still green afterwards
- [ ] No behaviour change — this is deletions and eslint config only, apart from the AuthModal fix

## Notes

- The three remaining `react-hooks/exhaustive-deps` warnings (`WavesurferKaraoke` `onReady`, `PitchChart` `words`, one stale disable directive) are warnings, not errors. Fix them only if trivial; don't restructure hooks to chase them.
- Deliberately **not** in scope: the backend's 83 pytest deprecation warnings (Pydantic v1-style `class Config`, `datetime.utcnow()`, `declarative_base()`). Same character of debt, different suite — worth its own ticket if the warning noise ever hides a real one. Note that `class Config: orm_mode = True` is a silent no-op under Pydantic v2, so those blocks are misleading as well as noisy.
