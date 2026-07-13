# 10 — Karaoke transcript highlighting

**What to build:** During native-clip playback, the transcript word whose alignment interval contains the current playback time lights up. Transcript tokens are matched to alignment words by normalizing both with the same rules as the alignment corpus (lowercase, punctuation stripped except apostrophes/hyphens, digits spelled out) and matching sequentially, skipping punctuation-only tokens. Practices without an alignment (404) simply don't highlight — feature off, no error. In shadow mode (once ticket 09 exists), the clock is the audio-context time; for plain playback, the player's time events.

**Blocked by:** 06 (alignment endpoint). Demoable with solo playback alone; shadow-clock sync activates when 09 lands.

**Status:** ready-for-agent

- [ ] Words highlight in sync during playback on an aligned practice, by ear
- [ ] Unaligned practice: no highlighting, no console errors
- [ ] Token↔word matching survives punctuation and apostrophes in the transcript
