import React, { useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import AccuracyRing from '../components/AccuracyRing';
import TranslationOverlay from '../components/TranslationOverlay';
import practices from '../data/practicesData';

export default function Results() {
  const { jobId } = useParams();

  const practice = useMemo(
    () => practices.find(p => p.id === Number(jobId)) || practices[0],
    [jobId]
  );

  // Mocked results
  const results = {
    score: 85.5,
    segments: [
      {
        start: 2.1,
        end: 2.8,
        tag: 'INTONATION_DROP',
        explanation: 'Your pitch dropped when it should have risen.',
      },
      {
        start: 4.2,
        end: 4.8,
        tag: 'SYLLABLE_STRETCH',
        explanation: 'You cut the final syllable too short.',
      },
    ],
  };

  return (
    <div className="workspace page-enter">
      {/* ── Accuracy Ring ── */}
      <section className="results-hero">
        <AccuracyRing score={results.score} size={200} strokeWidth={14} />
      </section>

      {/* ── Transcript + Translation ── */}
      <section className="context-banner flat-section">
        <h2>Practice Transcript</h2>
        <TranslationOverlay text={practice.transcript} />
      </section>

      <hr />

      {/* ── Detailed Feedback ── */}
      <section className="flat-section">
        <h3>Detailed Feedback ✎</h3>
        <div className="feedback-list">
          {results.segments.map((seg, idx) => (
            <div
              key={idx}
              className="feedback-card"
              style={{ animationDelay: `${0.3 + idx * 0.12}s` }}
            >
              <div className="feedback-card-tag">
                <span className="feedback-time">
                  {seg.start}s – {seg.end}s
                </span>
                <span className="feedback-badge">{seg.tag.replace(/_/g, ' ')}</span>
              </div>
              <p className="feedback-explanation">{seg.explanation}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Actions ── */}
      <div className="results-actions">
        <Link to={`/practice/${practice.id}`}>
          <button className="btn-primary">Practice Again</button>
        </Link>
        <Link to="/">
          <button>Back to Dashboard</button>
        </Link>
      </div>
    </div>
  );
}
