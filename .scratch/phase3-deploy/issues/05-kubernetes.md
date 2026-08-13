# 05 — Kubernetes deployment

**What to build:** The app and worker images from 03/04 run as Kubernetes workloads, so the
deployed topology is a real orchestrated cluster rather than `docker compose`. Scope: a
`Deployment` for the API and a second one for the worker (independently replicable — that
separation is the point), a `Service` plus `Ingress` fronting the API, and `ConfigMap`/`Secret`
objects supplying the env vars the seams from 01–04 already read (`DATABASE_URL`,
`STORAGE_BACKEND`, `S3_BUCKET`, `AWS_REGION`, `QUEUE_BACKEND`, the queue URL). Manifests live under
`k8s/` and are plain YAML — no Helm chart unless something actually needs templating. Liveness and
readiness probes on the API; the worker needs neither (it polls, it doesn't serve).

**The probe endpoints exist** (ticket 09, done): `livenessProbe` → `GET /health` (never touches
Postgres, so a database blip cannot restart every API pod), `readinessProbe` → `GET /health/ready`
(503 when the database is unreachable, so the pod is drained instead of killed). Do not point
liveness at anything that queries the database.

The worker `Deployment` is what makes the architecture legible: scaling audio processing means
`replicas: N` on that object alone, with no effect on API capacity. That is the whole reason the
queue in 04 exists.

**Deploy target (settled): Docker Desktop Kubernetes**, pointed at **real** AWS S3 and SQS, with
Postgres on the Supabase free tier. Real Kubernetes objects, real managed services, zero cluster
cost. Chosen over `kind`/`k3s`/minikube for two concrete reasons on Windows:

- It shares the Docker image store, so `docker build -t lecho:dev ./backend` is immediately usable
  by the cluster with `imagePullPolicy: IfNotPresent` — no registry, no `minikube image load`, no
  `eval $(minikube docker-env)` per shell. (Tag must not be `latest`, which implies `Always`.)
- It binds `Service type=LoadBalancer` to `localhost`, so the Ingress answers on
  `http://localhost` with no `minikube tunnel` and no hosts-file entry.

Its one cost: no ingress controller ships with it, so `ingress-nginx` is installed by manifest
(the `provider/cloud` variant — its `LoadBalancer` Service is what maps to localhost). Single-node
only, which does not matter here: `kubectl scale deploy/worker --replicas=3` schedules three pods
on one node, and independent scaling is what this ticket demonstrates.

**Deployment-specific requirements found while implementing** (each fails *silently* if missed):

- **Supabase must use the session pooler** (`aws-0-<region>.pooler.supabase.com:5432`), not
  `db.<ref>.supabase.co` — the direct endpoint is IPv6-only on the free tier and Docker Desktop
  cannot reach it. Not the transaction pooler (6543) either: it breaks psycopg's prepared
  statements. Add `?sslmode=require`. The free tier also pauses after 7 days idle.
- **The S3 bucket needs a CORS policy.** `GET /practices/{id}/audio` redirects to a presigned S3
  URL and wavesurfer fetches it cross-origin, so without one the API stays healthy while every
  waveform fails to load.
- **`proxy-body-size: 10m` on the Ingress.** ingress-nginx defaults to 1MB; `job_gates`
  accepts 10MB, so takes over 1MB would 413 at the Ingress before reaching the app's own gate.
- **Google's authorised JS origins are per-origin, including port.** `http://localhost` (the
  Ingress) is a different origin from `http://localhost:5173` (Vite) and must be registered too —
  ticket 24.
- Port 80 on Windows is often held by IIS / the World Wide Web Publishing Service; the controller's
  EXTERNAL-IP stays `<pending>` if so.

