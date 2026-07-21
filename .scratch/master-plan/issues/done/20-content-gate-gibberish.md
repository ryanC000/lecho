# 05 — Content gate: gibberish scores like a real take

**Symptom (2026-07-13, owner report):** speaking gibberish on practice 7 (shadow mode) scored 58.5–70.6 overall under dsp-3 — one take (70.6) outscored the corpus emulation (70.1). The six takes were deleted at the owner's request (jobs `2a5564e0…`, `2f897f4a…`, `794dcabf…`, `7af465b6…`, `6b0184b5…`, `ff8a9916…`); re-recording gibberish takes 30 seconds when picking this up.

**Diagnosis (measured on the actual takes before deletion):**

- The scorer is prosody-only; nothing measures *what* was said. The calibration corpus's bad takes (monotone/low_effort) all speak the correct words, so the dsp-3 tuner had no constraint preserving content sensitivity.
- Shadow mode hands the timing axis (weight 0.60) to anyone speaking in sync with playback: gibberish timing RMSE 1.31–1.91 vs emulation 1.45.
- Pitch RMSE does see 5 of 6 takes (3.6–8.2 st vs emulation 2.71) but K=8 / weight 0.20 forgives it. Best possible reweighting (grid scan, emulation ≥ 65 + low_effort margin ≥ 3 kept): catchable gibberish drops only to ~50–58 with degenerate weights (energy 0) — a partial patch.
- MFCC does NOT catch wrong words: gaps vs emulation +0.02…+0.22, mostly under the 0.15 go-criterion (cross-speaker spectral floor; consistent with ADR 0003's no-go).
- **One take was uncatchable in principle:** flat-spoken, rhythm-matched gibberish measured *better than the genuine emulation on every axis* (pitch 2.04, timing 1.54, energy 1.01, MFCC 1.35). Prosody features cannot ever reject it.

**Fix direction (owner deferred):** a content *gate*, not a graded axis — force-align the practice transcript against the take (MFA French models, Task 2.1 track, owner-approved 2026-07-11); reject unintelligible takes with "we couldn't make out the line" before scoring. Prerequisite: per-practice transcripts (`napoleon_script.txt` is currently empty). Optional hardening: add recorded gibberish takes to the calibration corpus as a new take kind with an emulation-vs-gibberish gate so the tuner can never again pick content-blind constants.

- [x] Per-practice transcripts exist (~~practice 7's script file is empty~~ — stale: transcripts live in `Practice.transcript` in the DB, not a script file; practice 7's is populated and already produced `alignments/7.json`)
- [~] MFA forced-alignment gate rejects a gibberish take end-to-end — **mechanism done & validated end-to-end on a genuine take** (`content_gate.assess` runs MFA, reads `speech_log_likelihood`, decides; wired into `worker_core.run` before scoring, fails open). The *reject* half is 🧑 **human-gated**: owner must re-record a gibberish take and graduate `CONTENT_GATE_MIN_SPEECH_LOGLIK` (it is `None` = measure-only until then, so an uncalibrated gate can't wrongly block learners).
- [~] Gibberish take kind added to `native_audio/manifest.json` + `calibrate.py` gate — `calibrate.py` now supports `gibberish` as a **diagnostic-only** take kind (never a tuning constraint — the diagnosis proved scoring can't gate wrong words). Adding `gibberish` WAVs + manifest entries is 🧑 **human-gated** (the takes were deleted; `load_manifest` would error on missing files).
- [~] Rerun `calibrate.py --tune`; decision log updated — Decision log updated (2026-07-21). The `--tune` rerun is 🧑 **human-gated** on the gibberish recordings and won't move constants (gibberish is diagnostic-only).

---

**Status: done (mechanism) — 2026-07-21, commit `44e7767`.** Content gate implemented, wired always-on into the worker (owner-approved), and validated end-to-end on a genuine take (`speech_log_likelihood` -47.9, passes). Remaining boxes are human-gated on the owner re-recording the deleted ~30s gibberish takes, then graduating the reject threshold (`python content_gate.py <take.wav> "<transcript>"` on genuine + gibberish) and adding them to the manifest. Full backend suite green (49 passed, 1 MFA integration skipped).
