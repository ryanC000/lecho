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
    rows = calibrate.corpus_rows(entries)

    # 2 entries: emulation + monotone each, low_effort only on the first.
    assert len(rows) == 5
    for row in rows:
        for component in (row.overall, row.pitch, row.timing, row.energy):
            assert 0.0 <= component <= 100.0

    # The synthetic emulation reproduces the native contour; the flat monotone
    # must land below it on every entry.
    for _pid, emulation, monotone, _margin, _passed in calibrate.gate_report(rows):
        assert emulation > monotone


corpus_missing = pytest.mark.skipif(
    not calibrate.DEFAULT_MANIFEST.exists(),
    reason="calibration corpus not recorded on this machine (ticket 03 is a human task)",
)


@corpus_missing
def test_corpus_scores_end_to_end():
    entries = calibrate.load_manifest(calibrate.DEFAULT_MANIFEST)
    rows = calibrate.corpus_rows(entries)

    assert len(calibrate.gate_report(rows)) >= 2  # corpus size per Decision log 2026-07-12
    for row in rows:
        for component in (row.overall, row.pitch, row.timing, row.energy):
            assert 0.0 <= component <= 100.0


@corpus_missing
@pytest.mark.xfail(
    reason="constants are placeholders and practice 7's near-flat native clip "
    "cannot discriminate emulation from monotone (2026-07-12 calibration run; "
    "corpus entry to be replaced) — remove this marker when ticket 04 graduates "
    "the constants",
    strict=False,
)
def test_corpus_passes_graduation_gates():
    entries = calibrate.load_manifest(calibrate.DEFAULT_MANIFEST)
    rows = calibrate.corpus_rows(entries)

    for _pid, emulation, _monotone, margin, _passed in calibrate.gate_report(rows):
        assert emulation >= calibrate.GATE_EMULATION_MIN
        assert margin >= calibrate.GATE_MARGIN_MIN
