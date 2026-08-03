"""Pure DSP core for prosody scoring (worker_plan.md Part 1.2).

Every function here is stateless: inputs are paths/arrays, outputs are
arrays/scores/dicts. No SQLAlchemy, no `storage.py` calls, no FastAPI. This
is what makes it directly unit-testable with synthetic audio, and what lets
the future SQS worker entrypoint import the exact same module the in-process
orchestrator (`worker/core.py`) uses — the Phase 3 split becomes a transport
swap, not an algorithm rewrite.

Pipeline (see worker_plan.md §4 for the full rationale):
    features_for -> align -> score / make_segments / build_archive

Module map:
    constants  every tunable knob            errors    the DspError hierarchy
    features   load / extract / trim         align     DTW warping path
    scoring    0-100 axis scores             segments  tagged feedback runs
    archive    visualizer JSON               bleed     shadow-mode NCC gate
    noise      user-clip cleanup + SNR (orchestrator-only; not in features_for)

This package re-exports the whole public surface, so callers keep writing
`dsp.features_for(...)`, `dsp.align(...)`, `dsp.TARGET_SR`. The constants
below are the shipped defaults; nothing mutates them at runtime — anything
that needs to vary a tuned value passes it as an argument (`ScoringParams`,
`align(energy_lambda=...)`, `extract_features(pitch_floor_hz=...)`).
"""
from .align import (
    Aligned,
    _apply_path_any,
    _apply_path_mean,
    _dtw_path,
    _path_local_slope,
    align,
)
from .archive import build_archive
from .bleed import detect_bleed
from .constants import *  # noqa: F401,F403 — the shipped tuning defaults
from .errors import (
    BleedDetectedError,
    DspError,
    LengthRatioError,
    NoSpeechDetectedError,
)
from .features import (
    ProsodyFeatures,
    extract_features,
    features_for,
    load_mono_16k,
    trim_silence,
)
from .noise import denoise, denoise_clip
from .scoring import (
    DEFAULT_SCORING,
    ScoringParams,
    blend_content,
    content_score_from_wer,
    score,
)
from .segments import make_segments
