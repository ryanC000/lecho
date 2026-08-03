"""Tunable constants for the prosody scorer.

One place for every knob the calibration harness (tools/calibrate.py) adjusts
and every threshold the pipeline reads, so tuning never means hunting through
function bodies. Graduation history for these values lives in docs/adr/.
"""
# --- Tunable constants -------------------------------------------------
# All named here (not buried in function bodies) so the scoring-calibration
# harness (worker_plan.md §5) has one place to adjust when real recordings
# are available to tune against.

FRAME_HOP_S = 0.01          # 10ms frame grid shared by F0 and RMS
TARGET_SR = 16000           # standard speech-processing rate; also cheap
PITCH_FLOOR_HZ = 75.0       # speech F0 range (worker_plan.md §9 open question, resolved here)
PITCH_CEILING_HZ = 500.0
RMS_WINDOW_S = 0.025        # ~25ms RMS window, centered on each F0 frame time

# Graduated 2026-07-13 (ADR 0003, calibrate.py --tune on the full corpus):
# timing-led because the content is flat-pitch French — rhythm, not melody,
# carries the discrimination signal there (pitch RMSE actively rewards
# flatness against a flat reference, so it cannot lead). These three weight the
# PROSODY sub-score (they sum to 1.0); content blends in on top at CONTENT_WEIGHT.
PITCH_WEIGHT = 0.20
TIMING_WEIGHT = 0.60
ENERGY_WEIGHT = 0.20

# Content axis (2026-07-28): a pronunciation/intelligibility score from the STT
# gate's word-error rate against the practice transcript. It measures *what* was
# said (did you pronounce the line clearly?), orthogonal to the prosody axes'
# *how*. Blended on top of the prosody sub-score: overall = (1-CW)*prosody +
# CW*content. Placeholder weight — WER is a blunt, noisy signal (good at catching
# mumbled/wrong-word takes, poor at fine grading), so it earns a modest share
# until graduated on a larger set. When the STT gate can't run (no transcript /
# infra failure) content is None and the overall is prosody-only.
CONTENT_WEIGHT = 0.15

DTW_ENERGY_LAMBDA = 1.0     # weight of |Δrms_z| in the joint DTW frame cost (PRD 8.6.3)
# Path regularization (dsp-2). Without it the timing score is unusable:
# on gently-varying contours many paths cost within pitch-tracker noise
# (~0.02 st) of each other, so the "optimal" path zig-zags randomly and the
# slope reads noise as rhythm error.
# - STEP_PENALTY: extra cost per non-diagonal step. Kills gratuitous
#   insert/delete zig-zags (noise-scale payoff) while leaving genuine warps
#   intact — following a real 2x syllable stretch pays semitone-scale costs,
#   10-100x larger than the penalty it incurs.
# - DIAG_PULL: tiny attraction toward the scaled diagonal so the mandatory
#   |n-m| insertions spread evenly through flat-cost regions instead of
#   clumping wherever the backtracker happens to walk.
#   Values swept empirically (see master_implementation_plan.md appendix, Phase 1.5): larger
#   STEP_PENALTY (0.05+) makes the path under-warp genuine 2x syllable
#   stretches on gently-sloped contours; 0.02 keeps real warps sharp while
#   still suppressing noise zig-zag.
DTW_STEP_PENALTY = 0.02
DTW_DIAG_PULL = 0.002

MAX_LENGTH_RATIO = 3.0      # PRD §6 abort: longer/shorter trimmed duration
SAKOE_CHIBA_BAND_FRAC = 0.15  # DTW band width as a fraction of the longer sequence
SILENCE_RMS_FRAC = 0.1      # frames below this fraction of peak RMS are "silence"

# Graduated 2026-07-13 (ADR 0003 gates: every emulation >= 70, every margin
# vs the entry's bad take >= 3 — measured achievable values, see the ADR).
# Larger K => score falls off more slowly with distance.
SCORE_K_PITCH_SEMITONES = 8.0
SCORE_K_ENERGY_Z = 3.0
SCORE_K_TIMING = 4.0        # timing: rmse of log2(tempo-normalized path slope)

# Window over which the local warping-path slope is measured for SCORING.
# Must exceed the typical vertical/horizontal run length of a real-speech DTW
# path: at 0.15 runs longer than the window drove the slope to the 0.05 clamp
# on 8-10% of frames, inflating timing RMSE to ~1.9 on every take regardless
# of quality (2026-07-13 corpus diagnostic). Segment TAGGING keeps its own
# shorter window below: a 0.30 window dilutes a genuine 0.25s syllable
# stretch below the SLOPE_STRETCH_RATIO threshold (test_dsp2 test 4), and a
# tag must localize the error while the score only aggregates it.
SLOPE_WINDOW_S = 0.30
SLOPE_TAG_WINDOW_S = 0.15   # segment-tagging slope window (SYLLABLE_STRETCH)
SLOPE_STRETCH_RATIO = 1.5   # |log2(slope)| beyond log2(this) tags SYLLABLE_STRETCH
PAUSE_MIN_S = 0.15          # minimum silent run to count as a pause (PRD 8.6.3)

SEGMENT_PITCH_THRESHOLD_SEMITONES = 2.0
SEGMENT_ENERGY_THRESHOLD_Z = 1.0
SEGMENT_MIN_FRAMES = 3

# Shadow-mode bleed gate (PRD 8.7 / Edge Case 3). A learner *imitating* the
# clip correlates weakly with it in the raw waveform domain (different voice,
# different phase); actual playback leaking into the mic correlates strongly.
# Threshold is a placeholder until calibration (Task 1.2). Max lag covers the
# playback-start offset plus output latency in a shadow take.
NCC_BLEED_THRESHOLD = 0.5
BLEED_MAX_LAG_S = 1.5

# Ambient-noise pipeline (PRD §6.1). Applied to the USER clip only, from the
# orchestrator — see dsp/noise.py for why it stays out of features_for.
BAND_LOW_HZ = 80.0          # below: room rumble, mic handling, mains hum
BAND_HIGH_HZ = 4000.0       # above: hiss; French prosody carries nothing up there
BANDPASS_ORDER = 4          # 4th-order Butterworth, zero-phase (sosfiltfilt)
NOISE_PROFILE_S = 0.3       # lead-in taken as the ambient-noise profile
# How far the body of the clip must sit above the lead-in for that lead-in to
# count as ambient rather than speech. Below this, spectral subtraction would
# be removing the user's own voice. Measured on synthetic takes (2026-08-03):
# a clip starting mid-speech reads ~0.17 dB, one with a genuine quiet lead-in
# reads 11-27 dB, so this sits conservatively in the gap. Placeholder until it
# graduates on real noisy recordings.
MIN_PROFILE_SNR_DB = 6.0
