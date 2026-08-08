# Phase 3 — Productionization

The seams the codebase already built for this ("Phase 3" in `infra/storage.py`, `worker/core.py`,
`infra/migrations.py`) get their real backends: managed Postgres, S3, an SQS-driven worker container,
Docker images, and a Kubernetes deployment to run it all. This is the work that makes the deployed
architecture match the intended one — the same swap the seams were designed for, not a rewrite.

Ambient-noise cleanup (SciPy) is **not** here — it already lives as master-plan ticket
[17](../master-plan/issues/17-noise-pipeline.md).

## Tickets & order

Dependencies are real, not stylistic. In particular: **S3 (02) is a hard prerequisite for the
worker split (04)** — once the worker is its own container it no longer shares the app's local
disk, so audio must live in shared object storage first.

```
01 postgres ✅ ─┐
02 s3       ✅ ─┼─→ 03 docker ✅ ─→ 04 sqs-worker ─→ 05 kubernetes
                └─────────────────────────────────────┘
```

1. **01 — PostgreSQL** → verify: suite green against Postgres; SQLite still works for dev — **done**
2. **02 — S3 storage backend** → verify: `BACKEND_S3` round-trips audio; routes unchanged — **done**
3. **03 — Docker** → verify: `docker compose up` boots app + Postgres locally — **done** (`910bd67`)
4. **04 — SQS + worker container** → verify: job published to SQS, scored by a separate worker
   — **unblocked by 03**
5. **05 — Kubernetes** → verify: worker pod scores a job uploaded through the Ingress; worker
   scales independently of the API

6. **06 — align_natives.py DATABASE_URL** → verify: respects the env var like every other entry
   point. Independent of 03–05; can be picked up any time. — **done** (`b1f73cf`)

7. **09 — Health endpoint** → verify: liveness survives a database outage, readiness does not.
   Prerequisite for 05's probes. — **done** (`9de8bb1`)

**Settled by 03:** the cluster in 05 must be **x86_64** — `praat-parselmouth` publishes no
Linux aarch64 wheel, so Oracle's ARM free tier is out without a source build of Praat.

Ticket 05 was **Terraform/ECS Fargate**; it is now Kubernetes. Container hosting moves to k8s
(local `kind`/`k3s` against real AWS S3 + SQS), and full infrastructure-as-code is deferred — it
gates nothing else in this phase.

**Cross-phase dependency:** master-plan ticket 15 (env-config) gates any *frontend* deployment —
`API_BASE` and the CORS origins are hardcoded to localhost, and Vite bakes them in at build time.
Nothing in 03–05 needs it, but the deployed app is not reachable from a browser without it.

## Status legend
`ready-for-agent` · `blocked` · `needs-info` · `in-progress` · `done` (matches master-plan)