**Not chosen — a hosted cluster.** The manifests are portable and would not change, but an
`Ingress` provisions a **billed load balancer (~$10–12/mo)** on every managed provider, HTTPS needs
a domain (~$10/yr) plus `cert-manager`, and a non-AWS cluster ships every audio file across the
public internet to S3. Oracle's free tier is additionally ruled out by 03's wheel check:
`praat-parselmouth` publishes no Linux aarch64 wheel, so an ARM node would have to build Praat's
C++ from source. **x86_64 only.**

**Frontend hosting (settled): an nginx pod in-cluster, behind the same Ingress as the API.**
Two constraints decided it:

1. **A publicly hosted frontend cannot reach a laptop cluster.** A bundle on Netlify/CloudFront
   loads fine, then fails every API call, because the cluster has no public address.
2. **Static hosts serve HTTPS by default**, and browsers block HTTPS pages calling HTTP APIs as
   mixed content — so even a reachable cluster would need TLS on the Ingress.

Serving both from one Ingress sidesteps both: the browser makes **no cross-origin request at all**,
so CORS and mixed content stop being deployment concerns. It also keeps the bundle portable —
built with `VITE_API_BASE=""` it emits relative URLs and is pinned to no hostname. The SPA's routes
(`/library`, `/history`, `/practice/:id`, `/results/:jobId`) do not collide with the API's
(`/practices`, `/auth`, `/jobs`, `/health`), so path prefixes route it with no rewrite rules.

Public reachability (a `cloudflared` tunnel, or a hosted cluster with TLS) was considered and
declined: it requires the laptop to be on to be worth anything, and a free tunnel's random URL
breaks Google sign-in, which needs an exact pre-registered origin.

**AWS resources needed:** an S3 bucket (+ a CORS rule), an SQS queue + DLQ with a redrive policy,
and an IAM user/policy scoped to exactly those two ARNs. Created by console — full checklist and a
teardown checklist in `k8s/README.md`. **Terraform was considered and dropped:** its value is
reproducibility, and four resources created once for a laptop demo do not need reproducing.
(Kubernetes cannot provision them either — that needs Crossplane or ACK, far more machinery than
the four resources it would manage.) No credentials in git; the `Secret` is created out-of-band
from a documented command and only a `.example` is committed.

**Blocked by:** nothing — 03 (images) and 04 are both done. Master-plan ticket 15 (env-config) was
listed as a soft prerequisite and is **done** (`be990fb`).

**Status:** ready-for-human — manifests in `k8s/`, runbook in `k8s/README.md`; **none of the
acceptance criteria below have been run**. They need a live cluster plus AWS/Supabase accounts
that do not exist yet, so every box is still open on purpose.

- [ ] `kubectl apply -k k8s/` brings up API and worker Deployments; both reach `Running`
- [ ] API is reachable through the Service/Ingress and serves `/`
- [ ] A recording uploaded through the Ingress is scored by a **worker pod**, not the API pod
      (prove it from the worker pod's logs)
- [ ] `kubectl scale deploy/worker --replicas=3` adds consumers without touching the API
- [ ] Config comes entirely from ConfigMap/Secret — no image rebuild to change bucket or queue
- [ ] No secrets committed; the Secret is created out-of-band from a documented command
- [ ] Frontend served from the same Ingress; SPA deep links survive a refresh (`try_files`)
- [ ] A practice's **waveform renders** in the browser — the only thing that proves the bucket's
      CORS rule is right, since a missing one leaves the API perfectly healthy

**Owner-run steps** (console work and a live cluster): enable Kubernetes in Docker Desktop, install
`ingress-nginx`, create the AWS + Supabase resources, register `http://localhost` with the OAuth
client (24), then walk `k8s/README.md` §3–§6.

## Dropped from the original scope

This ticket previously specified **Terraform provisioning ECS Fargate**. Kubernetes replaces ECS as
the container host. Full infrastructure-as-code (RDS, IAM roles, container hosting) is deferred —
it is not a prerequisite for anything else in this phase, and the resources this needs are small
enough to create by hand. Revisit if the deployment ever needs to be reproducible from clean.
