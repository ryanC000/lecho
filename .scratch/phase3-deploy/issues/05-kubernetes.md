# 05 — Kubernetes deployment

**What to build:** The app and worker images from 03/04 run as Kubernetes workloads, so the
deployed topology is a real orchestrated cluster rather than `docker compose`. Scope: a
`Deployment` for the API and a second one for the worker (independently replicable — that
separation is the point), a `Service` plus `Ingress` fronting the API, and `ConfigMap`/`Secret`
objects supplying the env vars the seams from 01–04 already read (`DATABASE_URL`,
`STORAGE_BACKEND`, `S3_BUCKET`, `AWS_REGION`, `QUEUE_BACKEND`, the queue URL). Manifests live under
`k8s/` and are plain YAML — no Helm chart unless something actually needs templating. Liveness and
readiness probes on the API; the worker needs neither (it polls, it doesn't serve).

The worker `Deployment` is what makes the architecture legible: scaling audio processing means
`replicas: N` on that object alone, with no effect on API capacity. That is the whole reason the
queue in 04 exists.

**Deploy target:** local `kind` or `k3s`, pointed at **real** AWS S3 and SQS. Real Kubernetes
objects, real AWS services, zero cluster cost. EKS is deliberately not required — the manifests are
portable, and running them on a managed cluster is a credit-card decision, not an engineering one.
Record which cluster the verification run used.

**AWS resources needed:** an S3 bucket, an SQS queue + DLQ, and an IAM user/policy scoped to
exactly those two ARNs. Create them however is fastest — console is fine. A ~40-line Terraform
file is optional and worth it only for `terraform destroy`, which is the reliable way to avoid
leaving billable resources running after a demo. Either way: no credentials, real `.tfvars`, or
state files in git, and the k8s `Secret` holding the AWS keys must not be committed with real
values (ship a `.example` and document the `kubectl create secret` command).

**Blocked by:** 03 (images), 04 (the worker split and queue this deploys).

**Status:** blocked

- [ ] `kubectl apply -k k8s/` brings up API and worker Deployments; both reach `Running`
- [ ] API is reachable through the Service/Ingress and serves `/`
- [ ] A recording uploaded through the Ingress is scored by a **worker pod**, not the API pod
      (prove it from the worker pod's logs)
- [ ] `kubectl scale deploy/worker --replicas=3` adds consumers without touching the API
- [ ] Config comes entirely from ConfigMap/Secret — no image rebuild to change bucket or queue
- [ ] No secrets committed; the Secret is created out-of-band from a documented command

## Dropped from the original scope

This ticket previously specified **Terraform provisioning ECS Fargate**. Kubernetes replaces ECS as
the container host. Full infrastructure-as-code (RDS, IAM roles, container hosting) is deferred —
it is not a prerequisite for anything else in this phase, and the resources this needs are small
enough to create by hand. Revisit if the deployment ever needs to be reproducible from clean.
