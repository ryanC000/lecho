# 03 — One clip-ingestion module for both audio entry points

**What to build:** A single module owns "bytes in → stored, validated, catalogued clip": store through the storage seam, derive authoritative metadata, apply the role's gates, and build the `AudioAsset` row. The upload route (USER_RECORDING, duration gates, 30-day expiry) and the native-clip ingest CLI (NATIVE_REFERENCE, ingest window, no expiry) become thin callers of the same interface. Asset invariants (sha256, authoritative duration, expiry policy) live once.

**Blocked by:** 02 (consumes the reshaped storage/metadata interfaces).

**Status:** done

- [ ] One implementation of AudioAsset construction; the duplicated field-by-field blocks are gone
- [ ] Upload route behaviour unchanged (same gates, same error messages)
- [ ] Ingest CLI behaviour unchanged (same window, same sanity check)
- [ ] Full pytest suite green

## Comments
Done 2026-07-11 in 71bb4c0. clip_ingest.ingest_clip + ClipRejectedError(log_message, detail). Verified end-to-end: real job on practice 7 SUCCESS 50.6 with sub-scores; size/duration/invalid gates return the original messages; CLI keeps its pre-store source-duration check (with --force) by design.
