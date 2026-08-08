# 09 — Health endpoint for the Kubernetes probes

**What to build:** `GET /health` and `GET /health/ready`, so ticket 05 has something to point
its liveness and readiness probes at. The app has **no `/` route at all** — 03 had to verify
"uvicorn serves" against `/practices` — so today there is no endpoint whose contract is
"tell me if this pod is healthy".

**Why two endpoints and not one.** Kubernetes asks two different questions, and answering both
with one DB-touching endpoint is a known way to build an outage amplifier:

- **Liveness** — "is this process wedged?" A failure **restarts the pod**. It must NOT touch
  Postgres: if it does, a brief database blip restarts every API pod simultaneously, and they
  come back into the same blip.
- **Readiness** — "can this pod serve traffic?" A failure only **removes it from the Service's
  endpoints**. This is where the DB check belongs, because a pod that cannot reach Postgres
  should be drained, not killed.

Using `/practices` for both (the obvious shortcut, since it already exists and hits the DB) is
exactly the trap: it is a correct readiness probe and a dangerous liveness probe.

**Found during:** ticket 03, which discovered the app has no root route, and ticket 05's
requirement "Liveness and readiness probes on the API".

**Blocked by:** nothing.

**Status:** done — `9de8bb1`, 2026-08-08

- [x] `GET /health` returns 200 without touching the database
- [x] `GET /health/ready` returns 200 when the database answers, 503 when it does not
- [x] Liveness stays green through a real database outage — verified in the compose stack by
      `docker compose stop db`: `/health` held at 200 while `/health/ready` returned 503, and
      readiness recovered to 200 on `docker compose start db` with no restart
- [x] Full pytest suite still green — 81 passed, 1 skipped

**Note for 05:** the manifests should set `livenessProbe` on `/health` and `readinessProbe` on
`/health/ready`. Give readiness a short `periodSeconds` and liveness a generous
`failureThreshold` — the asymmetry is the point.
