import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import PitchChart from './PitchChart';

// Five frames on the native timeline. The user contour has an unvoiced gap at
// index 2, and a ≥2-semitone deviation across the last two (voiced) frames.
const coordinates = {
  times: [0.0, 0.1, 0.2, 0.3, 0.4],
  native_f0_hz: [200, 210, 220, 215, 205],
  user_f0_hz_aligned: [198, 209, 0, 190, 185],
  native_semitone: [0.0, 0.8, 1.6, 1.2, 0.4],
  user_semitone_aligned: [-0.2, 0.6, 0.0, -3.0, -2.0], // |gap| at idx 3,4 ≥ 2.0
  native_rms: [0.5, 0.6, 0.6, 0.5, 0.4],
  user_rms_aligned: [0.5, 0.6, 0.0, 0.4, 0.3],
  voiced_masks: {
    native: [true, true, true, true, true],
    user_aligned: [true, true, false, true, true],
  },
};

const segments = [
  {
    timestamp_start: 0.3,
    timestamp_end: 0.4,
    feedback_tag: 'INTONATION_DROP',
    explanation: 'Your pitch dips below the native speaker here.',
  },
];

describe('PitchChart', () => {
  it('breaks the user line at the unvoiced gap and colors the deviation', () => {
    const { container } = render(<PitchChart coordinates={coordinates} words={null} segments={segments} />);

    // Chart is present and labeled for assistive tech.
    expect(screen.getByRole('img')).toBeInTheDocument();

    // The unvoiced gap splits the user contour into ≥2 separate polylines.
    const userLines = container.querySelectorAll('.pitch-line-user, .pitch-line-user-warn');
    expect(userLines.length).toBeGreaterThanOrEqual(2);

    // The ≥2-semitone run renders in the warning color as a drawn segment.
    const warnLines = container.querySelectorAll('.pitch-line-user-warn');
    expect(warnLines.length).toBeGreaterThanOrEqual(1);
    expect(warnLines[0].getAttribute('points').trim()).toContain(' '); // ≥2 points
  });

  it('renders word labels when an alignment is provided', () => {
    render(
      <PitchChart
        coordinates={coordinates}
        words={[{ word: 'bonjour', start: 0.0, end: 0.2 }]}
        segments={segments}
      />
    );
    expect(screen.getByText('bonjour')).toBeInTheDocument();
  });

  it('renders without word labels when the alignment is absent', () => {
    render(<PitchChart coordinates={coordinates} words={null} segments={segments} />);
    expect(screen.getByRole('img')).toBeInTheDocument();
    // Screen-reader summary of the flagged region is present.
    expect(screen.getByText(/From 0.3s to 0.4s/)).toBeInTheDocument();
  });
});
