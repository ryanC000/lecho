# 02 — Close the get_path() hole in the storage seam

**What to build:** Every file access crosses the storage seam's interface instead of reaching through it. The seam gains the verbs callers actually need — existence check, readable stream, and an audio-serving response — so `.exists()`, `FileResponse`, and `wave.open()` on raw paths disappear from routes, worker, and the ingest CLI. Audio metadata extraction reads a file-like object rather than a filesystem path. The dead `presign_put` stub goes (one adapter today makes it a hypothetical seam verb). Rename the `s3_coordinates_json_path` column reference in the domain model to a backend-agnostic name via the startup-migrations mechanism (SQLite: add-and-backfill or accept the ORM-attribute rename only — pick the lighter option and record it).

**Blocked by:** 01 (both rewrite the worker's file access).

**Status:** done

- [ ] No caller outside the storage module touches a raw storage path
- [ ] Native-clip serving works through the seam (manual: practice audio plays)
- [ ] Metadata extraction works on both upload and ingest paths
- [ ] Full pytest suite green

## Comments
Done 2026-07-11 in 66f164e. Verbs: exists/open_read/audio_response; get_path re-scoped to DSP materialization; presign_put deleted; extract_metadata takes a stream; coordinates_key ORM rename (column name kept — the lighter option). Verified: leak grep clean, audio route serves practice 7 (which turned out to exist on disk), 404 path intact.
