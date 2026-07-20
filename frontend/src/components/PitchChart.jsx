import React from 'react';

/**
 * Hand-rolled SVG pitch-overlay chart (no chart library) for a scored job.
 *
 * Overlays the native and user pitch contours in *semitones relative to each
 * speaker's own median* (the archive's per-clip-normalized tracks), so two
 * voices in different registers land on the same 0 baseline and the intonation
 * SHAPE can be compared directly. User-line runs where the absolute semitone
 * gap from the native reaches DEVIATION_SEMITONES render in the warning color.
 *
 * Continuity: a raw voiced mask fragments the contour at every unvoiced
 * consonant (p/t/k/s/f — sub-200ms F0 dropouts that aren't real pitch resets).
 * We bridge non-drawable gaps up to MAX_BRIDGE_S so the line reads as one
 * contour through a word, but keep genuine pauses (longer silences) as real
 * breaks — we never draw a pitch line across a pause the learner actually took.
 *
 * A handful of frames are octave-tracking errors (F0 estimated at 2–4× the true
 * pitch → +12…+24 st from the median); left in, they blow up the y-domain and
 * squash the real contours into thin bands. We exclude frames more than an
 * octave from the median from the drawn lines (they break like an unvoiced gap)
 * so the axis reflects real speech, whose excursions stay well inside an octave.
 *
 * Props:
 *   coordinates — the /jobs/{id}/coordinates archive (fixed worker contract).
 *   words       — optional [{word, start, end}] from the practice alignment;
 *                 x-axis labels degrade gracefully to nothing when absent.
 *   segments    — the job's feedback segments, reused for the screen-reader
 *                 summary of flagged regions.
 */

// Same constant the backend uses to flag pitch-deviation segments
// (dsp.SEGMENT_PITCH_THRESHOLD_SEMITONES). Kept in sync by hand.
const DEVIATION_SEMITONES = 2.0;

// Non-drawable gaps at or below this length are bridged (unvoiced consonants /
// short stops); longer ones are genuine pauses and stay real breaks.
const MAX_BRIDGE_S = 0.2;

const VB_W = 1000;
const VB_H = 320;
const PAD = { left: 12, right: 12, top: 16, bottom: 40 };

// Frames more than an octave from the speaker's median (the tracks are
// normalized so the median is 0 st) are treated as F0 octave-tracking errors
// and excluded from the drawn lines and the y-domain. Real speech excursions in
// one utterance stay well inside an octave; ×2–4 tracking errors land at +12 st
// and up, so this cleanly separates them without touching genuine pitch peaks.
const OCTAVE_ST = 12;
const withinOctave = (v) => Math.abs(v) <= OCTAVE_ST;

/** min/max of an array via reduce (avoids Math.min(...spread) stack limits on
 *  the ~1500-point archives). Returns null for an empty array. */
