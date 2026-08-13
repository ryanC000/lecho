# Deploying L'Écho on Docker Desktop Kubernetes

Real Kubernetes objects against real AWS services, at zero cluster cost. The API
and the worker are the same image with different commands; the frontend is a
static bundle behind the same Ingress, so the whole app is served from one
origin.

```
Docker Desktop k8s (single node, x86_64, namespace: lecho)

  Ingress (nginx)  ->  http://localhost
    /practices  /jobs  /auth  /health   ->  api Service  ->  api pod
    everything else                     ->  frontend Service -> nginx pod
                                                 |
  worker pods  <--- long-poll SQS --------------+
      |
      +--> Supabase Postgres (session pooler) · AWS S3 · AWS SQS + DLQ
```

**Architecture constraint: x86_64 only.** `praat-parselmouth` publishes no Linux
aarch64 wheel, so an ARM node would have to build Praat's C++ from source.

---

## 1. AWS resources (console)

Created by hand — four resources, made once. Teardown checklist is at the bottom.

### S3 bucket

1. Create a bucket, default settings (Block Public Access **on** — the app serves
   audio through presigned URLs, never public objects).
2. **Add a CORS policy.** This is not optional and its absence is silent:
   `GET /practices/{id}/audio` redirects to a presigned S3 URL, and wavesurfer
   fetches that URL cross-origin. Without CORS the API looks perfectly healthy
   while every waveform fails to load.

   ```json
   [
     {
       "AllowedHeaders": ["*"],
       "AllowedMethods": ["GET"],
       "AllowedOrigins": ["http://localhost"],
       "ExposeHeaders": [],
       "MaxAgeSeconds": 3000
     }
   ]
   ```

### SQS queues

1. Create a **standard** queue `lecho-jobs-dlq` (the dead-letter queue) first.
2. Create a **standard** queue `lecho-jobs` with:
   - **Visibility timeout: 300s.** It must exceed the worst-case scoring time —
     DSP plus STT is seconds, but a cold model load plus a slow clip is not. Too
     short and a job still being scored gets handed to a second worker.
   - **Redrive policy:** dead-letter queue `lecho-jobs-dlq`, `maxReceiveCount` 3.
3. Copy the queue URL into `configmap.yaml` as `SQS_QUEUE_URL`.

### IAM user

