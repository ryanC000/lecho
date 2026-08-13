# 08 — Connection pool budget for the free-tier database

**What to build:** Make the SQLAlchemy pool size configurable and set it per role, so scaling the
worker cannot exhaust the database's connection ceiling.
[database.py](../../../backend/infra/database.py) calls `create_engine` with no pool arguments,
which means SQLAlchemy's defaults: `pool_size=5` plus `max_overflow=10` — up to **15 connections
per process**. That was invisible when the API was the only process and SQLite was the database.
It is not invisible now:

| Pods | Connections at full pool |
|---|---|
| 1 API | 15 |
| 3 workers (`kubectl scale deploy/worker --replicas=3`) | 45 |
| **total** | **60** |

The exact ceiling on a Supabase free-tier project has to be read off the dashboard rather than
assumed, but it is on the order of 60 — and Supabase's **session** pooler, which 05 requires for
IPv4 reachability, holds one server connection per client connection for the life of the session,
so it does not absorb this the way the transaction pooler would. The demo that proves the
architecture (scale the worker, watch throughput rise without touching the API) is exactly the
action that would hit the wall.

The worker does not need 15 connections. It processes **one message at a time** by construction
([queue.py](../../../backend/infra/queue.py) `MaxNumberOfMessages=1`), so it opens one session per
job and closes it in `run`'s `finally`. Two is generous.

Add `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` env vars read in `infra/database.py`, keep today's defaults
so nothing changes for dev, and set them low on the worker Deployment. SQLite ignores pool
arguments, so the dev path is untouched either way.

**Why not just raise the ceiling:** the free tier is the constraint the whole deployment was
designed around, and a worker holding 14 idle connections is wrong regardless of what the ceiling
is. This is right-sizing, not a workaround.

**Found during:** phase3-deploy 05, writing the worker Deployment's scale story.

**Blocked by:** nothing. Independent of 07 — can be picked up any time, and should land before the
`--replicas=3` demo in 05.

**Status:** ready-for-agent

- [ ] `DB_POOL_SIZE` and `DB_MAX_OVERFLOW` read in `infra/database.py`, defaulting to SQLAlchemy's
      current values so no existing behaviour changes
- [ ] Pool arguments are not passed on SQLite, which does not accept them
- [ ] `worker-deployment.yaml` sets a small pool (2 / 0); documented in `backend/.env.example`
- [ ] `kubectl scale deploy/worker --replicas=3` runs without connection-limit errors, and the
      Supabase dashboard's connection count stays well under the project's ceiling
- [ ] Full pytest suite still green
