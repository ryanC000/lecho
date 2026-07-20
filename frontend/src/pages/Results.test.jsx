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
              words: ['tout', 'le'],
            },
          ],
        })
      )
      // The SUCCESS payload triggers the chart's coordinate + alignment fetches;
      // this test doesn't exercise the chart, so let them fail harmlessly.
      .mockRejectedValue(new Error('no chart data in this test'));

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
    // Word-anchored feedback (PRD 8.4): the segment's words are the headline.
    expect(screen.getByText('tout le')).toBeInTheDocument();
    expect(screen.getByText('Your pitch fell where the native rises.')).toBeInTheDocument();
    expect(screen.getByText('Pitch')).toBeInTheDocument(); // sub-score row

    // Terminal state clears the interval — no further polls.
    const calls = apiFetch.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });
    expect(apiFetch.mock.calls.length).toBe(calls);
  });

  it('renders the pitch chart from the coordinate archive, degrading gracefully when alignment 404s', async () => {
    const archive = {
      times: [0.0, 0.1, 0.2, 0.3],
      native_f0_hz: [200, 210, 215, 205],
      user_f0_hz_aligned: [198, 209, 190, 185],
      native_semitone: [0.0, 0.8, 1.2, 0.4],
      user_semitone_aligned: [-0.2, 0.6, -3.0, -2.0],
      native_rms: [0.5, 0.6, 0.5, 0.4],
      user_rms_aligned: [0.5, 0.6, 0.4, 0.3],
      voiced_masks: {
        native: [true, true, true, true],
        user_aligned: [true, true, true, true],
      },
    };
    const alignment404 = Object.assign(new Error('no alignment'), { status: 404 });

    // Path-routed mock: status poll, then the chart's two follow-up fetches.
    apiFetch.mockImplementation((path) => {
      if (path === '/jobs/job-1') {
        return Promise.resolve(
          jsonResponse({
            id: 'job-1',
            status: 'SUCCESS',
            score: 88.5,
            practice_id: 7,
            segments: [
              {
                timestamp_start: 0.2,
                timestamp_end: 0.3,
                feedback_tag: 'INTONATION_DROP',
                explanation: 'Your pitch dips below the native speaker here.',
              },
            ],
          })
        );
      }
      if (path === '/jobs/job-1/coordinates') return Promise.resolve(jsonResponse(archive));
      if (path === '/practices/7/alignment') return Promise.reject(alignment404);
      return Promise.reject(new Error(`unexpected path ${path}`));
    });

    renderResults();
    // Flush the status poll and both follow-up fetches.
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    // Chart rendered despite the alignment 404, with the SR flagged-region list.
    expect(screen.getByRole('img')).toBeInTheDocument();
    expect(screen.getByText(/From 0.2s to 0.3s/)).toBeInTheDocument();
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
