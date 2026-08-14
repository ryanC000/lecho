import { useEffect, useState } from 'react';
import { Link, useLoaderData } from 'react-router-dom';
import { LEVELS, LEVEL_COLORS } from '../constants/levels';
import LevelFilterInk from '../components/LevelFilterInk';
import { SketchPanel } from '../components/core/SketchPanel';
import { SketchButton } from '../components/core/SketchButton';
import AccuracyRing from '../components/AccuracyRing';
import { apiFetch } from '../api/client';
import { isLoggedIn } from '../api/auth';
import { relativeTime } from '../utils/time';

// Score at/above which a clip counts as "mastered" for the counters below.
const MASTERY_THRESHOLD = 70;
// Bounds client-side per-clip aggregation until a backend summary endpoint
// exists (see .scratch/dashboard-redesign/issues/01).
const RECENT_JOBS_LIMIT = 100;
const WEEK_DAYS = 7;
// Tallest bar, leaving the column room for its value label and weekday.
const BAR_MAX_PX = 110;

/** The trailing week as local day buckets, oldest first, each holding the
 * minutes recorded that day. Takes rejected before storage have no duration. */
function weeklyMinutes(takes) {
  const days = [];
  for (let i = WEEK_DAYS - 1; i >= 0; i--) {
    const day = new Date();
    day.setDate(day.getDate() - i);
    day.setHours(0, 0, 0, 0);
    days.push({
      key: day.getTime(),
      label: day.toLocaleDateString(undefined, { weekday: 'narrow' }),
      seconds: 0,
    });
  }
  const byDay = new Map(days.map((day) => [day.key, day]));
  for (const take of takes) {
    if (take.duration_seconds == null) continue;
    const day = new Date(take.created_at);
    day.setHours(0, 0, 0, 0);
    const bucket = byDay.get(day.getTime());
    if (bucket) bucket.seconds += take.duration_seconds;
  }
  return days.map((day) => ({ ...day, minutes: Math.round(day.seconds / 60) }));
}

function shadowedMinutes(takes) {
  const seconds = takes
    .filter((take) => take.mode === 'shadow' && take.duration_seconds != null)
    .reduce((total, take) => total + take.duration_seconds, 0);
  return Math.round(seconds / 60);
}

function scoreColor(score) {
  if (score >= 75) return 'var(--color-accent-sage)';
  if (score >= 50) return 'var(--color-accent-amber)';
  return 'var(--color-accent-warm)';
}

function LastTakePanel({ lastTake, signedOut }) {
  return (
    <SketchPanel>
      <div className="last-take-greeting">Bienvenue</div>
      {lastTake ? (
        <>
          <div className="last-take-eyebrow">your last take</div>
          <div className="last-take-title">
            {lastTake.practice_title || 'Practice'}{' '}
            <span className="last-take-time">({relativeTime(lastTake.created_at)})</span>
          </div>
          <div className="last-take-ring-row">
            <AccuracyRing score={lastTake.score} size={168} strokeWidth={12} />
          </div>
        </>
      ) : (
        <p className="last-take-empty">
          {signedOut ? 'Log in to see your last take here.' : 'No takes yet — pick a clip below and begin.'}
        </p>
      )}
    </SketchPanel>
  );
}

function StatNotes({ ready, clipsOpen, clipsMastered, shadowMinutes }) {
  return (
    <div className="stat-notes">
      <div className="stat-note">
        <div className="stat-note-value">{ready ? clipsOpen : '—'}</div>
        <div className="stat-note-label">clips open</div>
      </div>
      <div className="stat-note">
        <div className="stat-note-value">{ready ? shadowMinutes : '—'}</div>
        <div className="stat-note-label">min shadowed</div>
      </div>
      <div className="stat-note">
        <div className="stat-note-value">{ready ? clipsMastered : '—'}</div>
        <div className="stat-note-label">clips mastered</div>
      </div>
    </div>
  );
}

function PerformanceRow({ name, score }) {
  return (
    <div>
      <div className="performance-row-head">
        <span className="performance-row-name">{name}</span>
        {score != null && (
          <span className="performance-row-value" style={{ color: scoreColor(score) }}>
            {Math.round(score)}
          </span>
        )}
      </div>
      <div className="performance-bar-track">
        <div className="performance-bar-fill" style={{ width: `${score ?? 0}%`, background: scoreColor(score ?? 0) }} />
      </div>
    </div>
  );
}

