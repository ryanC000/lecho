import React, { useEffect, useState, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import AccuracyRing from '../components/AccuracyRing';
import TranslationOverlay from '../components/TranslationOverlay';
import { apiFetch } from '../utils/auth';

const POLL_INTERVAL_MS = 2000;

export default function Results() {
  const { jobId } = useParams();
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const timerRef = useRef(null);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const res = await apiFetch(`/jobs/${jobId}`);
        const data = await res.json();
        if (cancelled) return;
        setJob(data);
        // Keep polling only while the job is still being processed.
        if (data.status === 'SUCCESS' || data.status === 'FAILED') {
          clearInterval(timerRef.current);
        }
      } catch (err) {
        if (cancelled) return;
        setError(
          err.status === 401
            ? 'Please log in to view your results.'
            : `Could not load results: ${err.message}`
        );
        clearInterval(timerRef.current);
      }
    };

    poll(); // fire immediately, then on an interval
    timerRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timerRef.current);
    };
  }, [jobId]);

  if (error) {
    return (
      <div className="workspace page-enter">
        <div className="alert-error">{error}</div>
        <div className="results-actions">
          <Link to="/"><button>Back to Dashboard</button></Link>
        </div>
      </div>
    );
  }

  // Still processing (PENDING / PROCESSING) or first load.
  if (!job || (job.status !== 'SUCCESS' && job.status !== 'FAILED')) {
    return (
      <div className="workspace page-enter">
        <section className="results-hero">
          <p className="hand-text text-lg">Analyzing your recording…</p>
        </section>
      </div>
    );
  }

  if (job.status === 'FAILED') {
    // Only offer "Try Again" when re-recording could actually help. Some
    // failures (e.g. a practice with no reference audio yet) aren't the
    // user's fault and won't change on a retry.
    const canRetry = job.retryable !== false;
    return (
      <div className="workspace page-enter">
        <div className="alert-error">
          {job.error_message || "We couldn't analyze this recording."}
        </div>
        <div className="results-actions">
          {canRetry && job.practice_id && (
            <Link to={`/practice/${job.practice_id}`}>
              <button className="btn-primary">Try Again</button>
            </Link>
          )}
          <Link to="/"><button>Back to Dashboard</button></Link>
        </div>
      </div>
    );
  }

  const segments = job.segments || [];

  return (
    <div className="workspace page-enter">
      {/* ── Accuracy Ring ── */}
      <section className="results-hero">
        <AccuracyRing score={job.score ?? 0} size={200} strokeWidth={14} />
      </section>

      {/* ── Per-axis sub-scores (null for jobs scored before dsp-2 persistence) ── */}
      {job.pitch_score != null && (
        <section className="sub-scores">
          {[
            ['Pitch', job.pitch_score],
            ['Timing', job.timing_score],
            ['Energy', job.energy_score],
          ].map(([label, value]) => (
            <div key={label} className="sub-score">
              <span className="sub-score-value">{value}</span>
              <span className="sub-score-label">{label}</span>
            </div>
          ))}
        </section>
      )}

      {/* ── Transcript + Translation ── */}
      {job.transcript && (
        <section className="context-banner flat-section">
          <h2>Practice Transcript</h2>
          <TranslationOverlay text={job.transcript} />
        </section>
      )}

      <hr />

      {/* ── Detailed Feedback ── */}
      <section className="flat-section">
        <h3>Detailed Feedback ✎</h3>
        {segments.length === 0 ? (
          <p className="hand-text text-lg" style={{ color: 'var(--color-ink-light)' }}>
            No specific issues flagged for this recording.
          </p>
        ) : (
          <div className="feedback-list">
            {segments.map((seg, idx) => (
              <div
                key={idx}
                className="feedback-card"
                style={{ animationDelay: `${0.3 + idx * 0.12}s` }}
              >
                <div className="feedback-card-tag">
                  <span className="feedback-time">
                    {seg.timestamp_start}s – {seg.timestamp_end}s
                  </span>
                  <span className="feedback-badge">
                    {(seg.feedback_tag || '').replace(/_/g, ' ')}
                  </span>
                </div>
                <p className="feedback-explanation">{seg.explanation}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ── Actions ── */}
      <div className="results-actions">
        {job.practice_id && (
          <Link to={`/practice/${job.practice_id}`}>
            <button className="btn-primary">Practice Again</button>
          </Link>
        )}
        <Link to="/">
          <button>Back to Dashboard</button>
        </Link>
      </div>
    </div>
  );
}
