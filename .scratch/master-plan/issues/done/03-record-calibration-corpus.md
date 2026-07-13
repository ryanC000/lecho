# 03 — 🧑 Record the calibration corpus (gate H1)

**What to build:** The owner records, for 2 practices with native clips (reduced from ≥3 — owner time constraint, see Decision log 2026-07-12): an **emulation take** (best effort, recorded shadow-style — listening to the native clip on headphones while speaking along; headphones mandatory since these WAVs bypass the app's bleed gate) and a **monotone take** (deliberate flat read). For at least one practice, also a **low-effort take** (mumbled/careless) as a diagnostic. Fill in the calibration manifest. (Practice 7's native reference was verified present and serving on 2026-07-11 — no re-ingest needed.)

**Blocked by:** None — human task, can start immediately. (Ticket 04 needs both this and 02.)

**Status:** done (2026-07-12)

- [x] Practice 7 native clip playable (verified 2026-07-11; re-ingest not needed)
- [x] 2 practices (7 "napoleon", 2 "napoleon2") each have emulation + monotone WAVs in `native_audio/` (count reduced from ≥3)
- [x] ≥1 low-effort take recorded (both practices have one)
- [x] Manifest filled and parseable: `native_audio/manifest.json`

**Note for ticket 04 (updated 2026-07-12 after the first calibration run):** practice 7's emulation take was recorded shadow-style (owner confirmed) and is bleed-clean — the take is fine. The problem is the clip: practice 7's native line is nearly flat (2.1 st semitone std vs 3.8 for practice 2), so a deliberate monotone genuinely resembles it and no constants can produce a positive margin. Its corpus entry must be replaced with a practice whose native clip has real pitch movement (aim for semitone std ≳ 3; the harness's diagnostics print it) plus fresh owner takes.