function PerformancePanel({ detail, signedOut }) {
  return (
    <SketchPanel label="your performance">
      {detail ? (
        <div className="performance-rows">
          <PerformanceRow name="Pitch contour" score={detail.pitch_score} />
          <PerformanceRow name="Rhythm & timing" score={detail.timing_score} />
          <PerformanceRow name="Energy" score={detail.energy_score} />
        </div>
      ) : (
        <p className="last-take-empty">
          {signedOut ? 'Log in to see your performance breakdown.' : 'Nothing scored yet.'}
        </p>
      )}
    </SketchPanel>
  );
}

function ContinueClipCard({ practice, score, idx }) {
  return (
    <Link
      to={`/practice/${practice.id}`}
      viewTransition
      className="continue-clip-card fade-in-up"
      style={{ animationDelay: `${idx * 0.06}s` }}
    >
      <span
        className="level-badge"
        style={{ backgroundColor: LEVEL_COLORS[practice.level], viewTransitionName: `level-${practice.id}` }}
      >
        {practice.level}
      </span>
      <div className="continue-clip-title" style={{ viewTransitionName: `title-${practice.id}` }}>
        {practice.title}
      </div>
      <div className="continue-clip-meta">
        <span className="meta-tag" style={{ viewTransitionName: `length-${practice.id}` }}>
          {practice.length}
        </span>
      </div>
      {score != null ? (
        <>
          <div className="continue-clip-score-row">
            <span className="continue-clip-score">
              {Math.round(score)}<span className="continue-clip-score-max">/100</span>
            </span>
          </div>
          <div className="continue-clip-bar-track">
            <div className="continue-clip-bar-fill" style={{ width: `${score}%`, background: scoreColor(score) }} />
          </div>
        </>
      ) : (
        <div className="continue-clip-unattempted">Not started yet</div>
      )}
    </Link>
  );
}

function ContinueShadowingPanel({ activeLevel, filtered, latestScoreByPractice }) {
  return (
    <div className="continue-panel">
      <div className="continue-panel-header">
        <div className="continue-panel-title">Continue shadowing</div>
        <Link to="/library" className="continue-panel-link">Full library</Link>
      </div>
      <div className="continue-panel-grid" key={activeLevel}>
        {filtered.map((practice, idx) => (
          <ContinueClipCard
            key={practice.id}
            practice={practice}
            score={latestScoreByPractice.get(practice.id)}
            idx={idx}
          />
        ))}
      </div>
      {filtered.length === 0 && (
        <div className="continue-panel-empty">Nothing open at this level yet — the full library has more.</div>
      )}
    </div>
  );
}

function WeekChart({ days }) {
  const peak = Math.max(...days.map((day) => day.minutes));
  return (
    <div className="week-chart">
      {days.map((day) => {
        const isPeak = peak > 0 && day.minutes === peak;
        return (
          <div className="week-bar-col" key={day.key}>
            <div
              className={`week-bar${isPeak ? ' is-peak' : ''}`}
              style={{ height: `${peak > 0 ? Math.max((day.minutes / peak) * BAR_MAX_PX, 3) : 3}px` }}
            >
              {day.minutes > 0 && <span className="week-bar-value">{day.minutes}</span>}
            </div>
            <div className={`week-bar-day${isPeak ? ' is-peak' : ''}`}>{day.label}</div>
          </div>
        );
      })}
    </div>
  );
}

