import React, { useState, useRef, useEffect } from 'react';
import { blobToWav } from '../utils/audio';

// For simplicity, passing the native duration down as a prop
export default function Recorder({ nativeDuration, onUpload }) {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const analyserRef = useRef(null);
  const audioContextRef = useRef(null);
  const timerRef = useRef(null);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
      analyserRef.current = audioContextRef.current.createAnalyser();
      const source = audioContextRef.current.createMediaStreamSource(stream);
      source.connect(analyserRef.current);
      analyserRef.current.fftSize = 256;

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

      // Simple timer
      timerRef.current = setInterval(() => {
        setRecordingTime((prev) => prev + 1);
        checkSilence();
      }, 1000);

    } catch (err) {
      setError("Microphone access denied or unavailable.");
    }
  };

  const checkSilence = () => {
    if (!analyserRef.current) return;
    const bufferLength = analyserRef.current.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    analyserRef.current.getByteTimeDomainData(dataArray);

    // Simple heuristic: if all values are ~128 (silence in 8-bit PCM), it's silent
    const isSilent = dataArray.every(val => val === 128);
    if (isSilent && recordingTime > 2) {
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
    }
  };

  return (
    <div className="recorder-container">
      <h3>Record your version 🎙</h3>
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
            Stop Recording ({recordingTime}s)
          </button>
        )}
      </div>
      {error && <div className="alert-error">{error}</div>}
    </div>
  );
}
