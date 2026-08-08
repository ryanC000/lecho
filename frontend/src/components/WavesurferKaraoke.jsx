import React, { useState, useEffect } from 'react';
import TranscriptKaraoke from './TranscriptKaraoke';

/**
 * Adapter from the native player's wavesurfer instance to the plain clock
 * TranscriptKaraoke consumes. Kept separate from the page so the ~60Hz playback
 * clock re-renders the transcript alone, not the transcription overlay and
 * waveform alongside it.
 */
export default function WavesurferKaraoke({ transcript, words, wavesurfer }) {
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  useEffect(() => {
    if (!wavesurfer) return;
    // getCurrentTime() is media time, so it stays correct under the speed control.
    const onProcess = () => setCurrentTime(wavesurfer.getCurrentTime());
    const onPlay = () => setIsPlaying(true);
    const onStop = () => setIsPlaying(false);
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

  return (
    <TranscriptKaraoke
      transcript={transcript}
      words={words}
      currentTime={currentTime}
      isPlaying={isPlaying}
    />
  );
}
