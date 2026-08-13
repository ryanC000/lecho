# 07 — 🧑 Load native reference clips into the deployed bucket

**What to build:** A documented, executed procedure that puts native reference audio into the
deployment's S3 bucket and links it to the practices in the Supabase database. Until that exists,
a freshly deployed cluster **fails every single submission** while looking perfectly healthy —
`worker.core.run` rejects any job whose practice has no `audio_url` with "This practice isn't ready
for scoring yet — its reference audio hasn't been added"
([core.py](../../../backend/worker/core.py)), and `tools.seed` creates practices without audio.

There is no code gap here; there is a **path** gap. [ingest_native.py](../../../backend/tools/ingest_native.py)
already writes through the storage seam and sets `Practice.audio_url`, so it lands in whatever
`STORAGE_BACKEND`/`DATABASE_URL` its environment points at. What is missing is how the clips get to
it in a deployment:

- `native_audio/` is gitignored and deliberately **not** in the image (03: "the image holds no
  audio"), so no pod has the source files.
- `docker-compose.yml` bind-mounts `./native_audio:/native_audio:ro`. The k8s manifests have **no
  equivalent volume**, and adding one would mount a laptop directory into a pod for a one-time
  data load — the wrong shape.

The clean answer is that this is a one-time, run-from-the-dev-box operation, not a cluster
concern: point `ingest_native` at the real bucket and the real database, run it once, and the
cluster reads the results out of S3 from then on. That needs writing down and doing.

    # from backend/, with the deployment's env
    DATABASE_URL=<supabase session pooler URI> \
    STORAGE_BACKEND=S3 S3_BUCKET=<bucket> AWS_REGION=<region> \
    python -m tools.ingest_native ../native_audio/clip.wav --practice-id 3

**Why it is a 🧑 ticket:** the clips themselves are the blocker, not the tooling. Sourcing them is
master-plan ticket [19](../../master-plan/issues/19-ingest-native-clips.md) (`ready-for-human`), and
the credentials this needs are the owner's.

**Watch for:** `ingest_native` enforces a native duration window of `[2/0.8, 15/1.2]` seconds so
user recordings still fit the ±20% and absolute 2–15s gates. Clips outside it are rejected at
ingest, not at scoring.

**Found during:** phase3-deploy 05. The manifests and runbook were complete and the deployed app
would still have failed 100% of jobs.

**Blocked by:** master-plan 19 (the clips must exist). The AWS bucket and Supabase project from 05
must exist first, since this writes to both.

**Status:** ready-for-human

- [ ] At least one native clip ingested into the deployment's S3 bucket, with
      `Practice.audio_url` set in the Supabase database
- [ ] Procedure written into `k8s/README.md` as its own step, including the env vars — a future
      redeploy against a fresh bucket must not have to rediscover it
- [ ] A job submitted through the Ingress reaches `SUCCESS` rather than the "isn't ready for
      scoring yet" failure — the same criterion 05 cannot pass without this
- [ ] `tools.seed` practices that have **no** native clip still fail with the clear user-facing
      message, not a 500

**Note for 05:** its "a recording uploaded through the Ingress is scored by a worker pod" box
cannot be ticked until this one is done.
