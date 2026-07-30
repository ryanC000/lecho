"""What a submitted take must satisfy to be worth scoring (PRD FR-1, 8.7).

Pure policy — no FastAPI, no DB — so the gates are unit-testable on their own
and the API layer just reports what they decide. The frontend mirrors these
numbers in `frontend/src/components/Recorder.jsx` for a fast client-side
rejection; this module is the source of truth.
"""

# --- Ingestion constraints (PRD FR-1) ---
MIN_DURATION_S = 2.0
MAX_DURATION_S = 15.0
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB — a 15s mono 16-bit WAV is well under this
RETENTION_DAYS = 30                   # PRD Section 4 storage lifecycle

# Solo-mode relative duration gate: generous (±50%) because an early/late
# stop press just pads the take with silence, which trim_silence strips
# before scoring and the 3:1 trimmed length-ratio abort still backstops.
# This only rejects takes that can't plausibly be the same utterance.
SOLO_TOLERANCE_FRAC = 0.5

# Shadow-mode duration gate (PRD 8.7): a shadow take runs the native clip's
# length plus a fixed tail, so its expected duration is native + SHADOW_TAIL_S
# within ±SHADOW_TOLERANCE_S (placeholder until calibration, Task 1.2).
SHADOW_TAIL_S = 1.0
SHADOW_TOLERANCE_S = 0.5

ALLOWED_JOB_MODES = {"solo", "shadow"}


def mode_duration_error(mode: str, duration: float, native_duration: float):
    """Per-mode relative duration gate. Returns the user-facing rejection
    message, or None if the duration passes. Applied twice per job: to the
    client-reported duration as a fast-fail, then to the server-derived
    duration as the authoritative check. The absolute 2-15s gate is separate
    (clip_ingest) and identical for both modes.
    """
    if mode == "shadow":
        expected = native_duration + SHADOW_TAIL_S
        if abs(duration - expected) > SHADOW_TOLERANCE_S:
            return (
                f"Shadow recording duration deviates too much from the expected "
                f"length ({expected:.1f}s = native + {SHADOW_TAIL_S:.0f}s tail)."
            )
        return None
    lo = native_duration * (1 - SOLO_TOLERANCE_FRAC)
    hi = native_duration * (1 + SOLO_TOLERANCE_FRAC)
    if duration < lo or duration > hi:
        return "Recording duration deviates too much from native reference."
    return None
