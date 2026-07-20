import React, { useState } from 'react';
import { useParams, useNavigate, Link, useLoaderData } from 'react-router-dom';
import Recorder from '../components/Recorder';
import AudioVisualizer from '../components/AudioVisualizer';
import TranslationOverlay from '../components/TranslationOverlay';
import TranscriptKaraoke from '../components/TranscriptKaraoke';
import { apiFetch, isLoggedIn, API_BASE } from '../utils/auth';

const levelColors = {
  A1: 'var(--color-level-a1)',
  A2: 'var(--color-level-a2)',
  B1: 'var(--color-level-b1)',
  B2: 'var(--color-level-b2)',
  C1: 'var(--color-level-c1)',
};

// Capture mode, persisted for the session (PRD 8.7: shadow is the default).
const MODE_KEY = 'lecho_practice_mode';

export default function Practice() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { practice, alignment } = useLoaderData();
  const [userAudioUrl, setUserAudioUrl] = useState(null);
  const [uploadError, setUploadError] = useState(null);
  const [nativeWave, setNativeWave] = useState(null);
  const [mode, setMode] = useState(() =>
    sessionStorage.getItem(MODE_KEY) === 'solo' ? 'solo' : 'shadow'
  );

  const changeMode = (next) => {
    setMode(next);
    sessionStorage.setItem(MODE_KEY, next);
  };

  // Native clips are served by the backend; no reference audio means the
  // practice isn't ready — never substitute a synthetic tone.
  const nativeAudioUrl = practice?.audio_url
    ? `${API_BASE}/practices/${practice.id}/audio`
    : null;

  const handleUpload = async (audioBlob, duration, takeMode = 'solo') => {
    setUploadError(null);

    // Local playback of what we recorded.
    const url = URL.createObjectURL(audioBlob);
    setUserAudioUrl(url);

    if (!isLoggedIn()) {
      setUploadError('Please log in before submitting a recording.');
      return;
    }

    // Real multipart upload to POST /jobs.
    const formData = new FormData();
    formData.append('file', audioBlob, 'recording.wav');
    formData.append('practice_id', String(practice.id));
    formData.append('user_audio_duration', String(duration));
    formData.append('mode', takeMode);

    try {
      const res = await apiFetch('/jobs', { method: 'POST', body: formData });
      const job = await res.json();
      // Navigate using the REAL job id returned by the backend.
      navigate(`/results/${job.id}`);
    } catch (err) {
      setUploadError(
        err.status === 401
          ? 'Your session expired. Please log in again.'
          : `Upload failed: ${err.message}`
      );
    }
  };

  return (
    <div className="workspace">
      <Link 
        to="/" 
        viewTransition 
        className="back-btn"
        aria-label="Back to Dashboard"
      >
        ← Back
      </Link>

      {/* ── Practice header with metadata ── */}
      <section className="practice-header">
        <h2 className="practice-title" style={{ viewTransitionName: `title-${practice.id}` }}>{practice.title}</h2>
        <div className="meta-badges">
          <span
            className="level-badge"
            style={{ 
              backgroundColor: levelColors[practice.level],
              viewTransitionName: `level-${practice.id}`
            }}
          >
            {practice.level}
          </span>
          <span className="meta-tag" style={{ viewTransitionName: `length-${practice.id}` }}>{practice.length}</span>
          <span className="meta-tag" style={{ viewTransitionName: `speed-${practice.id}` }}>{practice.speed} speed</span>
        </div>
      </section>

      {/* ── Video / Audio placeholder ── */}
      {practice.video_url ? (
        <section className="flat-section">
          <h3>Video</h3>
          <div className="video-container">
            <video controls src={practice.video_url} />
          </div>
        </section>
      ) : (
        <section className="flat-section">
          <div className="video-placeholder">
            <div className="video-placeholder-inner">
              <span className="video-placeholder-icon">🎬</span>
              <span>Video will appear here</span>
            </div>
          </div>
        </section>
      )}

      {/* ── Transcription with click-to-translate ── */}
      <section className="context-banner flat-section">
        <h2>Transcription</h2>
        <TranslationOverlay text={practice.transcript} />
        {practice.notes && (
          <div className="notes">
            ✎ {practice.notes}
          </div>
        )}
      </section>

      {/* ── Native audio waveform with speed control ── */}
      <section className="flat-section">
        <h3>Native Reference ♪</h3>
        {nativeAudioUrl ? (
          <>
            <AudioVisualizer
              audioUrl={nativeAudioUrl}
              color="var(--color-accent-violet)"
              showSpeedControl={true}
              onReady={setNativeWave}
            />
            <TranscriptKaraoke
              transcript={practice.transcript}
              words={alignment?.words}
              wavesurfer={nativeWave}
            />
          </>
        ) : (
          <p className="hand-text text-lg" style={{ color: 'var(--color-ink-light)' }}>
            This practice isn't ready yet — reference audio coming soon.
          </p>
        )}
      </section>

      {/* ── Recording (only when there's a real reference to score against) ── */}
      {nativeAudioUrl && (
        <section className="flat-section">
          <div className="mode-toggle" role="radiogroup" aria-label="Practice mode">
            <button
              role="radio"
              aria-checked={mode === 'shadow'}
              className={`mode-btn${mode === 'shadow' ? ' active' : ''}`}
              onClick={() => changeMode('shadow')}
            >
              Shadow
            </button>
            <button
              role="radio"
              aria-checked={mode === 'solo'}
              className={`mode-btn${mode === 'solo' ? ' active' : ''}`}
              onClick={() => changeMode('solo')}
            >
              Solo
            </button>
          </div>
          <p className="mode-hint">
            {mode === 'shadow'
              ? 'The native clip plays while you record — speak along with it.'
              : 'Record on your own, then compare with the native clip.'}
          </p>
          <Recorder
            nativeDuration={practice.duration}
            nativeAudioUrl={nativeAudioUrl}
            mode={mode}
            onUpload={handleUpload}
          />
          {uploadError && <div className="alert-error">{uploadError}</div>}
          {userAudioUrl && (
            <div className="playback">
              <h4 className="hand-text text-lg mb-2" style={{ color: 'var(--color-ink-light)' }}>
                Your Recording
              </h4>
              <AudioVisualizer audioUrl={userAudioUrl} color="var(--color-accent-warm)" />
            </div>
          )}
        </section>
      )}
    </div>
  );
}
