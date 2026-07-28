"""Content-gate tests (ticket 22).

The STT subprocess is integration-only (needs the `stt` conda env; downloads a
model on first run), so it is opt-in via RUN_STT_TESTS. The gate's WER metric
and decision logic are pure functions and covered here directly.
"""
import os

import pytest

import content_gate


def test_word_error_rate_identical_is_zero():
    assert content_gate.word_error_rate("hier soir j'ai vu le film", "hier soir j'ai vu le film") == 0.0


def test_word_error_rate_disjoint_is_one():
    # Every reference word substituted → distance == reference length → 1.0.
    assert content_gate.word_error_rate("un deux trois", "sept huit neuf") == pytest.approx(1.0)


def test_word_error_rate_empty_hypothesis_is_one():
    # No words recognized against a real line: all deletions → 1.0 (rejects).
    assert content_gate.word_error_rate("un deux trois quatre", "") == pytest.approx(1.0)


def test_word_error_rate_empty_reference_is_zero():
    assert content_gate.word_error_rate("", "quelque chose") == 0.0


def test_word_error_rate_partial_errors():
    # One substitution out of four words → 0.25.
    assert content_gate.word_error_rate("un deux trois quatre", "un deux trois cinq") == pytest.approx(0.25)


def test_decide_ungraduated_threshold_never_rejects(monkeypatch):
    monkeypatch.setattr(content_gate, "CONTENT_GATE_MAX_WER", None)
    assert content_gate.decide(0.99) is True  # measure-and-log mode


def test_decide_rejects_above_and_passes_below(monkeypatch):
    monkeypatch.setattr(content_gate, "CONTENT_GATE_MAX_WER", 0.50)
    assert content_gate.decide(0.25) is True   # genuine take clears the bar
    assert content_gate.decide(0.90) is False  # gibberish sits above it
    assert content_gate.decide(0.50) is True   # boundary is inclusive
    assert content_gate.decide(None) is True   # unmeasurable never rejects


def test_normalize_transcript_matches_offline_aligner_rules():
    assert content_gate.normalize_transcript(
        "Hier soir, j’ai vu le film Napoléon de Ridley Scott."
    ) == "hier soir j'ai vu le film napoléon de ridley scott"
    assert content_gate.normalize_transcript("Il y a 2 chats.") == "il y a deux chats"


@pytest.mark.skipif(
    os.environ.get("RUN_STT_TESTS") != "1",
    reason="STT integration (conda env, model download); set RUN_STT_TESTS=1 to run",
)
def test_assess_genuine_take_is_intelligible():
    from pathlib import Path

    wav = Path(__file__).resolve().parent.parent / "native_audio" / "napoleon_emulation.wav"
    result = content_gate.assess(wav, "Hier soir, j'ai vu le film Napoléon de Ridley Scott.")
    assert result.assessed and result.passed
    assert result.wer is not None and result.wer < 0.5
