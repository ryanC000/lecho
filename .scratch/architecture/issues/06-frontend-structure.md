# 06 — Frontend structure: name the api seam, kill the page duplication, decompose Recorder

**What to build:** The frontend gets the same treatment tickets 01–05 gave the backend: modules named for what they are, one home per shared constant, and components that own one concern. Four independent parts, landable in any order and separately reviewable — none changes rendered output or network behaviour.

**1. The api-client seam is called `auth.js`.** Ticket 05 built "one api-client interface" but left it in `utils/auth.js`, so every page's HTTP goes through a file named for one of its two concerns. Split into `api/client.js` (`API_BASE`, `request`, `apiFetch`, `apiGet`) and `api/auth.js` (token storage, the `lecho-auth-changed` event, `login`, `register`). Callers are `App.jsx`, `Practice.jsx`, `Results.jsx`, `AuthModal.jsx`.

**2. Dashboard and Library are the same page twice.** `pages/Dashboard.jsx:4-20` and `pages/Library.jsx:4-20` are character-identical except the function name — the `levels` array, the `levelColors` map, and the `useLoaderData`/`activeLevel`/`filtered` block. `Dashboard.jsx:32-43` and `Library.jsx:29-40` (the filter-pill markup) are character-identical too. `Practice.jsx:9` holds a third copy of `levelColors`. Extract `constants/levels.js` (`LEVELS`, `LEVEL_COLORS`) and a `<LevelFilter>` component; the two pages keep their own distinct list/grid markup.

**3. `Recorder.jsx` is 308 lines carrying five concerns:** mic + AudioContext lifecycle, shadow playback scheduling with its auto-stop poll, silence detection, the client-side duration gates, and an inline headphones modal that re-implements `AuthModal`'s `auth-overlay`/`auth-modal` markup. Extract a `useRecorder` hook for the media-graph lifecycle (start/stop/release, the `isRecordingRef` mirror, the analyser tap) and a `HeadphonesModal` component. The component keeps the UI; the hook keeps the imperative teardown, which is where the leak risk lives.

**4. Cross-stack constants are mirrored by hand.** `Recorder.jsx:6-8` mirrors `SOLO_TOLERANCE_FRAC`/`SHADOW_TAIL_S`/`SHADOW_TOLERANCE_S` from `backend/domain/job_gates.py`; `PitchChart.jsx:46` mirrors `SEGMENT_PITCH_THRESHOLD_SEMITONES` from `backend/domain/dsp/constants.py` with the comment "Kept in sync by hand". Collect both into one `constants/gates.js` naming the backend module as the source of truth. **Do not** build a codegen or build-time sync step — four numbers do not justify a pipeline, and the backend now has exactly one file to point at for each.

**Explicitly out of scope:** `index.css` is 1324 lines for the whole app and is worth splitting, but only after parts 2 and 3 settle the component boundaries — otherwise the split is guesswork. Raise it as its own ticket afterwards.

**Blocked by:** None — frontend only, and the backend reorganization it references has landed.

**Status:** ready-for-agent

- [ ] All HTTP crosses `api/client.js`; no component imports a file named `auth` to make a request
- [ ] `levels`/`levelColors` declared once; Dashboard, Library and Practice import them
- [ ] Filter-pill markup exists once as a component used by both pages
- [ ] `Recorder.jsx` under ~150 lines; mic teardown lives in `useRecorder`; headphones modal is its own component
- [ ] Each mirrored constant declared once on the frontend, with the backend module named in a comment
- [ ] `npm test` green (19 tests), and `npm run lint` clean
- [ ] Manual pass unchanged: record a solo take and a shadow take, both reach a scored Results page with the pitch chart
