"""Pytest wrapper for the calibration harness (master-plan ticket 02).

The smoke test needs no corpus — it runs the full pipeline on synthetic WAVs.
The corpus test asserts the ADR 0002 graduation gates on the real manifest and
skips cleanly when it is absent (the corpus is personal voice recordings,
gitignored — other machines and CI won't have it).
"""
import pytest

import calibrate


def test_smoke_corpus_runs_end_to_end(tmp_path):
    entries = calibrate.build_smoke_corpus(tmp_path)
    feats = calibrate.extract_corpus(entries)
    stds = calibrate.native_st_stds(entries, feats)
    rows = calibrate.corpus_rows(entries, feats)

    # 2 entries: reference + emulation + monotone + low_effort scored takes.
    assert len(rows) == 6
    for row in rows:
        for component in (row.overall, row.pitch, row.timing, row.energy):
            assert 0.0 <= component <= 100.0

    # The synthetic emulation reproduces the native contour; the entry's bad
    # take (ADR 0003: low_effort here — chirp references classify as flat)
    # must land below it on every entry.
    for _pid, emulation, _kind, bad, _margin, _gate, _passed in calibrate.gate_report(rows, stds):
        assert emulation > bad


corpus_missing = pytest.mark.skipif(
    not calibrate.DEFAULT_MANIFEST.exists(),
    reason="calibration corpus not recorded on this machine (ticket 03 is a human task)",
)


@corpus_missing
def test_corpus_scores_end_to_end():
    entries = calibrate.load_manifest(calibrate.DEFAULT_MANIFEST)
    feats = calibrate.extract_corpus(entries)
    stds = calibrate.native_st_stds(entries, feats)
    rows = calibrate.corpus_rows(entries, feats)

    assert len(calibrate.gate_report(rows, stds)) >= 2  # corpus size per Decision log 2026-07-12
    for row in rows:
        for component in (row.overall, row.pitch, row.timing, row.energy):
            assert 0.0 <= component <= 100.0


def test_bad_take_selection():
    """ADR 0003: expressive natives gate on monotone at the ADR 0002 margin;
    flat natives gate on low_effort at the flat margin."""
    assert calibrate.bad_take_kind(3.8) == "monotone"
    assert calibrate.margin_gate(3.8) == calibrate.GATE_MARGIN_MIN
    assert calibrate.bad_take_kind(2.1) == "low_effort"
    assert calibrate.margin_gate(2.1) == calibrate.GATE_MARGIN_FLAT_MIN


@corpus_missing
def test_corpus_passes_graduation_gates():
    """Definition of done for the dsp-3 graduation (ADR 0003): every corpus
    entry passes its emulation gate and its per-entry margin gate with the
    constants as shipped in dsp.py."""
    entries = calibrate.load_manifest(calibrate.DEFAULT_MANIFEST)
    feats = calibrate.extract_corpus(entries)
    stds = calibrate.native_st_stds(entries, feats)
    rows = calibrate.corpus_rows(entries, feats)

    for _pid, _emulation, _kind, _bad, _margin, _gate, passed in calibrate.gate_report(rows, stds):
        assert passed
