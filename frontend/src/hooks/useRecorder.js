import { useRef, useState, useEffect } from 'react';
import { blobToWav } from '../utils/audio';
import { SOLO_TOLERANCE_FRAC, SHADOW_TAIL_S, SHADOW_TOLERANCE_S } from '../constants/gates';

/**
 * Owns the mic + AudioContext media graph: start/stop/release, shadow
 * playback with its auto-stop poll, silence detection, and the client-side
 * duration gates. Recorder.jsx keeps the UI; this hook keeps the imperative
 * teardown, which is where the leak risk lives.
 */
export default function useRecorder({ nativeDuration, nativeAudioUrl, onUpload }) {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  // Exposed to the live waveform so it can read the mic signal in real time.
  const [analyser, setAnalyser] = useState(null);
  // Seconds into the native clip while a shadow take plays it; null when no
  // native playback is running (always, in solo mode). Ticking this at 20Hz
  // re-renders the whole recorder, which is cheap — the live waveform draws on
  // its own rAF loop and its effect deps don't change.
  const [shadowTime, setShadowTime] = useState(null);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const analyserRef = useRef(null);
  const audioContextRef = useRef(null);
  const streamRef = useRef(null);
  const timerRef = useRef(null);
  // Shadow-take machinery: the native playback node, its auto-stop poll, and
  // the mode captured at take start (so toggling mid-take can't skew the gate).
  const nativeSourceRef = useRef(null);
  const autoStopRef = useRef(null);
  const takeModeRef = useRef('solo');
  // Mirror of isRecording for callbacks created before the state updated
  // (the auto-stop interval closes over a stale render otherwise).
  const isRecordingRef = useRef(false);

  const startTake = async (mode) => {
    takeModeRef.current = mode;
    audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
    const ctx = audioContextRef.current;

    // Shadow: decode the native clip up front so playback and recording can
    // start back-to-back on the same audio-context clock.
    let nativeBuffer = null;
    if (mode === 'shadow') {
      try {
        const res = await fetch(nativeAudioUrl);
        nativeBuffer = await ctx.decodeAudioData(await res.arrayBuffer());
      } catch (err) {
        setError('Could not load the native clip for shadowing. Please try again.');
        releaseMic();
        return;
      }
    }

    try {
      // Browser defaults leave AGC/noise-suppression/echo-cancellation ON —
      // AGC's time-varying gain distorts the RMS contour the backend scores,
      // and noise suppression can distort F0 (PRD FR-1). Disable all three.
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      });
      streamRef.current = stream;
      analyserRef.current = ctx.createAnalyser();
      // The mic feeds ONLY this analyser tap — never ctx.destination, which
      // would loop the mic back out of the speakers.
      const source = ctx.createMediaStreamSource(stream);
      source.connect(analyserRef.current);
      analyserRef.current.fftSize = 1024;
      setAnalyser(analyserRef.current);

      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = handleStopRecording;

      mediaRecorder.start();
      if (nativeBuffer) {
        // Start native playback back-to-back with the recorder and auto-stop
        // at native duration + tail, both read off the context clock.
        // MediaRecorder's start latency is deliberately NOT compensated for —
        // silence-trim + DTW absorb it.
        const playback = ctx.createBufferSource();
        playback.buffer = nativeBuffer;
        playback.connect(ctx.destination);
        nativeSourceRef.current = playback;
        const t0 = ctx.currentTime;
        playback.start(t0);
        setShadowTime(0);
        autoStopRef.current = setInterval(() => {
          // Wall-clock elapsed since playback started. It doubles as the
          // follow-along transcript's position in the native clip ONLY because
          // shadow playback always runs at rate 1.0 — a shadow speed control
          // would have to publish media time instead.
          const elapsed = ctx.currentTime - t0;
          setShadowTime(elapsed);
          if (elapsed >= nativeBuffer.duration + SHADOW_TAIL_S) {
            stopRecording();
          }
        }, 50);
      }
      isRecordingRef.current = true;
      setIsRecording(true);
      setError(null);
      setRecordingTime(0);

      // Simple timer. We compute the elapsed seconds here and hand it to
      // checkSilence so it isn't reading a stale value from the closure.
      timerRef.current = setInterval(() => {
        setRecordingTime((prev) => {
          const next = prev + 1;
          checkSilence(next);
          return next;
        });
      }, 1000);

    } catch (err) {
      setError("Microphone access denied or unavailable.");
      releaseMic();
    }
  };

  const checkSilence = (elapsedSeconds) => {
    if (!analyserRef.current) return;
    const bufferLength = analyserRef.current.fftSize;
    const dataArray = new Uint8Array(bufferLength);
    analyserRef.current.getByteTimeDomainData(dataArray);

    // Real mic silence sits *near* 128 (with a little noise), not exactly at it.
    // Treat the signal as silent if every sample stays within a small threshold.
    const SILENCE_THRESHOLD = 1; // out of 128
    const isSilent = dataArray.every((val) => Math.abs(val - 128) <= SILENCE_THRESHOLD);
    if (isSilent && elapsedSeconds > 2) {
      setError("We aren't detecting any audio. It seems like your mic is not working.");
    }
  };

  const stopRecording = () => {
    if (!isRecordingRef.current) return;
    isRecordingRef.current = false;
    clearInterval(timerRef.current);
    clearInterval(autoStopRef.current);
    if (nativeSourceRef.current) {
      try { nativeSourceRef.current.stop(); } catch (err) { /* already ended */ }
      nativeSourceRef.current = null;
    }
    setShadowTime(null);
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();
    }
    setIsRecording(false);
  };

  // Release the microphone and tear down the audio graph once we're done with it.
  const releaseMic = () => {
    setAnalyser(null);
    clearInterval(autoStopRef.current);
    if (nativeSourceRef.current) {
      try { nativeSourceRef.current.stop(); } catch (err) { /* already ended */ }
      nativeSourceRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close();
    }
    audioContextRef.current = null;
    analyserRef.current = null;
  };

  const handleStopRecording = async () => {
    // MediaRecorder gives us WebM/Opus (or mp4 on Safari), NOT wav — transcode
    // to real PCM WAV so the backend can read it, and get the precise duration.
    const recordedBlob = new Blob(audioChunksRef.current, {
      type: mediaRecorderRef.current?.mimeType || 'audio/webm',
    });

    setIsProcessing(true);
    try {
      const { blob: wavBlob, duration } = await blobToWav(recordedBlob);
      const durationInSeconds = Number(duration.toFixed(2));

      // Validation mirrors the backend's per-mode gate.
      if (nativeDuration) {
        if (takeModeRef.current === 'shadow') {
          const expected = nativeDuration + SHADOW_TAIL_S;
          if (Math.abs(durationInSeconds - expected) > SHADOW_TOLERANCE_S) {
            setError(`Shadow recording (${durationInSeconds}s) should run about ${expected.toFixed(1)}s — the native clip plus a ${SHADOW_TAIL_S}s tail.`);
            return;
          }
        } else {
          const lowerBound = nativeDuration * (1 - SOLO_TOLERANCE_FRAC);
          const upperBound = nativeDuration * (1 + SOLO_TOLERANCE_FRAC);
          if (durationInSeconds < lowerBound || durationInSeconds > upperBound) {
            setError(`Recording duration (${durationInSeconds}s) must be within ±${SOLO_TOLERANCE_FRAC * 100}% of native sample (${nativeDuration}s).`);
            return;
          }
        }
      }

      onUpload(wavBlob, durationInSeconds, takeModeRef.current);
    } catch (err) {
      setError('Could not process the recording. Please try again.');
    } finally {
      setIsProcessing(false);
      releaseMic();
    }
  };

  // Make sure the mic is released if the component unmounts mid-recording.
  useEffect(() => {
    return () => {
      clearInterval(timerRef.current);
      releaseMic();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    isRecording,
    error,
    isProcessing,
    recordingTime,
    analyser,
    shadowTime,
    startTake,
    stopRecording,
  };
}
