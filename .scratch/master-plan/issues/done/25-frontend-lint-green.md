# 25 — Get `npm run lint` to green so it can gate

**What to build:** `npm run lint` exits non-zero on a clean tree (27 errors, 3 warnings), which means it gates nothing and a genuinely new error is invisible — proving a change added none currently takes a `git stash -u` baseline diff by hand. Clear the backlog so the script can be trusted, and so CI can eventually run it. The errors are almost all mechanical: 14 unused `React` imports (React 19's JSX transform makes the default import unnecessary — the named hook imports stay), 5 `'global' is not defined` in test files (the eslint config needs the vitest/node globals rather than per-file disables), 5 unused `err` catch bindings (optional catch binding, `catch { }`), and two dead locals (`id` in `Practice.jsx`, `extent` in `PitchChart.jsx`). One error is not mechanical and deserves a real look: `AuthModal.jsx:18` calls setState synchronously inside an effect, which the React Compiler flags as cascading-render risk.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] `npm run lint` exits 0 on a clean tree
- [x] The `AuthModal` setState-in-effect finding is actually fixed, not suppressed with a disable comment
- [x] `npm test` and `npm run build` still green afterwards
- [x] No behaviour change — this is deletions and eslint config only

Done 2026-08-14. Cleared all 27 errors: 15 unused `React` default imports (`App.jsx`
and `SketchButton.jsx` keep theirs — they call `React.useState`), 5 `catch (err)` →
`catch {}` in `useRecorder.js`, the dead `extent()` in `PitchChart.jsx`, and the dead
`id` in `Practice.jsx` (which orphaned `useParams` from its import). The 5 `'global'
is not defined` errors are fixed in `eslint.config.js` with a second config block
adding `globals.node` for `**/*.test.{js,jsx}` and `src/test/**` rather than per-file
disables. Also removed the stale `exhaustive-deps` disable in `useRecorder.js`
(trivial, and it was one of the 3 warnings). Two `exhaustive-deps` warnings remain by
design — they'd need hook restructuring. Lint now exits 0; `npm test` 48/48 and
`npm run build` green.

The `AuthModal` setState-in-effect needed no work: it was the field-reset effect at
line 18 as of `e18f99b`, and `682ab67` already removed it properly — `App.jsx:96`
keys the modal on `open`+`mode` so a remount gives a fresh form. No disable comment
was involved. That line 18 now holds unrelated code is why the finding no longer
appears in lint output.

## Notes

- The three remaining `react-hooks/exhaustive-deps` warnings (`WavesurferKaraoke` `onReady`, `PitchChart` `words`, one stale disable directive) are warnings, not errors. Fix them only if trivial; don't restructure hooks to chase them.
- Deliberately **not** in scope: the backend's 83 pytest deprecation warnings (Pydantic v1-style `class Config`, `datetime.utcnow()`, `declarative_base()`). Same character of debt, different suite — worth its own ticket if the warning noise ever hides a real one. Note that `class Config: orm_mode = True` is a silent no-op under Pydantic v2, so those blocks are misleading as well as noisy.
