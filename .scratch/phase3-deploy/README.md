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
02 s3       ✅ ─┼─→ 03 docker ✅ ─→ 04 sqs-worker ✅ ─→ 05 kubernetes ✅ (code)
                └─────────────────────────────────────┘
```

1. **01 — PostgreSQL** → verify: suite green against Postgres; SQLite still works for dev — **done**
2. **02 — S3 storage backend** → verify: `BACKEND_S3` round-trips audio; routes unchanged — **done**
3. **03 — Docker** → verify: `docker compose up` boots app + Postgres locally — **done** (`910bd67`)
4. **04 — SQS + worker container** → verify: job published to SQS, scored by a separate worker
   — **code complete**; the queue seam, worker entrypoint and tests are in, the real-queue run is not
5. **05 — Kubernetes** → verify: worker pod scores a job uploaded through the Ingress; worker
   scales independently of the API — **manifests complete, unverified**; needs the owner to stand
   up the cluster and the AWS/Supabase accounts (`k8s/README.md`)

6. **06 — align_natives.py DATABASE_URL** → verify: respects the env var like every other entry
   point. Independent of 03–05; can be picked up any time. — **done** (`b1f73cf`)

7. **09 — Health endpoint** → verify: liveness survives a database outage, readiness does not.
   Prerequisite for 05's probes. — **done** (`9de8bb1`)

### Opened by 05 — the gap between "manifests exist" and "the demo works"

```
07 natives ─┐
08 pool    ─┴─→ 05 verified ─→ 11 readme
10 retention (independent)
```

8. **07 — 🧑 Natives into the deployed bucket** → verify: a job through the Ingress reaches
   SUCCESS. **Hard prerequisite for 05's own scoring criterion** — without native reference audio
   the deployed app fails every submission while looking healthy. Needs master-plan 19 first.
9. **08 — Connection pool budget** → verify: `--replicas=3` doesn't exhaust the free-tier
   database. SQLAlchemy's default is 15 connections *per pod*; 1 API + 3 workers is 60. Should
   land before 05's scaling demo.
10. **10 — Retention sweep** → verify: expired user recordings actually get deleted. `expires_at`
    has been written since Phase 1 and read by nothing. Independent of everything.
11. **11 — README deployed architecture** → verify: the top-level README describes the system that
    now exists. Best written after 05 has actually been stood up.

**Settled by 03:** the cluster in 05 must be **x86_64** — `praat-parselmouth` publishes no
Linux aarch64 wheel, so Oracle's ARM free tier is out without a source build of Praat.

Ticket 05 was **Terraform/ECS Fargate**; it is now Kubernetes on **Docker Desktop** against real
AWS S3 + SQS and Supabase Postgres. Full infrastructure-as-code is dropped, not deferred: four
hand-created AWS resources for a laptop demo have nothing to reproduce.

**Deployed shape:** frontend, API and worker all run in the cluster, with one Ingress serving the
static bundle and the API on a single origin (`http://localhost`) — which is what removes CORS and
mixed content from the deployment entirely. Public reachability was considered and declined; the
demo is local and live. Full runbook: `k8s/README.md`.

**Cross-phase dependencies:** master-plan ticket 15 (env-config) is **done** (`be990fb`), so it no
longer gates the frontend deployment. Ticket 24 (Google OAuth client ID) still does for sign-in —
and now needs `http://localhost` registered as an origin alongside the Vite one.

## Status legend
`ready-for-agent` · `blocked` · `needs-info` · `in-progress` · `done` (matches master-plan)
