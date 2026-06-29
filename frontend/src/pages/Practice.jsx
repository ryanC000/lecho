import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import Recorder from '../components/Recorder';
import AudioVisualizer from '../components/AudioVisualizer';
import TranslationOverlay from '../components/TranslationOverlay';
import { generateMockAudioBlob } from '../utils/audio';
import practices from '../data/practicesData';

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
  const [userAudioUrl, setUserAudioUrl] = useState(null);
  const [nativeAudioUrl, setNativeAudioUrl] = useState(null);

  const practice = useMemo(
    () => practices.find(p => p.id === Number(id)) || practices[0],
    [id]
  );

  useEffect(() => {
    if (practice.audioUrl) {
      setNativeAudioUrl(practice.audioUrl);
    } else {
      const blob = generateMockAudioBlob(practice.duration);
      setNativeAudioUrl(URL.createObjectURL(blob));
    }

    return () => {
      if (nativeAudioUrl && !practice.audioUrl) {
        URL.revokeObjectURL(nativeAudioUrl);
      }
    };
  }, [practice]);

  const handleUpload = (audioBlob, duration) => {
    const url = URL.createObjectURL(audioBlob);
    setUserAudioUrl(url);
    console.log('Mock Uploading...', duration);
    setTimeout(() => {
      navigate(`/results/${practice.id}`);
    }, 1500);
  };

  return (
    <div className="workspace page-enter">
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
      {practice.videoUrl ? (
        <section className="flat-section">
          <h3>Video</h3>
          <div className="video-container">
            <video controls src={practice.videoUrl} />
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