Docker Desktop has no IRSA, so the pods authenticate with static keys. Scope them
to exactly these two resources — nothing here needs broader access:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::YOUR-BUCKET/*"
    },
    {
      "Effect": "Allow",
      "Action": ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage",
                 "sqs:GetQueueAttributes"],
      "Resource": "arn:aws:sqs:REGION:ACCOUNT:lecho-jobs"
    }
  ]
}
```

Create an access key for the user. It goes in the k8s Secret, never in the repo.

**Free-tier note:** SQS's 1M requests/month is always-free, but a worker
long-polling at 20s burns ~130k receives/month *per replica*. Three replicas left
running for a month is ~390k — under the limit, but don't leave them up. S3's 5GB
is free for 12 months on new accounts only.

## 2. Supabase

Create a free project, then take the connection string from
**Project Settings → Database → Connection string → Session pooler**:

```
postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

Rewrite the scheme for SQLAlchemy and require TLS:

```
postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
```

Three things that will each cost you an evening if skipped:

- **Use the session pooler, not the direct host.** `db.<ref>.supabase.co` is
  IPv6-only on the free tier and Docker Desktop cannot reach it.
- **Not the transaction pooler (port 6543) either.** It does not support prepared
  statements, which psycopg uses by default.
- **The free tier pauses after 7 days of inactivity.** Wake the project in the
  dashboard before a demo, or the first request hangs and readiness fails.

The API creates its tables and runs the idempotent column migrations at startup
(`api/main.py` lifespan). The worker deliberately does not — schema has one owner.

## 3. Cluster prerequisites

Enable Kubernetes in Docker Desktop (**Settings → Kubernetes → Enable**), then
install an ingress controller — Docker Desktop, unlike minikube, ships none:

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.3/deploy/static/provider/cloud/deploy.yaml
kubectl -n ingress-nginx get svc          # EXTERNAL-IP should read "localhost"
```

Use the **`provider/cloud`** manifest: it creates a `LoadBalancer` Service, which
is what Docker Desktop binds to `localhost:80`.

If the EXTERNAL-IP stays `<pending>` or the port never binds, something else on
Windows holds port 80 — usually IIS or the World Wide Web Publishing Service.
`netstat -ano | findstr :80` names the process.

## 4. Build and deploy

Docker Desktop's Kubernetes shares the Docker image store, so a local build is
immediately usable by the cluster — no registry, no push.

```bash
docker build -t lecho:dev ./backend
docker build -t lecho-frontend:dev ./frontend
```

The frontend build takes `VITE_API_BASE=""` by default, which makes the bundle
issue relative URLs so it is not pinned to a hostname. To enable Google sign-in,
pass the client ID at build time (Vite bakes it in — it cannot come from the
ConfigMap):

```bash
docker build -t lecho-frontend:dev --build-arg VITE_GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com ./frontend
```

Then edit `configmap.yaml` (bucket, queue URL, region), create the Secret, and
apply:

```bash
kubectl apply -f k8s/namespace.yaml

kubectl create secret generic lecho-secrets -n lecho \
  --from-literal=DATABASE_URL='postgresql+psycopg://...?sslmode=require' \
  --from-literal=JWT_SECRET_KEY='<long random value>' \
  --from-literal=GOOGLE_CLIENT_ID='<id>.apps.googleusercontent.com' \
  --from-literal=AWS_ACCESS_KEY_ID='AKIA...' \
  --from-literal=AWS_SECRET_ACCESS_KEY='...'

kubectl apply -k k8s/
kubectl get pods -n lecho -w
```

Seed the database once (drops every table, so never automate it):

```bash
kubectl exec -n lecho deploy/api -- python -m tools.seed
```

## 5. Google sign-in

The OAuth client's authorised JavaScript origins are per-environment, and Google
treats `http://localhost` (what the Ingress serves) as a **different origin** from
`http://localhost:5173` (the Vite dev server). Add **both** in the Google Cloud
console, or sign-in works in dev and 400s in the cluster.

## 6. Verify

```bash
kubectl get pods -n lecho                     # api, worker, frontend all Running
```

1. Open <http://localhost> — the library loads and a practice's **waveform
   renders** (that last part is what proves the S3 CORS policy is right).
2. Sign in, record a take, submit it.
3. `kubectl logs -n lecho deploy/worker` shows `scoring started` then `-> SUCCESS`;
   `kubectl logs -n lecho deploy/api` shows the job created and **no** scoring —
   that separation is the whole point of the queue.
4. `kubectl scale deploy/worker -n lecho --replicas=3` adds consumers; the API is
   untouched. Scale back to 1 afterwards (memory, and SQS request volume).
5. Change `S3_BUCKET` in the ConfigMap, `kubectl rollout restart deploy/api -n lecho`
   — config changes without an image rebuild.

If worker pods get OOMKilled at 3 replicas, raise Docker Desktop's memory:
`%UserProfile%\.wslconfig` → `[wsl2]` / `memory=6GB`, then restart Docker Desktop.
Each worker holds the whisper model at roughly 1GB resident.

## 7. Teardown

The cluster costs nothing and can stay. The AWS resources should not:

```bash
kubectl delete -k k8s/
kubectl delete namespace lecho
```

- [ ] S3 — **empty the bucket**, then delete it (a non-empty bucket will not delete)
- [ ] SQS — delete `lecho-jobs` and `lecho-jobs-dlq`
- [ ] IAM — delete the access key, then the user
- [ ] Supabase — pause or delete the project

## Notes

- **No secrets in this directory.** `secret.example.yaml` documents the shape and
  is not part of `kustomization.yaml`; the real Secret is created from the command
  above.
- **No Terraform.** Four resources created once, with no need to reproduce them
  elsewhere — and Kubernetes itself cannot provision AWS resources without adding
  Crossplane or ACK, which is far more machinery than it would manage.
- **Ingress, not LoadBalancer per service.** On a managed cloud provider every
  Ingress provisions a billed load balancer (~$10–12/mo). Docker Desktop maps it
  to localhost for free, and the manifests move to a real cluster unchanged.
