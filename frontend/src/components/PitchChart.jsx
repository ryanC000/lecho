import React from 'react';

/**
 * Hand-rolled SVG pitch-overlay chart (no chart library) for a scored job.
 *
 * Overlays the native and user pitch contours in *semitones relative to each
 * speaker's own median* (the archive's per-clip-normalized tracks), so two
 * voices in different registers land on the same 0 baseline and the intonation
 * SHAPE can be compared directly. A shaded target band of native ±
 * DEVIATION_SEMITONES sits behind the lines so the learner can see the
 * acceptable pitch range at a glance; the user line runs warm wherever it
 * leaves that band (the same threshold the backend uses to flag segments).
 *
 * Continuity: the semitone tracks are already gap-interpolated by the worker,
 * so we draw straight through the sub-200ms F0 dropouts of unvoiced consonants
 * (p/t/k/s/f) that aren't real pitch resets. We break the line only at genuine
 * pauses — when the alignment is present, an unvoiced run that falls in
 * inter-word silence and lasts longer than PAUSE_S; otherwise a frame-count
 * fallback (MAX_BRIDGE_S). We never draw a pitch line across a pause the learner
 * actually took, but a stop *within* a word stays one contour.
 *
 * A median-3 de-spike pass on the drawn geometry removes single-frame F0
 * octave-tracking errors (×2–4 spikes) and frame jitter without flattening
 * genuine 2-frame pitch peaks, and a robust 2–98th-percentile y-domain keeps a
 * stray outlier from squashing the axis. Deviation coloring is computed from the
 * RAW tracks (not the smoothed geometry) so it stays in sync with the backend's
 * segment flags.
 *
 * Props:
 *   coordinates — the /jobs/{id}/coordinates archive (fixed worker contract).
 *   words       — optional [{word, start, end}] from the practice alignment;
 *                 enables word-aware pause breaks and x-axis labels, both of
 *                 which degrade gracefully to a time-threshold / no labels when
 *                 absent.
 *   segments    — the job's feedback segments, reused for the screen-reader
 *                 summary of flagged regions.
 */

// Same constant the backend uses to flag pitch-deviation segments
// (dsp.SEGMENT_PITCH_THRESHOLD_SEMITONES). Kept in sync by hand. Also the
// half-height of the target band.
const DEVIATION_SEMITONES = 2.0;

// Fallback (no alignment): unvoiced runs at or below this length are bridged
// (unvoiced consonants / short stops); longer ones are treated as pauses.
const MAX_BRIDGE_S = 0.2;

// Word-aware: an unvoiced run in inter-word silence longer than this is a real
// pause and breaks the line; anything shorter, or anything inside a word, is
// bridged.
const PAUSE_S = 0.15;

const VB_W = 1000;
const VB_H = 320;
const PAD = { left: 12, right: 12, top: 16, bottom: 40 };

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

/** Linear-interpolated percentile of a *sorted* array (p in [0,100]). */
function percentile(sorted, p) {
  if (sorted.length === 0) return null;
  const idx = (p / 100) * (sorted.length - 1);
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  if (lo === hi) return sorted[lo];
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}

/** Median-3 de-spike: each frame becomes the median of itself and its two
 *  neighbors (window shrinks at the ends). Kills single-frame octave errors and
 *  jitter while preserving genuine 2-frame pitch peaks. */
function median3(arr) {
  const out = new Array(arr.length);
  for (let i = 0; i < arr.length; i++) {
    const a = arr[i];
    const b = i > 0 ? arr[i - 1] : a;
    const c = i < arr.length - 1 ? arr[i + 1] : a;
    out[i] = a + b + c - Math.min(a, b, c) - Math.max(a, b, c); // median of 3
  }
  return out;
}

const wordCoversTime = (words, t) => words.some((w) => t >= w.start && t <= w.end);

/** Split a contour into continuity segments — arrays of drawable frames. The
 *  line breaks only where a run of non-drawable (unvoiced) frames is judged a
 *  real pause by isPause; shorter gaps are bridged (the segment continues,
 *  connecting across them with a straight line to the next drawable frame). */
function segment(frames, isPause) {
  const runs = [];
  let current = null;
  let gap = [];       // consecutive non-drawable frames since the last drawn one
  let prev = null;    // last drawn frame
  for (const f of frames) {
    if (!f.drawable) {
      gap.push(f);
      continue;
    }
    if (current && gap.length && isPause(prev, f, gap)) current = null; // pause → break
    if (!current) {
      current = [];
      runs.push(current);
    }
    current.push(f);
    prev = f;
    gap = [];
  }
  return runs;
}

