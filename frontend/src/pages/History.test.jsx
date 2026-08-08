import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import History from './History';
import { apiFetch } from '../utils/auth';

vi.mock('../utils/auth', () => ({ apiFetch: vi.fn() }));

const jsonResponse = (data) => ({ json: async () => data });

const row = (id, overrides = {}) => ({
  id,
  practice_id: 7,
  practice_title: 'Au marché',
  status: 'SUCCESS',
  score: 88.4,
  mode: 'solo',
  created_at: '2026-01-01T12:00:00',
  ...overrides,
});

const renderHistory = () =>
  render(
    <MemoryRouter>
      <History />
    </MemoryRouter>
  );

beforeEach(() => {
  vi.clearAllMocks();
});

describe('History', () => {
  it('renders each job as a row linking to its results page, whatever the status', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse({
        total: 2,
        jobs: [
          row('job-2', { status: 'FAILED', score: null, mode: 'shadow' }),
          row('job-1'),
        ],
      })
    );

    renderHistory();

    expect(apiFetch).toHaveBeenCalledWith('/jobs?limit=20&offset=0');
    const links = await screen.findAllByRole('link');
    expect(links.map((a) => a.getAttribute('href'))).toEqual([
      '/results/job-2',
      '/results/job-1',
    ]);
    // A FAILED job still gets a row (Results renders any status), with no score.
    expect(screen.getByText('FAILED')).toBeInTheDocument();
    expect(screen.getByText('shadow')).toBeInTheDocument();
    expect(screen.getByText('88')).toBeInTheDocument();
  });

  it('pages forward and back through the history', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ total: 25, jobs: [row('job-1')] }));

    renderHistory();

    const next = await screen.findByText('Next');
    expect(screen.getByText('Previous')).toBeDisabled();

    fireEvent.click(next);
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith('/jobs?limit=20&offset=20')
    );
    expect(await screen.findByText('Next')).toBeDisabled();

    fireEvent.click(screen.getByText('Previous'));
    await waitFor(() =>
      expect(apiFetch).toHaveBeenLastCalledWith('/jobs?limit=20&offset=0')
    );
  });

  it('shows an empty state when there are no takes yet', async () => {
    apiFetch.mockResolvedValue(jsonResponse({ total: 0, jobs: [] }));

    renderHistory();

    expect(await screen.findByText(/No takes yet/)).toBeInTheDocument();
    expect(screen.queryByText('Next')).not.toBeInTheDocument();
  });

  it('asks a logged-out visitor to log in', async () => {
    apiFetch.mockRejectedValue(Object.assign(new Error('Not authenticated'), { status: 401 }));

    renderHistory();

    expect(await screen.findByText(/log in to see your history/i)).toBeInTheDocument();
  });
});
