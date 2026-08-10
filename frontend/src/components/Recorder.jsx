import React, { useEffect, useState } from 'react';
import LiveWaveform from './LiveWaveform';
import TranscriptKaraoke from './TranscriptKaraoke';
import HeadphonesModal from './HeadphonesModal';
import useRecorder from '../hooks/useRecorder';

// Session flag: the user confirmed they're on headphones for shadow takes.
const HEADPHONES_KEY = 'lecho_headphones_ok';

// For simplicity, passing the native duration down as a prop
export default function Recorder({
  nativeDuration,
  nativeAudioUrl,
  transcript,
  words,
  mode = 'solo',
  onUpload,
}) {
  const [showHeadphonesModal, setShowHeadphonesModal] = useState(false);
  const {
    isRecording,
    error,
    isProcessing,
    recordingTime,
    analyser,
    shadowTime,
    startTake,
    stopRecording,
  } = useRecorder({ nativeDuration, nativeAudioUrl, onUpload });

  const startRecording = async () => {
    // First shadow take of the session: confirm headphones before anything
    // plays out of the speakers (PRD §5 / Edge Case 3).
    if (mode === 'shadow' && !sessionStorage.getItem(HEADPHONES_KEY)) {
      setShowHeadphonesModal(true);
      return;
    }
    await startTake(mode);
  };

  const confirmHeadphones = async () => {
    sessionStorage.setItem(HEADPHONES_KEY, '1');
    setShowHeadphonesModal(false);
    await startTake(mode);
  };

  // Format seconds as m:ss for the on-page timer.
  const formatTime = (secs) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${String(s).padStart(2, '0')}`;
  };

  // Spacebar toggles the take while the recorder is on screen (PRD a11y).
  // No dep array: re-binding each render keeps the handler reading current state.
  useEffect(() => {
    const onKey = (e) => {
      if (e.code !== 'Space' || e.repeat) return;
      const tag = e.target.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      // Guards first: bailing out must leave Space free to press whatever has
      // focus (the headphones modal's buttons).
      if (isProcessing || showHeadphonesModal) return;
      e.preventDefault(); // stops page scroll, and Space re-firing a focused button
      if (isRecording) stopRecording();
      else startRecording();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

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

      {/* Follow-along transcript, rendered here rather than under the native
          player so it's on screen while the user is shadowing. */}
      {shadowTime !== null && (
        <TranscriptKaraoke
          transcript={transcript}
          words={words}
          currentTime={shadowTime}
          isPlaying
        />
      )}

      <div className="controls">
        {isProcessing ? (
          <button className="btn-primary" disabled>
            Processing…
          </button>
        ) : !isRecording ? (
          <button className="btn-primary" onClick={startRecording} aria-keyshortcuts="Space">
            Start Recording
          </button>
        ) : (
          <button className="btn-danger" onClick={stopRecording} aria-keyshortcuts="Space">
            Stop Recording
          </button>
        )}
      </div>
      {error && <div className="alert-error">{error}</div>}

      <HeadphonesModal
        show={showHeadphonesModal}
        onConfirm={confirmHeadphones}
        onCancel={() => setShowHeadphonesModal(false)}
      />
    </div>
  );
}
