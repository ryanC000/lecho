import { useMemo } from 'react';

/**
 * Follow-along transcript that lights up the word currently being spoken in the
 * native clip. Driven by whatever is playing that clip: `currentTime` is seconds
 * into the native audio and `isPlaying` says whether it is running. Callers own
 * the clock — the native player adapts wavesurfer, a shadow take adapts its
 * audio-context playback. When the practice has no alignment (words absent),
 * the component renders nothing — the feature is simply off.
 */

// Normalize a transcript token the same way align_natives.py normalizes the
// transcript before alignment: lowercase, curly→straight apostrophe, strip
// everything except letters (incl. accents), apostrophes and hyphens. Alignment
// words are already normalized this way, so equal tokens compare equal.
// (Digit-spelling is omitted — no transcript has digits; a digit would just not
// match and stay un-highlighted.)
function normalizeToken(tok) {
  return tok.toLowerCase().replace(/’/g, "'").replace(/[^\p{L}'-]/gu, '');
}

// Zip transcript tokens (split on whitespace) to alignment words positionally:
// each non-empty normalized token takes the next alignment word; punctuation-
// only tokens normalize to empty, get no word, and never highlight.
function buildTokens(transcript, words) {
  let wi = 0;
  return (transcript ? transcript.split(/\s+/) : []).map((raw) => {
    // words is absent when the practice has no alignment; hooks run before the
    // early return below, so this has to tolerate it rather than rely on that guard.
    const word = normalizeToken(raw) && wi < (words?.length ?? 0) ? words[wi++] : null;
    return { raw, word };
  });
}

export default function TranscriptKaraoke({ transcript, words, currentTime, isPlaying }) {
  const tokens = useMemo(() => buildTokens(transcript, words), [transcript, words]);
  if (!words || words.length === 0) return null;

  const activeIndex = isPlaying
    ? tokens.findIndex((t) => t.word && currentTime >= t.word.start && currentTime < t.word.end)
    : -1;

  return (
    <p className="karaoke-transcript" aria-hidden="true">
      {tokens.map((t, i) => (
        <span key={i} className={`karaoke-word${i === activeIndex ? ' active' : ''}`}>
          {t.raw}{' '}
        </span>
      ))}
    </p>
  );
}
