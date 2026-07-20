import React, { useEffect, useMemo, useState } from 'react';

/**
 * Follow-along transcript that lights up the word currently being spoken in the
 * native clip. Driven by the native player's playback clock (wavesurfer). When
 * the practice has no alignment (words absent), the component renders nothing —
 * the feature is simply off.
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
    const word = normalizeToken(raw) && wi < words.length ? words[wi++] : null;
    return { raw, word };
  });
}

export default function TranscriptKaraoke({ transcript, words, wavesurfer }) {
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!wavesurfer) return;
    const onProcess = () => setTime(wavesurfer.getCurrentTime());
    const onPlay = () => setPlaying(true);
    const onStop = () => setPlaying(false);
    // wavesurfer v7 .on() returns its own unsubscribe fn.
    const unsubs = [
      wavesurfer.on('audioprocess', onProcess),
      wavesurfer.on('timeupdate', onProcess),
      wavesurfer.on('play', onPlay),
      wavesurfer.on('pause', onStop),
      wavesurfer.on('finish', onStop),
    ];
    return () => unsubs.forEach((u) => u());
  }, [wavesurfer]);

  const tokens = useMemo(() => buildTokens(transcript, words), [transcript, words]);
  if (!words || words.length === 0) return null;

  const activeIndex = playing
    ? tokens.findIndex((t) => t.word && time >= t.word.start && time < t.word.end)
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
