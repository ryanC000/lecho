import React, { useState, useRef, useEffect } from 'react';
import { blobToWav } from '../utils/audio';
import LiveWaveform from './LiveWaveform';

// For simplicity, passing the native duration down as a prop
export default function Recorder({ nativeDuration, onUpload }) {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  // Exposed to the live waveform so it can read the mic signal in real time.
  const [analyser, setAnalyser] = useState(null);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const analyserRef = useRef(null);
  const audioContextRef = useRef(null);
  const streamRef = useRef(null);
  const timerRef = useRef(null);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
      analyserRef.current = audioContextRef.current.createAnalyser();
      const source = audioContextRef.current.createMediaStreamSource(stream);
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
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      clearInterval(timerRef.current);
    }
  };

  // Release the microphone and tear down the audio graph once we're done with it.
  const releaseMic = () => {
    setAnalyser(null);
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

      // Validation: ±20% of native duration (mirrors the backend gate).
      if (nativeDuration) {
        const lowerBound = nativeDuration * 0.8;
        const upperBound = nativeDuration * 1.2;
        if (durationInSeconds < lowerBound || durationInSeconds > upperBound) {
          setError(`Recording duration (${durationInSeconds}s) must be within ±20% of native sample (${nativeDuration}s).`);
          return;
        }
      }

      onUpload(wavBlob, durationInSeconds);
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
    </div>
  );
}
