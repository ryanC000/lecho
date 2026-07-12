import React, { useState, useRef, useEffect } from 'react';
import { blobToWav } from '../utils/audio';
import LiveWaveform from './LiveWaveform';

// Client mirror of the server's per-mode duration gates (backend main.py).
const SHADOW_TAIL_S = 1.0;
const SHADOW_TOLERANCE_S = 0.5;
// Session flag: the user confirmed they're on headphones for shadow takes.
const HEADPHONES_KEY = 'lecho_headphones_ok';

// For simplicity, passing the native duration down as a prop
export default function Recorder({ nativeDuration, nativeAudioUrl, mode = 'solo', onUpload }) {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [showHeadphonesModal, setShowHeadphonesModal] = useState(false);
  // Exposed to the live waveform so it can read the mic signal in real time.
  const [analyser, setAnalyser] = useState(null);

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

  const startRecording = async () => {
    // First shadow take of the session: confirm headphones before anything
    // plays out of the speakers (PRD §5 / Edge Case 3).
    if (mode === 'shadow' && !sessionStorage.getItem(HEADPHONES_KEY)) {
      setShowHeadphonesModal(true);
      return;
    }
    await beginTake();
  };

  const confirmHeadphones = async () => {
    sessionStorage.setItem(HEADPHONES_KEY, '1');
    setShowHeadphonesModal(false);
    await beginTake();
  };

  const beginTake = async () => {
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
        autoStopRef.current = setInterval(() => {
          if (ctx.currentTime - t0 >= nativeBuffer.duration + SHADOW_TAIL_S) {
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
    const SILENCE_THRESHOLD = 2; // out of 128
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

  // Format seconds as m:ss for the on-page timer.
  const formatTime = (secs) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${String(s).padStart(2, '0')}`;
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
          const lowerBound = nativeDuration * 0.8;
          const upperBound = nativeDuration * 1.2;
          if (durationInSeconds < lowerBound || durationInSeconds > upperBound) {
            setError(`Recording duration (${durationInSeconds}s) must be within ±20% of native sample (${nativeDuration}s).`);
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

  return (
    <div className="recorder-container">
      <h3>Record your version 🎙</h3>

      {/* On-page recording status: pulsing indicator + prominent timer */}
      {(isRecording || recordingTime > 0) && (
        <div className={`recording-status${isRecording ? ' is-recording' : ''}`}>
          <div className="recording-indicator">
            <span className="rec-dot" />
            <span className="rec-label">{isRecording ? 'Recording' : 'Recorded'}</span>
          </div>
          <span className="recording-timer">{formatTime(recordingTime)}</span>
        </div>
      )}

      {/* Live reactive sound wave — visible feedback that the mic is picking up audio */}
      {isRecording && <LiveWaveform analyser={analyser} active={isRecording} />}

      <div className="controls">
        {isProcessing ? (
          <button className="btn-primary" disabled>
            Processing…
          </button>
        ) : !isRecording ? (
          <button className="btn-primary" onClick={startRecording}>
            Start Recording
          </button>
        ) : (
          <button className="btn-danger" onClick={stopRecording}>
            Stop Recording
          </button>
        )}
      </div>
      {error && <div className="alert-error">{error}</div>}

      {/* Headphones confirmation before the first shadow take of the session */}
      {showHeadphonesModal && (
        <div className="auth-overlay" onClick={() => setShowHeadphonesModal(false)}>
          <div
            className="auth-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Headphones check"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="auth-header">
              <h2 className="auth-title">Headphones on? 🎧</h2>
              <p className="auth-sub">
                Shadowing plays the native clip while you record — use headphones
                so your mic only hears you
              </p>
            </div>
            <div className="controls" style={{ justifyContent: 'center' }}>
              <button className="btn-primary" onClick={confirmHeadphones}>
                I'm wearing headphones
              </button>
              <button onClick={() => setShowHeadphonesModal(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
