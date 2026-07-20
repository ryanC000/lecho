import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import PitchChart from './PitchChart';

// Ten frames at a 0.1s hop (so MAX_BRIDGE_S=0.2 → maxGap=2 frames). The user
// contour has a SHORT gap at index 2 (1 frame → bridged) and a LONG gap at
// indices 5–7 (3 frames → a real break). The native rises to +2.6/+2.8 st over
// indices 3–4 while the user stays near median → a ≥2-semitone deviation there.
// All values stay within an octave, so none are dropped as octave errors.
const coordinates = {
  times: [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
  native_f0_hz: [200, 205, 215, 240, 245, 215, 210, 208, 209, 212],
  user_f0_hz_aligned: [198, 205, 0, 205, 210, 0, 0, 0, 204, 202],
  native_semitone: [0.0, 0.5, 1.0, 2.6, 2.8, 1.0, 0.5, 0.3, 0.4, 0.6],
  user_semitone_aligned: [-0.2, 0.4, 0.0, 0.3, 0.5, 0.0, 0.0, 0.0, 0.2, 0.1],
  native_rms: [0.5, 0.6, 0.6, 0.5, 0.4, 0.5, 0.5, 0.4, 0.5, 0.5],
  user_rms_aligned: [0.5, 0.6, 0.0, 0.4, 0.3, 0.0, 0.0, 0.0, 0.4, 0.4],
  voiced_masks: {
    native: [true, true, true, true, true, true, true, true, true, true],
    user_aligned: [true, true, false, true, true, false, false, false, true, true],
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

// Parse a polyline's "x,y x,y …" into [[x,y],…] and the max jump in x between
// consecutive points (how far the line reaches without a break).
const points = (el) => el.getAttribute('points').trim().split(' ').map((p) => p.split(',').map(Number));
const maxDx = (el) => {
  const pts = points(el);
  let m = 0;
  for (let i = 1; i < pts.length; i++) m = Math.max(m, Math.abs(pts[i][0] - pts[i - 1][0]));
  return m;
};

describe('PitchChart', () => {
  it('bridges a short gap, breaks at a long one, and colors the deviation', () => {
    const { container } = render(<PitchChart coordinates={coordinates} words={null} segments={segments} />);

    expect(screen.getByRole('img')).toBeInTheDocument();

    // The native line is fully voiced and contiguous → uniform frame spacing.
    const nativeEl = container.querySelector('.pitch-line-native');
    const frameW = maxDx(nativeEl);

    // Across all user polylines, the largest within-line reach is ~2 frames
    // (the bridged 1-frame gap) — proving the short gap was bridged but the
    // 3-frame gap was NOT (that one is a real break between separate polylines).
    const userLines = [...container.querySelectorAll('.pitch-line-user, .pitch-line-user-warn')];
    const reach = Math.max(...userLines.map(maxDx));
    expect(reach).toBeGreaterThan(1.5 * frameW); // short gap bridged
    expect(reach).toBeLessThan(3 * frameW);      // long gap left as a break

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