function extent(values) {
  if (values.length === 0) return null;
  let lo = values[0];
  let hi = values[0];
  for (const v of values) {
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  return [lo, hi];
}

/** Split a contour into drawn polylines, tagging each frame's warn state.
 *  Returns a list of { warn, points: [[x,y], ...] }. The line breaks only when
 *  a run of non-drawable frames exceeds maxGap (a genuine pause) — shorter gaps
 *  are bridged by a straight segment to the next drawable point. A warn-state
 *  change also splits, seeding the next run with the previous point so the
 *  colored segments stay visually connected. */
function buildRuns(frames, maxGap) {
  const runs = [];
  let current = null;
  let gap = 0; // consecutive non-drawable frames since the last drawn point
  for (const f of frames) {
    if (!f.drawable) {
      gap += 1;
      continue;
    }
    if (current && gap > maxGap) current = null; // pause → real break
    if (current && current.warn !== f.warn) {
      // Color change: start a new run seeded with the previous point so the
      // segments stay connected.
      const prev = current.points[current.points.length - 1];
      current = { warn: f.warn, points: [prev] };
      runs.push(current);
    } else if (!current) {
      current = { warn: f.warn, points: [] };
      runs.push(current);
    }
    current.points.push([f.x, f.y]);
    gap = 0;
  }
  return runs;
}

const toPoints = (pts) => pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');

export default function PitchChart({ coordinates, words, segments = [] }) {
  const { times, native_semitone, user_semitone_aligned, voiced_masks } = coordinates;

  const nativeVoiced = voiced_masks.native;
  const userVoiced = voiced_masks.user_aligned;

  // y-domain over the within-octave voiced semitone frames of both contours, so
  // octave-error outliers neither squash the axis nor get drawn.
  const keptValues = [];
  for (let i = 0; i < times.length; i++) {
    if (nativeVoiced[i] && withinOctave(native_semitone[i])) keptValues.push(native_semitone[i]);
    if (userVoiced[i] && withinOctave(user_semitone_aligned[i])) keptValues.push(user_semitone_aligned[i]);
  }
  let [loBound, hiBound] = extent(keptValues) || [-1, 1];    // nothing kept → flat guard below
  if (hiBound === loBound) { loBound -= 1; hiBound += 1; }   // flat-contour guard
  const pad = (hiBound - loBound) * 0.08;
  const yMin = loBound - pad;
  const yMax = hiBound + pad;

  const t0 = times[0];
  const t1 = times[times.length - 1];
  const tSpan = t1 - t0 || 1;

  const plotW = VB_W - PAD.left - PAD.right;
  const plotH = VB_H - PAD.top - PAD.bottom;
  const xScale = (t) => PAD.left + ((t - t0) / tSpan) * plotW;
  const yScale = (st) => PAD.top + (1 - (st - yMin) / (yMax - yMin)) * plotH;

  // A frame is drawable only if voiced AND within an octave — an out-of-range
  // octave error is skipped like an unvoiced gap.
  const nativeFrames = times.map((t, i) => ({
    x: xScale(t),
    y: yScale(native_semitone[i]),
    drawable: nativeVoiced[i] && withinOctave(native_semitone[i]),
    warn: false,
  }));
  const userFrames = times.map((t, i) => ({
    x: xScale(t),
    y: yScale(user_semitone_aligned[i]),
    drawable: userVoiced[i] && withinOctave(user_semitone_aligned[i]),
    // Deviation coloring is only meaningful where both contours are voiced.
    warn: nativeVoiced[i] && userVoiced[i] &&
      Math.abs(native_semitone[i] - user_semitone_aligned[i]) >= DEVIATION_SEMITONES,
  }));

  // Bridge gaps up to MAX_BRIDGE_S, measured in frames off the native hop.
  const hop = times.length > 1 ? times[1] - times[0] : 0.01;
  const maxGap = Math.max(1, Math.round(MAX_BRIDGE_S / hop));
  const nativeRuns = buildRuns(nativeFrames, maxGap);
  const userRuns = buildRuns(userFrames, maxGap);
  const zeroY = yMin < 0 && yMax > 0 ? yScale(0) : null;

  return (
    <div className="pitch-chart">
      <svg
        className="pitch-chart-svg"
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Pitch overlay chart comparing your intonation shape to the native speaker's over time, in semitones relative to each speaker's median."
      >
        {/* Median baseline (0 semitones) — the shared reference both contours
            are normalized against. */}
        {zeroY != null && (
          <line
            x1={PAD.left}
            y1={zeroY}
            x2={VB_W - PAD.right}
            y2={zeroY}
            stroke="var(--color-cream-border)"
            strokeWidth="1.5"
            strokeDasharray="6 5"
          />
        )}
        {/* Native contour — neutral ink */}
        {nativeRuns.map((run, i) => (
          <polyline
            key={`n${i}`}
            className="pitch-line-native"
            fill="none"
            stroke="var(--color-ink-light)"
            strokeWidth="3"
            points={toPoints(run.points)}
          />
        ))}
        {/* User contour — accent, warm where the pitch gap is large */}
        {userRuns.map((run, i) => (
          <polyline
            key={`u${i}`}
            className={run.warn ? 'pitch-line-user-warn' : 'pitch-line-user'}
            fill="none"
            stroke={run.warn ? 'var(--color-accent-warm)' : 'var(--color-accent-violet)'}
            strokeWidth="3"
            points={toPoints(run.points)}
          />
        ))}
        {/* Word labels from the practice alignment (absent → no labels) */}
        {words && words.map((w, i) => {
          const cx = xScale((w.start + w.end) / 2);
          if (cx < PAD.left || cx > VB_W - PAD.right) return null;
          return (
            <text
              key={`w${i}`}
              className="pitch-word-label"
              x={cx}
              y={VB_H - 12}
              textAnchor="middle"
              fill="var(--color-ink-light)"
              fontSize="16"
            >
              {w.word}
            </text>
          );
        })}
      </svg>

      <div className="pitch-chart-legend" aria-hidden="true">
        <span><span className="swatch swatch-native" /> Native</span>
        <span><span className="swatch swatch-user" /> You</span>
        <span><span className="swatch swatch-warn" /> Off pitch</span>
      </div>

      {/* Screen-reader summary of flagged regions (reuses segment data). */}
      <ul className="sr-only">
        {segments.length === 0
          ? <li>No specific issues flagged for this recording.</li>
          : segments.map((seg, i) => (
              <li key={i}>
                From {seg.timestamp_start}s to {seg.timestamp_end}s:{' '}
                {(seg.feedback_tag || '').replace(/_/g, ' ')}. {seg.explanation}
              </li>
            ))}
      </ul>
    </div>
  );
}
