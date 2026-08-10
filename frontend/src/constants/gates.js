// Client mirrors of backend policy constants. Source of truth is the
// backend module named in each comment — update there first.

// Per-mode duration gates (backend/domain/job_gates.py).
export const SOLO_TOLERANCE_FRAC = 0.5;
export const SHADOW_TAIL_S = 1.0;
export const SHADOW_TOLERANCE_S = 0.5;

// Segment pitch-deviation threshold (backend/domain/dsp/constants.py,
// SEGMENT_PITCH_THRESHOLD_SEMITONES).
export const SEGMENT_PITCH_THRESHOLD_SEMITONES = 2.0;
