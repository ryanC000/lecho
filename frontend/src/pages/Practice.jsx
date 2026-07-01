import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link, useLoaderData } from 'react-router-dom';
import Recorder from '../components/Recorder';
import AudioVisualizer from '../components/AudioVisualizer';
import TranslationOverlay from '../components/TranslationOverlay';
import { generateMockAudioBlob } from '../utils/audio';
import { apiFetch, isLoggedIn } from '../utils/auth';

const levelColors = {
  A1: 'var(--color-level-a1)',
  A2: 'var(--color-level-a2)',
  B1: 'var(--color-level-b1)',
  B2: 'var(--color-level-b2)',
  C1: 'var(--color-level-c1)',
};

export default function Practice() {
  const { id } = useParams();
  const navigate = useNavigate();
  const practice = useLoaderData();
  const [userAudioUrl, setUserAudioUrl] = useState(null);
  const [nativeAudioUrl, setNativeAudioUrl] = useState(null);
  const [uploadError, setUploadError] = useState(null);

  useEffect(() => {
    if (!practice) return;
    
    if (practice.audio_url) {
      setNativeAudioUrl(practice.audio_url);
    } else {
      const blob = generateMockAudioBlob(practice.duration);
      setNativeAudioUrl(URL.createObjectURL(blob));
    }

    return () => {
      if (nativeAudioUrl && !practice.audio_url) {
        URL.revokeObjectURL(nativeAudioUrl);
      }
    };
  }, [practice]);

  const handleUpload = async (audioBlob, duration) => {
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
          <AudioVisualizer
            audioUrl={nativeAudioUrl}
            color="var(--color-accent-violet)"
            showSpeedControl={true}
          />
        ) : (
          <p className="hand-text text-lg" style={{ color: 'var(--color-ink-light)' }}>
            Loading audio…
          </p>
        )}
      </section>

      {/* ── Recording ── */}
      <section className="flat-section">
        <Recorder nativeDuration={practice.duration} onUpload={handleUpload} />
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
    </div>
  );
}