/** Split one continuity segment into polylines by warn state, seeding each new
 *  run with the previous point so the colored segments stay visually connected. */
function splitByWarn(seg) {
  const parts = [];
  let current = null;
  for (const f of seg) {
    if (current && current.warn !== f.warn) {
      const prev = current.points[current.points.length - 1];
      current = { warn: f.warn, points: [prev] };
      parts.push(current);
    } else if (!current) {
      current = { warn: f.warn, points: [] };
      parts.push(current);
    }
    current.points.push([f.x, f.y]);
  }
  return parts;
}

const toPoints = (pts) => pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');

export default function PitchChart({ coordinates, words, segments = [] }) {
  const { times, native_semitone, user_semitone_aligned, voiced_masks } = coordinates;

  const nativeVoiced = voiced_masks.native;
  const userVoiced = voiced_masks.user_aligned;

  // Smooth only the drawn geometry; warn state below stays on the raw tracks.
  const smNative = median3(native_semitone);
  const smUser = median3(user_semitone_aligned);

  // Robust y-domain over the voiced smoothed frames, including the native ±
  // DEVIATION band edges so the target band is always fully visible. The
  // 2–98th percentile trims residual outliers without deleting any frame.
  const domainValues = [];
  for (let i = 0; i < times.length; i++) {
    if (nativeVoiced[i]) {
      domainValues.push(smNative[i] - DEVIATION_SEMITONES, smNative[i] + DEVIATION_SEMITONES);
    }
    if (userVoiced[i]) domainValues.push(smUser[i]);
  }
  domainValues.sort((a, b) => a - b);
  let loBound = percentile(domainValues, 2);
  let hiBound = percentile(domainValues, 98);
  if (loBound == null) [loBound, hiBound] = [-1, 1];         // nothing voiced → flat guard
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

  const nativeFrames = times.map((t, i) => ({
    x: xScale(t),
    y: yScale(smNative[i]),
    st: smNative[i],
    t,
    drawable: nativeVoiced[i],
    warn: false,
  }));
  const userFrames = times.map((t, i) => ({
    x: xScale(t),
    y: yScale(smUser[i]),
    t,
    drawable: userVoiced[i],
    // Deviation coloring is only meaningful where both contours are voiced, and
    // is measured on the RAW tracks to match the backend's segment flags.
    warn: nativeVoiced[i] && userVoiced[i] &&
      Math.abs(native_semitone[i] - user_semitone_aligned[i]) >= DEVIATION_SEMITONES,
  }));

  // Break at genuine pauses: word-aware when an alignment is present, else a
  // frame-count fallback off the native hop.
  const hop = times.length > 1 ? times[1] - times[0] : 0.01;
  const maxGap = Math.max(1, Math.round(MAX_BRIDGE_S / hop));
  const isPause = words && words.length
    ? (prev, curr, gap) =>
        gap.every((g) => !wordCoversTime(words, g.t)) && curr.t - prev.t > PAUSE_S
    : (prev, curr, gap) => gap.length > maxGap;

  const nativeSegments = segment(nativeFrames, isPause);
  const userRuns = segment(userFrames, isPause).flatMap(splitByWarn);
  const zeroY = yMin < 0 && yMax > 0 ? yScale(0) : null;

  return (
    <div className="pitch-chart">
      <svg
        className="pitch-chart-svg"
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label="Pitch overlay chart comparing your intonation shape to the native speaker's over time, in semitones relative to each speaker's median, with a shaded target band around the native contour."
      >
        {/* Target band — native ± DEVIATION_SEMITONES, drawn first so it sits
            behind the baseline and contours. Breaks at pauses with the line. */}
        {nativeSegments.map((seg, i) => {
          const upper = seg.map((f) => [f.x, yScale(f.st + DEVIATION_SEMITONES)]);
          const lower = seg.map((f) => [f.x, yScale(f.st - DEVIATION_SEMITONES)]);
          return (
            <polygon
              key={`band${i}`}
              className="pitch-target-band"
              points={toPoints(upper.concat(lower.reverse()))}
            />
          );
        })}
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
        {nativeSegments.map((seg, i) => (
          <polyline
            key={`n${i}`}
            className="pitch-line-native"
            fill="none"
            stroke="var(--color-ink-light)"
            strokeWidth="3"
            points={toPoints(seg.map((f) => [f.x, f.y]))}
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
        <span><span className="swatch swatch-band" /> In range</span>
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