function BottomRow({ recentTakes, weekDays, signedOut }) {
  return (
    <div className="dashboard-bottom-row">
      <SketchPanel label="minutes this week">
        {signedOut ? (
          <p className="last-take-empty">Log in to see your minutes.</p>
        ) : (
          <WeekChart days={weekDays} />
        )}
      </SketchPanel>

      <SketchPanel label="recent takes">
        {recentTakes.length > 0 ? (
          <div className="recent-takes-list">
            {recentTakes.map((job) => (
              <div className="recent-take-row" key={job.id}>
                <div className="recent-take-info">
                  <div className="recent-take-title">{job.practice_title || 'Practice'}</div>
                  <div className="recent-take-meta">{job.mode} · {relativeTime(job.created_at)}</div>
                </div>
                <span className="recent-take-score" style={{ color: scoreColor(job.score) }}>
                  {Math.round(job.score)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="recent-takes-empty">
            {signedOut ? 'Log in to see your recent takes.' : 'No takes yet.'}
          </p>
        )}
      </SketchPanel>
    </div>
  );
}

function NewClipsBanner() {
  return (
    <div className="new-clips-banner">
      <div>
        <div className="new-clips-banner-heading">Ready for a fresh clip?</div>
        <div className="new-clips-banner-body">New practice clips are added to the library regularly — take a look.</div>
      </div>
      <Link to="/library">
        <SketchButton variant="primary" alt className="new-clips-banner-action">
          <span style={{ whiteSpace: 'nowrap' }}>Browse library</span>
        </SketchButton>
      </Link>
    </div>
  );
}

const LOADING = { status: 'loading', jobs: [], takes: [] };
const SIGNED_OUT = { status: 'signed-out', jobs: [], takes: [] };

/** Owner-scoped job history, same reasoning as History.jsx: fetched here
 * rather than through the route loader, which only ever calls unauthenticated apiGet. */
function useJobHistory() {
  // `jobs` is the scored subset the score-driven panels read; `takes` keeps
  // every row, since minutes practiced counts a take whether or not it scored.
  const [loggedIn, setLoggedIn] = useState(isLoggedIn);
  const [history, setHistory] = useState(LOADING);

  // api/auth dispatches 'lecho-auth-changed' on login/logout; without tracking it
  // the panels keep whatever they showed at mount until the page is reloaded.
  useEffect(() => {
    const sync = () => setLoggedIn(isLoggedIn());
    window.addEventListener('lecho-auth-changed', sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener('lecho-auth-changed', sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  // Reset while rendering, not in an effect: signing in as someone else must
  // not flash the previous session's rows before the refetch lands.
  const [lastLoggedIn, setLastLoggedIn] = useState(loggedIn);
  if (lastLoggedIn !== loggedIn) {
    setLastLoggedIn(loggedIn);
    setHistory(LOADING);
  }

  useEffect(() => {
    if (!loggedIn) return; // the signed-out payload is returned below, not stored
    let cancelled = false;
    apiFetch(`/jobs?limit=${RECENT_JOBS_LIMIT}`)
      .then((res) => res.json())
      .then((body) => {
        if (cancelled) return;
        setHistory({ status: 'ready', jobs: body.jobs.filter((j) => j.score != null), takes: body.jobs });
      })
      .catch(() => { if (!cancelled) setHistory({ status: 'error', jobs: [], takes: [] }); });
    return () => { cancelled = true; };
  }, [loggedIn]);

  return loggedIn ? history : SIGNED_OUT;
}

/** Dimension scores aren't on the job-list endpoint, only the per-job detail one. */
function useLastTakeDetail(jobId) {
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    apiFetch(`/jobs/${jobId}`)
      .then((res) => res.json())
      .then((body) => { if (!cancelled) setDetail(body); })
      .catch(() => { if (!cancelled) setDetail(null); });
    return () => { cancelled = true; };
  }, [jobId]);

  // Derived, not cleared in an effect: logging out drops the last take, and the
  // panel must not go on showing its scores.
  return jobId ? detail : null;
}

export default function Dashboard() {
  const practices = useLoaderData();
  const [activeLevel, setActiveLevel] = useState('All');
  const jobsState = useJobHistory();
  const jobs = jobsState.jobs;
  const lastTake = jobs[0] || null;
  const lastTakeDetail = useLastTakeDetail(lastTake?.id);
  const signedOut = jobsState.status === 'signed-out';

  // Latest score per practice — jobs are newest-first, so the first hit per id wins.
  const latestScoreByPractice = new Map();
  for (const job of jobs) {
    if (job.practice_id != null && !latestScoreByPractice.has(job.practice_id)) {
      latestScoreByPractice.set(job.practice_id, job.score);
    }
  }
  const clipsMastered = [...latestScoreByPractice.values()].filter((s) => s >= MASTERY_THRESHOLD).length;
  const clipsOpen = latestScoreByPractice.size - clipsMastered;
  const weekDays = weeklyMinutes(jobsState.takes);

  const filtered = activeLevel === 'All'
    ? practices
    : practices.filter((p) => p.level === activeLevel);

  return (
    <div className="dashboard-grid">
      <div className="dashboard-rail">
        <LastTakePanel lastTake={lastTake} signedOut={signedOut} />
        <StatNotes
          ready={jobsState.status === 'ready'}
          clipsOpen={clipsOpen}
          clipsMastered={clipsMastered}
          shadowMinutes={shadowedMinutes(jobsState.takes)}
        />
        <PerformancePanel detail={lastTakeDetail} signedOut={signedOut} />
      </div>

      <div className="dashboard-main">
        <LevelFilterInk levels={LEVELS} activeLevel={activeLevel} onChange={setActiveLevel} />
        <ContinueShadowingPanel activeLevel={activeLevel} filtered={filtered} latestScoreByPractice={latestScoreByPractice} />
        <BottomRow recentTakes={jobs.slice(0, 4)} weekDays={weekDays} signedOut={signedOut} />
        <NewClipsBanner />
      </div>
    </div>
  );
}
