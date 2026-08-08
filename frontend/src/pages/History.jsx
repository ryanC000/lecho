import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { apiFetch } from '../utils/auth';

const PAGE_SIZE = 20;

export default function History() {
  const [page, setPage] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch(`/jobs?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`)
      .then((res) => res.json())
      .then((body) => { if (!cancelled) setData(body); })
      .catch((err) => {
        if (cancelled) return;
        setError(
          err.status === 401
            ? 'Please log in to see your history.'
            : `Could not load your history: ${err.message}`
        );
      });
    return () => { cancelled = true; };
  }, [page]);

  if (error) {
    return (
      <div className="flat-section">
        <div className="alert-error">{error}</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flat-section">
        <p className="hand-text text-lg" style={{ color: 'var(--color-ink-light)' }}>
          Loading your history…
        </p>
      </div>
    );
  }

  const { jobs, total } = data;
  const pageCount = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="flat-section">
      <h2 className="hand-text text-3xl mb-1" style={{ color: 'var(--color-ink)' }}>
        Your History
      </h2>
      <p className="library-sub">
        {total} {total === 1 ? 'take' : 'takes'} recorded so far ♪
      </p>

      {jobs.length === 0 ? (
        <p className="hand-text text-lg" style={{ color: 'var(--color-ink-light)' }}>
          No takes yet — pick a practice and record your first one.
        </p>
      ) : (
        <div className="dashboard-list">
          {jobs.map((job, idx) => (
            <Link
              key={job.id}
              to={`/results/${job.id}`}
              className="dashboard-item fade-in-up"
              style={{ animationDelay: `${idx * 0.06}s` }}
            >
              <div className="dashboard-item-info">
                <span><strong>{job.practice_title || 'Practice'}</strong></span>
                <span className="library-meta">
                  {new Date(job.created_at).toLocaleString()}
                </span>
              </div>
              <div className="history-item-meta">
                <span className="meta-tag">{job.mode}</span>
                <span className="meta-tag">{job.status}</span>
                {job.score != null && (
                  <span className="dashboard-item-score">{Math.round(job.score)}</span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}

      {pageCount > 1 && (
        <div className="results-actions">
          <button onClick={() => setPage((p) => p - 1)} disabled={page === 0}>
            Previous
          </button>
          <span className="library-meta">Page {page + 1} of {pageCount}</span>
          <button onClick={() => setPage((p) => p + 1)} disabled={page + 1 >= pageCount}>
            Next
          </button>
        </div>
      )}
    </div>
  );
}
