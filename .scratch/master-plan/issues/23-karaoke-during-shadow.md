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

**Status:** ready-for-agent

- [ ] During a shadow take, words highlight in time with the native audio the user is shadowing
- [ ] Solo listening still highlights exactly as before (no regression to the wavesurfer path)
- [ ] Solo *takes* are unaffected — no transcript playback where there is no native audio
- [ ] The transcript is visible on screen during a shadow take without scrolling away from the recorder
- [ ] No second timer added; the existing 50ms auto-stop poll carries the clock
- [ ] A practice with no alignment still renders nothing, in both modes
- [ ] Frontend suite green (`npm test`)
