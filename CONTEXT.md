# L'Écho — Domain Glossary

Terms as this project uses them. Outputs (issues, tests, docs) should use these words,
not synonyms. Decisions behind them live in `docs/adr/`.

- **Emulation take** — the owner's best-effort imitation of a native clip, recorded for
  calibration. Replaces the unavailable "second native rendition" (ADR 0002).
- **Monotone take** — a deliberate flat read of the same line; the negative example
  calibration discriminates against.
- **Low-effort take** — a mumbled/careless read used as a *diagnostic row* in the
  calibration table; never a tuning constraint.
- **Discrimination margin** — emulation score minus monotone score for the same
  practice. The quantity `--tune` maximizes; gate is ≥ 20 points (ADR 0002).
- **Graduation** — a placeholder constant in `dsp.py` becoming a calibrated value via
  Task 1.2; recorded in the plan's Decision log, bumps `ALGO_VERSION`.
- **dsp-2 baseline** — the scoring pipeline frozen at commit `338eb58` (ADR 0001);
  calibration tunes its constants but its structure is fixed for this phase.
- **Bleed** — native-clip playback leaking into the user's mic during a shadow take;
  detected by normalized cross-correlation in the worker, hard-fails the job.
