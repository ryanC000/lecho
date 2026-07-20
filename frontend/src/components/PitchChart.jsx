import React from 'react';

/**
 * Hand-rolled SVG pitch-overlay chart (no chart library) for a scored job.
 *
 * Overlays the native and user F0 contours (in Hz) against the native
 * timeline. Lines go blank — never interpolated — wherever the respective
 * voiced mask is false. User-line runs where the absolute semitone gap from
 * the native reaches DEVIATION_SEMITONES render in the warning color.
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

const VB_W = 1000;
const VB_H = 320;
const PAD = { left: 12, right: 12, top: 16, bottom: 40 };

/** Split a contour into contiguous voiced runs, tagging each frame's warn
 *  state. Returns a list of { warn, points: [[x,y], ...] } polylines. A run
 *  breaks on an unvoiced frame (blank gap) or a change of warn state; on a
 *  warn-state change the next run is seeded with the previous point so the
 *  colored segments stay visually connected. */
function buildRuns(frames) {
  const runs = [];
  let current = null;
  for (const f of frames) {
    if (!f.voiced) {
      current = null;
      continue;
    }
    if (current && current.warn !== f.warn) {
      const prev = current.points[current.points.length - 1];
      runs.push(current);
      current = { warn: f.warn, points: [prev] };
    }
    if (!current) {
      current = { warn: f.warn, points: [] };
      runs.push(current);
    }
    current.points.push([f.x, f.y]);
  }
  return runs;
}

const toPoints = (pts) => pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');

export default function PitchChart({ coordinates, words, segments = [] }) {
  const {
    times,
    native_f0_hz,
    user_f0_hz_aligned,
    native_semitone,
    user_semitone_aligned,
    voiced_masks,
  } = coordinates;

  const nativeVoiced = voiced_masks.native;
  const userVoiced = voiced_masks.user_aligned;

  // Y-domain over voiced frames of both contours (blank frames don't count).
  let yMin = Infinity;
  let yMax = -Infinity;
  for (let i = 0; i < times.length; i++) {
    if (nativeVoiced[i]) { yMin = Math.min(yMin, native_f0_hz[i]); yMax = Math.max(yMax, native_f0_hz[i]); }
    if (userVoiced[i]) { yMin = Math.min(yMin, user_f0_hz_aligned[i]); yMax = Math.max(yMax, user_f0_hz_aligned[i]); }
  }
  if (!isFinite(yMin)) { yMin = 0; yMax = 1; }        // no voiced frames at all
  if (yMax === yMin) { yMax = yMin + 1; }             // flat contour guard

  const t0 = times[0];
  const t1 = times[times.length - 1];
  const tSpan = t1 - t0 || 1;

  const plotW = VB_W - PAD.left - PAD.right;
  const plotH = VB_H - PAD.top - PAD.bottom;
  const xScale = (t) => PAD.left + ((t - t0) / tSpan) * plotW;
  const yScale = (hz) => PAD.top + (1 - (hz - yMin) / (yMax - yMin)) * plotH;

  const nativeFrames = times.map((t, i) => ({
    x: xScale(t), y: yScale(native_f0_hz[i]), voiced: nativeVoiced[i], warn: false,
  }));
  const userFrames = times.map((t, i) => ({
    x: xScale(t),
    y: yScale(user_f0_hz_aligned[i]),
    voiced: userVoiced[i],
    // Deviation coloring is only meaningful where both contours are voiced.
    warn: nativeVoiced[i] && userVoiced[i] &&
      Math.abs(native_semitone[i] - user_semitone_aligned[i]) >= DEVIATION_SEMITONES,
  }));

  const nativeRuns = buildRuns(nativeFrames);
  const userRuns = buildRuns(userFrames);

  return (
    <div className="pitch-chart">
      <svg
        className="pitch-chart-svg"
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Pitch overlay chart comparing your intonation to the native speaker's over time."
      >
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
