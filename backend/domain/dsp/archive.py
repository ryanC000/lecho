"""JSON archive of the aligned contours, for the pitch-overlay visualizer."""

from .align import Aligned


def build_archive(aligned: Aligned) -> dict:
    """JSON-serializable dict written to storage/analysis/{job_id}.json.

    Stores both Hz (the visualizer shows Hz) and the normalized arrays (for
    deviation coloring), per §4 step 9.
    """
    native = aligned.native
    return {
        "times": native.times.tolist(),
        "native_f0_hz": native.f0_hz.tolist(),
        "user_f0_hz_aligned": aligned.user_f0_hz.tolist(),
        "native_semitone": native.f0_semitone.tolist(),
        "user_semitone_aligned": aligned.user_f0_semitone.tolist(),
        "native_rms": native.rms.tolist(),
        "user_rms_aligned": aligned.user_rms.tolist(),
        "voiced_masks": {
            "native": native.voiced.tolist(),
            "user_aligned": aligned.user_voiced.tolist(),
        },
    }
