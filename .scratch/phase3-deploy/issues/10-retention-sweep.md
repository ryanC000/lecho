# 10 — Nothing ever acts on `expires_at`

**What to build:** A job that deletes expired user recordings from storage and their rows from the
database, and a Kubernetes `CronJob` to run it. The retention half of the lifecycle is already
implemented and has been since Phase 1 — the *expiry* half does not exist at all.

Today: [jobs.py](../../../backend/api/routes/jobs.py) stamps every user recording with
`expires_at = utcnow() + RETENTION_DAYS`, `AudioAsset.expires_at` is a real column
([models.py](../../../backend/infra/models.py)), and `job_gates.RETENTION_DAYS = 30` cites
"PRD Section 4 storage lifecycle". Grep the backend for reads of `expires_at` and there are none.
Every upload is written, stamped with a promise, and kept forever.

**Why it matters now and not before:** on local disk this was an untidy `backend/storage/`
directory. On the deployment it is an S3 bucket against a **5GB free tier that expires after 12
months on a new account**, filling with 30-day-old audio nobody can reach. It is also a stated
privacy property of the product that is currently false.

The delete path already exists — `storage.delete(key)` — so this is a query, a loop, and a
manifest. Order matters: delete the object first, then the row. A row deleted before its object
orphans the object with no key left to find it by; an object deleted before its row leaves a row
whose `exists()` is false, which the worker already handles.

    # sketch
    for asset in db.query(AudioAsset).filter(
        AudioAsset.expires_at < utcnow(), AudioAsset.role == "USER_RECORDING"
    ):
        storage.delete(asset.storage_key)
        db.delete(asset)

**Scope it to `USER_RECORDING`.** Native reference clips are ingested with `expires_at=None`
([clip_ingest.py](../../../backend/ingest/clip_ingest.py) defaults it), but a filter on role rather
than on null-ness is the safer expression of the intent — deleting the natives would silently break
every practice, and it is exactly the bug a careless `expires_at < now()` would introduce if a
future ingest ever stamped one.

A `CronJob` is also the one Kubernetes workload type the deployment does not otherwise
demonstrate, sitting alongside the two Deployments and the Ingress.

**Found during:** phase3-deploy 05, auditing what the free tier actually accumulates.

**Blocked by:** nothing — the storage seam and the column both exist. Independent of 04/05/07/08.

**Status:** ready-for-agent

- [ ] `python -m tools.expire_assets` (or similar) deletes expired `USER_RECORDING` objects and
      rows, and is idempotent — a second run is a no-op
- [ ] Native reference clips are never deleted, whatever their `expires_at`
- [ ] The object is deleted before its row, so a mid-run failure cannot orphan storage
- [ ] Dry-run flag that reports what it would delete without deleting it
- [ ] `k8s/cronjob.yaml` runs it daily, reusing the same image and ConfigMap/Secret
- [ ] Tests cover: an expired user recording goes, an unexpired one stays, a native stays
