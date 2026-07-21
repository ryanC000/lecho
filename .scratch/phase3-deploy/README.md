# Phase 3 — Productionization

The seams the codebase already built for this ("Phase 3" in `storage.py`, `worker_core.py`,
`migrations.py`) get their real backends: managed Postgres, S3, an SQS-driven worker container,
Docker images, and Terraform to provision it all. This is the work that makes the deployed
architecture match the intended one — the same swap the seams were designed for, not a rewrite.

Ambient-noise cleanup (SciPy) is **not** here — it already lives as master-plan ticket
[17](../master-plan/issues/17-noise-pipeline.md).

## Tickets & order

Dependencies are real, not stylistic. In particular: **S3 (02) is a hard prerequisite for the
worker split (04)** — once the worker is its own container it no longer shares the app's local
disk, so audio must live in shared object storage first.

```
01 postgres ─┐
02 s3 ───────┼─→ 03 docker ─→ 04 sqs-worker ─→ 05 terraform
             └──────────────────────────────────┘
```

1. **01 — PostgreSQL** → verify: suite green against Postgres; SQLite still works for dev
2. **02 — S3 storage backend** → verify: `BACKEND_S3` round-trips audio; routes unchanged
3. **03 — Docker** → verify: `docker compose up` boots app + Postgres locally
4. **04 — SQS + worker container** → verify: job published to SQS, scored by a separate worker
5. **05 — Terraform** → verify: `terraform apply` provisions the stack from clean

## Status legend
`ready-for-agent` · `blocked` · `needs-info` · `in-progress` · `done` (matches master-plan)
