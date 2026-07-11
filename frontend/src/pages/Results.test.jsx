import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import Results from './Results';
import { apiFetch } from '../utils/auth';

vi.mock('../utils/auth', () => ({ apiFetch: vi.fn() }));

const jsonResponse = (data) => ({ json: async () => data });

function renderResults() {
  return render(
    <MemoryRouter initialEntries={['/results/job-1']}>
      <Routes>
        <Route path="/results/:jobId" element={<Results />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('Results polling', () => {
  it('shows the analyzing state while PENDING, then renders the SUCCESS payload and stops polling', async () => {
    apiFetch
      .mockResolvedValueOnce(jsonResponse({ id: 'job-1', status: 'PENDING' }))
      .mockResolvedValueOnce(
        jsonResponse({
          id: 'job-1',
          status: 'SUCCESS',
          score: 88.5,
          pitch_score: 91.0,
          timing_score: 84.0,
          energy_score: 87.5,
          practice_id: 7,
          transcript: 'bonjour tout le monde',
          segments: [
            {
              timestamp_start: 1.0,
              timestamp_end: 2.0,
              feedback_tag: 'INTONATION_DROP',
              explanation: 'Your pitch fell where the native rises.',
            },
          ],
        })
      );

    renderResults();

    // First poll fires immediately -> PENDING.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText(/Analyzing your recording/)).toBeInTheDocument();
    expect(apiFetch).toHaveBeenCalledWith('/jobs/job-1');

    // Next 2s tick -> SUCCESS payload rendered.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    // TranslationOverlay renders the transcript as per-word tokens.
    expect(screen.getByText('bonjour')).toBeInTheDocument();
    expect(screen.getByText('monde')).toBeInTheDocument();
    expect(screen.getByText('INTONATION DROP')).toBeInTheDocument();
    expect(screen.getByText('Your pitch fell where the native rises.')).toBeInTheDocument();
    expect(screen.getByText('Pitch')).toBeInTheDocument(); // sub-score row

    // Terminal state clears the interval — no further polls.
    const calls = apiFetch.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(apiFetch.mock.calls.length).toBe(calls);
  });

  it('renders a retryable failure with Try Again', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse({
        id: 'job-1',
        status: 'FAILED',
        error_message: 'No speech detected in the recording.',
        practice_id: 7,
        retryable: true,
        segments: [],
      })
    );

    renderResults();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(screen.getByText('No speech detected in the recording.')).toBeInTheDocument();
    expect(screen.getByText('Try Again')).toBeInTheDocument();
  });

  it('hides Try Again when the failure is not retryable', async () => {
    apiFetch.mockResolvedValue(
      jsonResponse({
        id: 'job-1',
        status: 'FAILED',
        error_message: "This practice isn't ready for scoring yet.",
        practice_id: 7,
        retryable: false,
        segments: [],
      })
    );

    renderResults();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(screen.getByText(/isn't ready for scoring/)).toBeInTheDocument();
    expect(screen.queryByText('Try Again')).not.toBeInTheDocument();
  });
});
