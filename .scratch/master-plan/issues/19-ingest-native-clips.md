# 19 — 🧑 Ingest native clips for the remaining practices (gate H2)

**What to build:** Every practice in the catalog becomes usable: the owner records or collects a native clip per remaining practice and ingests each through the ingestion CLI, which converts to 16k mono, enforces the duration window, and wires the practice's audio. Blocks nothing in code — it gates only "all practices usable" acceptance, and each newly ingested clip should also get an alignment (ticket 05's script re-run).

**Blocked by:** None — human task, ongoing.

**Status:** ready-for-human

- [ ] Every practice has playable native audio in the app
- [ ] Alignment JSON regenerated for each newly ingested clip
