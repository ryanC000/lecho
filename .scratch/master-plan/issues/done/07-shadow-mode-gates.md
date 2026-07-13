# 07 — Shadow mode backend: mode field + per-mode duration gates

**What to build:** Job submission understands solo vs shadow. The job-creation form gains a `mode` field (`solo` default, `shadow` allowed, 400 otherwise), persisted on the job and exposed in the status payload. Duration gates go per-mode, applied twice in the existing two-layer pattern (client-reported duration as fast-fail, server-derived as authoritative): solo keeps ±20% of the native duration; shadow expects native duration + 1.0s tail within ±0.5s. The absolute 2–15s gate is unchanged for both.

**Blocked by:** None — can start immediately.

**Status:** done (commit `15ff53c`, 2026-07-12)

- [x] Invalid mode → 400; missing mode → solo (backward compatible)
- [x] Solo gate unchanged and still tested
- [x] Shadow gate accepts native+1.0s ±0.5s and rejects outside it, tested at both layers
- [x] Job status payload includes `mode`

## Comments

- 2026-07-12 (post-completion, owner decision): the solo relative gate was later relaxed from ±20% to ±50% (`SOLO_TOLERANCE_FRAC`, both layers + client mirror) — edge silence from early/late button presses is trimmed before scoring, so the tight gate only caused false rejections. See the master plan Decision log.
