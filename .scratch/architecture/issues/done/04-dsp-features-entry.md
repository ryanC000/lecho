# 04 — Deepen the dsp pipeline entry point

**What to build:** One entry function on the dsp module — path in, trimmed `ProsodyFeatures` out — absorbs the load→extract→trim stage order that every caller currently re-encodes. The worker and the ingest sanity-check switch to it; the calibration harness (master-plan ticket 02) is written against it instead of copying the chain a third time. The stage functions stay public as internal seams so the existing 12 dsp tests are untouched — the dsp-2 baseline (ADR 0001) does not move.

**Blocked by:** 03 (call sites live in files reshaped by 01–03).

**Status:** done

- [ ] New entry function; worker and ingest call it
- [ ] No behaviour change: identical scores for identical inputs
- [ ] Existing dsp tests pass unmodified
- [ ] Full pytest suite green

## Comments
Done 2026-07-11 in 3ba50af. dsp.features_for(path); worker uses it for both clips. Deviation from AC: the ingest CLI keeps extract+trim on its already-loaded Sound (features_for would double-load); the calibration harness is the intended third caller. Verified: identical arrays and identical E2E score (50.6) pre/post.
