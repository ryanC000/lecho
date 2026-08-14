import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Dashboard from './Dashboard';
import { apiFetch } from '../api/client';
import { isLoggedIn } from '../api/auth';

vi.mock('../api/client', () => ({ apiFetch: vi.fn() }));
vi.mock('../api/auth', () => ({ isLoggedIn: vi.fn() }));
vi.mock('react-router-dom', async () => ({
  ...(await vi.importActual('react-router-dom')),
  useLoaderData: () => [],
}));

const NOW = new Date('2026-08-14T15:00:00'); // a Friday, local time

// Local-time timestamps: the chart buckets by local day, so a UTC-tagged
// string would land in a different bucket depending on the runner's zone.
const daysAgo = (n, hour = 10) => {
  const d = new Date(NOW);
  d.setDate(d.getDate() - n);
  d.setHours(hour, 0, 0, 0);
  return d.toISOString().slice(0, 19);
};

const take = (id, overrides = {}) => ({
  id,
  practice_id: 7,
  practice_title: 'Au marché',
  status: 'SUCCESS',
  score: 88.4,
  mode: 'solo',
  duration_seconds: 60,
  created_at: daysAgo(0),
  ...overrides,
});

function mockJobs(jobs) {
  apiFetch.mockImplementation((url) =>
    Promise.resolve({
      json: async () => (url.startsWith('/jobs?') ? { total: jobs.length, jobs } : { id: 'job-1' }),
    })
  );
}

const renderDashboard = () => render(<MemoryRouter><Dashboard /></MemoryRouter>);

const barValues = (container) =>
  [...container.querySelectorAll('.week-bar-col')].map(
    (col) => col.querySelector('.week-bar-value')?.textContent ?? ''
  );

const statNote = (label) =>
  screen.getByText(label).parentElement.querySelector('.stat-note-value').textContent;

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(NOW);
  isLoggedIn.mockReturnValue(true);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('Dashboard minutes this week', () => {
  it('sums each day of the trailing week into a bar, marking the busiest day', async () => {
    mockJobs([
      take('job-1', { duration_seconds: 120 }),
      take('job-2', { duration_seconds: 60 }),
      take('job-3', { duration_seconds: 300, created_at: daysAgo(2) }),
    ]);

    const { container } = renderDashboard();

    await waitFor(() => expect(container.querySelectorAll('.week-bar-col')).toHaveLength(7));
    // Oldest day first, today last: 5 min two days ago, 3 min today.
    expect(barValues(container)).toEqual(['', '', '', '', '5', '', '3']);
    const peaks = container.querySelectorAll('.week-bar.is-peak');
    expect(peaks).toHaveLength(1);
    expect(peaks[0].textContent).toBe('5');
  });

  it('leaves older takes and takes that never stored out of the week', async () => {
    mockJobs([
      take('job-1', { duration_seconds: 120 }),
      take('job-2', { duration_seconds: null, status: 'FAILED', score: null }),
      take('job-3', { duration_seconds: 600, created_at: daysAgo(8) }),
    ]);

    const { container } = renderDashboard();

    await waitFor(() => expect(container.querySelectorAll('.week-bar-col')).toHaveLength(7));
    expect(barValues(container)).toEqual(['', '', '', '', '', '', '2']);
  });

  it('shows a sign-in prompt instead of the chart when signed out', async () => {
    isLoggedIn.mockReturnValue(false);

    const { container } = renderDashboard();

    expect(await screen.findByText(/log in to see your minutes/i)).toBeInTheDocument();
    expect(container.querySelector('.week-chart')).toBeNull();
    expect(apiFetch).not.toHaveBeenCalled();
  });
});

describe('Dashboard "min shadowed" stat', () => {
  it('totals shadow-mode minutes across all takes, not just this week', async () => {
    mockJobs([
      take('job-1', { mode: 'solo', duration_seconds: 240 }),
      take('job-2', { mode: 'shadow', duration_seconds: 300, created_at: daysAgo(2) }),
      take('job-3', { mode: 'shadow', duration_seconds: 600, created_at: daysAgo(8) }),
    ]);

    renderDashboard();

    await waitFor(() => expect(statNote('min shadowed')).toBe('15'));
  });

  it('counts nothing when no shadow take has a duration', async () => {
    mockJobs([take('job-1', { mode: 'shadow', duration_seconds: null })]);

    renderDashboard();

    await waitFor(() => expect(statNote('min shadowed')).toBe('0'));
  });

  it('stays a dash until the history loads', async () => {
    isLoggedIn.mockReturnValue(false);

    renderDashboard();

    expect(statNote('min shadowed')).toBe('—');
  });
});
