# 05 — Terraform infrastructure

**What to build:** The AWS stack the app now depends on is provisioned as code under `infra/`, so
`terraform apply` stands the whole thing up from clean and `terraform destroy` tears it down. Scope:
the S3 bucket (private, used by 02), the SQS queue + its dead-letter queue (04), an RDS Postgres
instance (01), the IAM roles/policies granting the app and worker least-privilege access to exactly
those resources, and container hosting for the app and worker images from 03/04 (ECS Fargate, or
document a lighter target if chosen). State backend and secrets handling are documented, not
committed — no credentials, `.tfvars` with real values, or state files enter git (extend
`.gitignore`). Outputs surface the queue URL, bucket name, and DB endpoint that the app and worker
consume as env vars, closing the loop with 01–04.

**Blocked by:** 01, 02, 03, 04 — Terraform provisions what those tickets taught the app to use.

**Status:** blocked

- [ ] `terraform apply` from clean provisions bucket, SQS + DLQ, RDS, IAM, and container services
- [ ] IAM policies are least-privilege (scoped to the specific bucket/queue ARNs, not `*`)
- [ ] No secrets, real `.tfvars`, or state files are committed; `.gitignore` updated
- [ ] Outputs feed the app/worker env vars (queue URL, bucket, DB endpoint) with no hand-editing
- [ ] `terraform destroy` removes every provisioned resource
