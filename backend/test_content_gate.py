"""Content-gate tests (ticket 20).

The MFA subprocess is integration-only (needs the conda env; ~45s), so it is
opt-in via RUN_MFA_TESTS. The gate's decision logic and MFA-output parsing are
pure functions and covered here directly.
"""
import os

import pytest

import content_gate

# Real speech_log_likelihood measured on practice 7's genuine emulation take
# (2026-07-21) — the "accept" reference the reject threshold graduates against.
GENUINE_ANALYSIS_CSV = (
    "file,begin,end,speaker,overall_log_likelihood,speech_log_likelihood,"
    "phone_duration_deviation,max_running_short_interval,snr,intensity_deviation\n"
    "utt,0.0,5.18,corpus,-44.64,-47.85,18.08,0,12.76,\n"
)


def test_parse_analysis_csv_reads_speech_log_likelihood():
    assert content_gate.parse_analysis_csv(GENUINE_ANALYSIS_CSV) == pytest.approx(-47.85)


def test_parse_analysis_csv_missing_value_is_none():
    header = (
        "file,begin,end,speaker,overall_log_likelihood,speech_log_likelihood,"
        "phone_duration_deviation,max_running_short_interval,snr,intensity_deviation\n"
    )
    assert content_gate.parse_analysis_csv(header) is None            # header only
    assert content_gate.parse_analysis_csv(header + "utt,0,1,corpus,-1,,0,0,1,\n") is None


def test_decide_ungraduated_threshold_never_rejects(monkeypatch):
    monkeypatch.setattr(content_gate, "CONTENT_GATE_MIN_SPEECH_LOGLIK", None)
    assert content_gate.decide(-999.0) is True  # measure-and-log mode


def test_decide_rejects_below_and_passes_above(monkeypatch):
    monkeypatch.setattr(content_gate, "CONTENT_GATE_MIN_SPEECH_LOGLIK", -60.0)
    assert content_gate.decide(-47.85) is True   # genuine take clears the bar
    assert content_gate.decide(-75.0) is False   # gibberish sits below it
    assert content_gate.decide(None) is True     # unmeasurable never rejects


def test_normalize_transcript_matches_offline_aligner_rules():
    assert content_gate.normalize_transcript(
        "Hier soir, j’ai vu le film Napoléon de Ridley Scott."
    ) == "hier soir j'ai vu le film napoléon de ridley scott"
    assert content_gate.normalize_transcript("Il y a 2 chats.") == "il y a deux chats"


@pytest.mark.skipif(
    os.environ.get("RUN_MFA_TESTS") != "1",
    reason="MFA integration (conda env, ~45s); set RUN_MFA_TESTS=1 to run",
)
def test_assess_genuine_take_is_intelligible():
    from pathlib import Path

    wav = Path(__file__).resolve().parent.parent / "native_audio" / "napoleon_emulation.wav"
    result = content_gate.assess(wav, "Hier soir, j'ai vu le film Napoléon de Ridley Scott.")
    assert result.assessed and result.passed
    assert result.speech_log_likelihood is not None
