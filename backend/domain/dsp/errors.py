"""Error hierarchy the worker orchestrator maps to a FAILED job."""


class DspError(Exception):
    """Base class for errors the worker orchestrator should map to FAILED."""


class NoSpeechDetectedError(DspError):
    """Raised when a clip has no voiced frames after silence trimming."""


class BleedDetectedError(DspError):
    """Raised (by the orchestrator) when the native clip's playback is
    detected in a shadow-mode user recording."""


class LengthRatioError(DspError):
    """Raised when trimmed clip lengths differ by more than MAX_LENGTH_RATIO."""

