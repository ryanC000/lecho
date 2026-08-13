# 11 — README describes a system that no longer exists

**What to build:** A deployed-architecture section in the top-level
[README.md](../../../README.md), with a diagram. The current file is 111 lines of local setup —
"Setup & Installation", "Backend Server Setup", "Frontend Application Setup", "Google Sign-In",
"Backend layout", "Offline tools" — and says nothing about the queue, the worker split, the
cluster, or the managed services. It describes the monolith the project stopped being at ticket 04.

**Why this is a ticket and not a chore:** this project's stated purpose is a portfolio piece, and
the README is the artifact a reader actually opens. The engineering worth showing is precisely the
part that is undocumented: a scoring job crossing a real queue into an independently scalable
worker, behind seams (`STORAGE_BACKEND`, `QUEUE_BACKEND`, `CONTENT_GATE_BACKEND`) that let the same
code run on a laptop with SQLite and local disk, or on Kubernetes against Postgres, S3 and SQS,
with no branching in the routes. That story is currently only legible to someone who reads
`.scratch/` — which nobody will.

Cover:

- **The diagram** — Ingress fronting the frontend and API on one origin, the worker consuming SQS,
  and the three managed services behind them. `k8s/README.md` has an ASCII version to start from.
- **Why the queue exists** — scaling audio processing is `replicas: N` on one Deployment, with no
  effect on API capacity. This is the whole architectural claim; state it in one sentence.
- **The seams**, and that they are why the test suite stays hermetic and offline while the
  deployment uses real infrastructure. `worker.core.run` being transport-independent is the point.
- **What runs where, and what it costs** — Docker Desktop k8s ($0), Supabase free tier, AWS free
  tier. Note that the demo is deliberately local: a laptop cluster has no public address, and the
  alternatives (tunnel, hosted cluster with a billed load balancer) were considered and declined.
- **The decisions with teeth** — x86_64 only because `praat-parselmouth` ships no aarch64 wheel;
  the content gate's two backends because there is no conda in a container; same-origin serving
  because it removes CORS and mixed content from the deployment entirely.

Keep the existing local-setup sections. This adds a layer above them; it does not replace them.

**Found during:** phase3-deploy 05.

**Blocked by:** nothing, but it is worth writing **after** 05 has actually been stood up — a README
claiming a verified deployment that has never run once is the kind of thing an interviewer checks.

**Status:** ready-for-agent

- [ ] Architecture diagram in the README, rendering correctly on GitHub
- [ ] The queue's purpose stated as independent scaling, in one sentence, near the top
- [ ] The three env-var seams named, with what each swaps between
- [ ] Deployment target, cost, and the explicit "local by choice" note
- [ ] Existing local-setup instructions still accurate and still present
- [ ] `k8s/README.md` linked rather than duplicated — the runbook stays in one place
