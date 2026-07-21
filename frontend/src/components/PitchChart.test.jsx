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
// Every x drawn across all user polylines (the frames actually rendered).
const userXs = (container) =>
  [...container.querySelectorAll('.pitch-line-user, .pitch-line-user-warn')]
    .flatMap((el) => points(el).map((p) => p[0]));
const hasXnear = (xs, x) => xs.some((v) => Math.abs(v - x) < 1);
// The rendered x of frame index round(t*10) off the (contiguous) native line.
const frameX = (container, t) =>
  points(container.querySelector('.pitch-line-native'))[Math.round(t * 10)][0];

describe('PitchChart', () => {
  it('draws through a short gap, breaks at a long one, and colors the deviation', () => {
    const { container } = render(<PitchChart coordinates={coordinates} words={null} segments={segments} />);

    expect(screen.getByRole('img')).toBeInTheDocument();

    // The native line is fully voiced and contiguous → uniform frame spacing.
    const nativeEl = container.querySelector('.pitch-line-native');
    const frameW = maxDx(nativeEl);

    // No user polyline ever jumps more than ~1 frame: the short (1-frame) gap is
    // drawn *through* its interpolated frame — a continuous curve, not a chord.
    const userLines = [...container.querySelectorAll('.pitch-line-user, .pitch-line-user-warn')];
    expect(Math.max(...userLines.map(maxDx))).toBeLessThan(1.5 * frameW);

    // The short gap's frame (t=0.2) IS drawn; the long gap's frames (t=0.5–0.7)
    // are NOT — proving the 1-frame gap was bridged and the 3-frame gap broke.
    const xs = userXs(container);
    expect(hasXnear(xs, frameX(container, 0.2))).toBe(true);  // short gap bridged (drawn through)
    expect(hasXnear(xs, frameX(container, 0.6))).toBe(false); // long gap is a real break

    // The ≥2-semitone run renders in the warning color as a drawn segment.
    const warnLines = container.querySelectorAll('.pitch-line-user-warn');
    expect(warnLines.length).toBeGreaterThanOrEqual(1);
    expect(warnLines[0].getAttribute('points').trim()).toContain(' '); // ≥2 points
  });

  it('renders a target band that brackets the native contour', () => {
    const { container } = render(<PitchChart coordinates={coordinates} words={null} segments={segments} />);

    // Native is fully voiced → one continuous band polygon.
    const bands = container.querySelectorAll('.pitch-target-band');
    expect(bands.length).toBeGreaterThanOrEqual(1);

    // The band (native ± 2 st) is wider in y than the native line at both edges:
    // its top edge sits above the line's highest point and its bottom below the
    // lowest (y grows downward, so smaller y = higher on screen).
    const ys = (el) => points(el).map((p) => p[1]);
    const bandYs = ys(bands[0]);
    const nativeYs = ys(container.querySelector('.pitch-line-native'));
    expect(Math.min(...bandYs)).toBeLessThan(Math.min(...nativeYs));
    expect(Math.max(...bandYs)).toBeGreaterThan(Math.max(...nativeYs));
  });

  it('draws through a long gap that falls within a single word', () => {
    // With the whole utterance under one word, the 3-frame gap is within-word,
    // so it's bridged — the contour is drawn continuously through the gap's
    // interpolated frames (contrast the words=null case, which breaks there and
    // omits t=0.5–0.7 entirely).
    const words = [{ word: 'liaison', start: 0.0, end: 1.0 }];
    const { container } = render(<PitchChart coordinates={coordinates} words={words} segments={segments} />);

    const frameW = maxDx(container.querySelector('.pitch-line-native'));

    // Every frame across the gap is drawn (no hole) and the line stays continuous.
    const xs = userXs(container);
    expect(hasXnear(xs, frameX(container, 0.5))).toBe(true);
    expect(hasXnear(xs, frameX(container, 0.6))).toBe(true);
    expect(hasXnear(xs, frameX(container, 0.7))).toBe(true);
    const userLines = [...container.querySelectorAll('.pitch-line-user, .pitch-line-user-warn')];
    expect(Math.max(...userLines.map(maxDx))).toBeLessThan(1.5 * frameW);
  });

  it('folds a multi-frame octave error out of the geometry and out of the coloring', () => {
    // A 2-frame +12 st harmonic-locking error that median-3 alone can't remove
    // (both spike frames survive a 3-window median). Octave-unwrap must fold it
    // back so the drawn user contour stays flat instead of leaping an octave —
    // AND the octave-reduced deviation must keep those frames OUT of the warm
    // "off pitch" color, so we never draw a warm segment flat inside the band.
    const octave = {
      times: [0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
      native_semitone: [0, 0, 0, 0, 0, 0],
      user_semitone_aligned: [0, 0, 12, 12, 0, 0],
      voiced_masks: {
        native: [true, true, true, true, true, true],
        user_aligned: [true, true, true, true, true, true],
      },
    };
    const { container } = render(<PitchChart coordinates={octave} words={null} segments={[]} />);

    const userYs = [...container.querySelectorAll('.pitch-line-user, .pitch-line-user-warn')]
      .flatMap((el) => points(el).map((p) => p[1]));
    // The whole user line is essentially flat — the octave spike is gone. (A
    // surviving +12 st spike would throw the two frames far off the others.)
    expect(Math.max(...userYs) - Math.min(...userYs)).toBeLessThan(5);
    // The octave gap is the same pitch class → not painted as off-pitch.
    expect(container.querySelectorAll('.pitch-line-user-warn').length).toBe(0);
  });

  it('re-anchors an octave-offset first frame instead of shifting the whole line', () => {
    // The very first frame is octave-doubled (+12). A naive continuity unwrap
    // would fold every later frame up to match it, riding the whole contour an
    // octave high; the mean re-anchor pulls it back to the true (~0) baseline.
    const badFirst = {
      times: [0.0, 0.1, 0.2, 0.3, 0.4],
      native_semitone: [0, 0, 0, 0, 0],
      user_semitone_aligned: [12, 0, 0, 0, 0],
      voiced_masks: {
        native: [true, true, true, true, true],
        user_aligned: [true, true, true, true, true],
      },
    };
    const { container } = render(<PitchChart coordinates={badFirst} words={null} segments={[]} />);
    const nativeYs = points(container.querySelector('.pitch-line-native')).map((p) => p[1]);
    const userYs = [...container.querySelectorAll('.pitch-line-user, .pitch-line-user-warn')]
      .flatMap((el) => points(el).map((p) => p[1]));
    // The user contour sits on the native baseline (~0), not an octave above it.
    const nativeMid = nativeYs[2];
    expect(Math.max(...userYs.map((y) => Math.abs(y - nativeMid)))).toBeLessThan(5);
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
