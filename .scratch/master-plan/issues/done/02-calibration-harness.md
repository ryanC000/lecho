# 02 — Calibration harness CLI

**What to build:** A CLI that answers "is dsp-2 scoring defensible on real audio?" from a corpus manifest. Given entries of reference / emulation take / monotone take (optional low-effort take as a diagnostic row), it runs the pure scoring pipeline per pair and prints a table of all four score components. A `--tune` mode grid-searches the scoring constants to maximize the discrimination margin (emulation minus monotone) subject to the graduation gates: emulation ≥ 75, monotone ≥ 20 points below (ADR 0002). A `--smoke` mode runs on synthetic WAVs so the harness is verifiable before the corpus exists. Recommended constants are printed for a human to apply deliberately — no auto-edit.

Manifest contract (paths relative to the manifest; 2 entries to graduate — reduced from ≥3, see Decision log 2026-07-12; actual manifest: `native_audio/manifest.json`):

```json
[{"practice_id": 7, "reference": "p7_native.wav", "emulation": "p7_emulation.wav",
  "monotone": "p7_monotone.wav", "low_effort": "p7_low_effort.wav"}]
```

**Blocked by:** None — can start immediately.

**Status:** done (2026-07-12) — `backend/calibrate.py` + `backend/test_calibration.py`

- [x] `--smoke` runs the full pipeline end to end on synthetic audio with no manifest present (exit 0 regardless of gates — synthetic audio only verifies the pipeline)
- [x] Table prints overall + pitch/timing/energy for every pair, low-effort rows marked diagnostic
- [x] `--tune` respects the gates and also sweeps the pitch floor (60/65/75 Hz) as a diagnostic (Phase 1R creak/octave-error finding), with median-F0/voiced% per take
- [x] A pytest wrapper skips cleanly when the manifest is missing
- [x] No HTTP or DB involvement — pure pipeline only
