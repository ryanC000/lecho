# 23 — Karaoke transcript does not follow along during shadow takes

**Symptom:** The follow-along transcript highlights words correctly when the user plays the native
clip on its own, but stays inert during a shadow take — exactly when a learner most needs it, since
shadowing means speaking along with the native audio in real time.

**Why it happens:** the two playbacks use different engines, and the karaoke is wired to only one.

- [TranscriptKaraoke.jsx](../../../frontend/src/components/TranscriptKaraoke.jsx) takes a
  `wavesurfer` prop and drives itself entirely off that instance — it subscribes to `audioprocess`
  and `timeupdate` and reads `wavesurfer.getCurrentTime()`. No wavesurfer activity means no
  highlighting, and `playing` never becomes true, so `activeIndex` stays `-1`.
- Shadow playback never touches wavesurfer. [Recorder.jsx](../../../frontend/src/components/Recorder.jsx)
  builds its own `AudioContext`, decodes the clip into `nativeBuffer`, and plays it through
  `ctx.createBufferSource()` with `playback.start(t0)`. The native section's wavesurfer sits idle.
- Placement compounds it: `TranscriptKaraoke` is rendered inside the **Native Reference** section of
  [Practice.jsx](../../../frontend/src/pages/Practice.jsx), not the recording section the user is
  looking at mid-take.

**What to build:** Decouple the karaoke from wavesurfer so any playback source can drive it, then
feed it the shadow clock.

1. Change the component's interface from a `wavesurfer` instance to a plain time source — a
   `currentTime` (seconds into the native clip) and an `isPlaying` boolean. The zip/normalize logic
   and the `activeIndex` lookup are unchanged; only the `useEffect` that subscribes to wavesurfer
   goes away.
2. `Practice.jsx` keeps a small adapter for the existing wavesurfer path so solo listening behaves
   exactly as it does now.
3. `Recorder.jsx` publishes elapsed playback time during a shadow take. **It already computes this**
   — the auto-stop `setInterval` runs every 50ms and evaluates `ctx.currentTime - t0`. Reuse that
   loop rather than adding a second timer; 50ms is comfortably finer than word duration.
4. Make the transcript visible where the user is looking during a shadow take.

**Constraints worth respecting:**

- Alignment timestamps are seconds into the native clip. `wavesurfer.getCurrentTime()` is media
  time, so it stays correct under the native section's speed control. `ctx.currentTime - t0` is
  wall-clock elapsed, which matches only because shadow playback runs at rate 1.0 — if a shadow
  speed control is ever added, this breaks. Name the assumption where the clock is published.
- The "no alignment → render nothing" behaviour must survive; `words` is `undefined` for practices
  without an alignment, and `buildTokens` must keep tolerating that (see `246f71d`).
- Solo mode has no native playback during the take. Its behaviour must not change.

**Blocked by:** None. **Overlaps** architecture ticket 06 part 3, which extracts a `useRecorder`
hook from this same file — whichever lands second should rebase rather than merge blind.

**Status:** done — `bf572fe`, 2026-08-08

- [x] During a shadow take, words highlight in time with the native audio the user is shadowing
- [x] Solo listening still highlights exactly as before (no regression to the wavesurfer path)
- [x] Solo *takes* are unaffected — no transcript playback where there is no native audio
- [x] The transcript is visible on screen during a shadow take without scrolling away from the recorder
- [x] No second timer added; the existing 50ms auto-stop poll carries the clock
- [x] A practice with no alignment still renders nothing, in both modes
- [x] Frontend suite green (`npm test`)

**How it landed:** `TranscriptKaraoke` now takes `currentTime`/`isPlaying` instead of a `wavesurfer`
instance. The wavesurfer subscription moved verbatim into a new `WavesurferKaraoke` adapter
(`frontend/src/components/WavesurferKaraoke.jsx`) rather than staying inline in `Practice.jsx` —
every other component in the repo lives under `components/`, and keeping it separate also stops the
playback clock re-rendering the transcription overlay and waveform. `Recorder` publishes
`shadowTime` from the existing 50ms poll and renders the transcript itself.

Verified by automated tests only (no manual browser pass): 35 frontend tests across 5 files, with
new coverage for the plain clock (`TranscriptKaraoke.test.jsx`), the wavesurfer path including
unsubscribe-on-unmount (`WavesurferKaraoke.test.jsx`), and the shadow take driven end to end through
a fake advancing `AudioContext` (`Recorder.test.jsx`). The *visual* quality of the highlight
in a real browser — timing feel, legibility while speaking — is unchecked and human-only.

**Known, not addressed:** during a shadow take the transcript is on screen three times — the
`TranslationOverlay`, the now-inert karaoke under Native Reference, and the live one in the
recorder. Pre-existing placement the ticket didn't ask to change; worth a look if it reads as noise.
