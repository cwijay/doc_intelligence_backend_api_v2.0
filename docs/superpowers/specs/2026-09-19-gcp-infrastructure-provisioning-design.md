# GCP Infrastructure Provisioning — Design

**Date:** 2026-09-19
**Status:** Approved, not yet provisioned
**Scope:** Stand up the `doc_intelligence_backend_api` service on GCP from scratch

## Context

No infrastructure exists yet. An audit on 2026-09-19 confirmed that none of the
five accessible projects contains a Cloud SQL instance, Cloud Run service, GKE
cluster, Memorystore instance, or Compute VM. The repo's deploy tooling
(`deploy.sh`, `cloudbuild.yaml`, the `biz2bricks_infra` CLI) has therefore never
run against live resources.

The driving constraint is cost. A previous ~$60/month bill prompted this work.
That bill is **not** explained by this application, and finding its true source
is tracked separately (see Out of Scope).

## Target

Project `biz2bricks-dev-v1`, region `us-central1`, billing account
`01BFBA-189CAF-F8E852` (verified open).

### Already exists — reuse

| Resource | Detail |
|---|---|
| GCS bucket | `biz2bricks-dev-v1-document-store`, US-CENTRAL1, uniform bucket-level access |
| Service account | `document-intelligence-api-sa@biz2bricks-dev-v1.iam.gserviceaccount.com` |
| Enabled APIs | sqladmin, run, cloudbuild, artifactregistry, secretmanager, storage, compute |

### To create

| Resource | Configuration |
|---|---|
| Cloud SQL | PostgreSQL, `db-f1-micro`, ZONAL, 10GB SSD, public IP, **no authorized networks** |
| Secret Manager | `JWT_SECRET_KEY`, `DATABASE_PASSWORD` — neither exists today |
| Artifact Registry | Docker repo `document-intelligence` in us-central1 |
| Cloud Run | `document-intelligence-api-dev`, min-instances 0, 1 vCPU / 1GiB |

## Cost model

| Item | Monthly |
|---|---|
| Cloud SQL `db-f1-micro`, ZONAL, 10GB SSD | ~$9.40 |
| Cloud Run (scale-to-zero, within free tier) | $0 |
| Cloud Build (within free tier) | $0 |
| Artifact Registry (with cleanup policy) | ~$0.25 |
| GCS + Secret Manager | ~$0.25 |
| **Total** | **~$10** |

SSD over HDD is deliberate: $0.80/month more for materially better demo
responsiveness.

## Decisions

**Cloud SQL over serverless Postgres.** Neon's free tier would be $0 and its
scale-to-zero suits a demo workload that idles most of the week. Cloud SQL was
chosen anyway for GCP-native consistency, no third-party dependency, and because
the provisioning tooling already exists. Accepted cost: ~$113/year to keep a
demo database warm.

**Public IP, not private.** `servicenetworking` is not enabled, and private IP
would additionally require Direct VPC egress on Cloud Run. It would also save
nothing: a public IPv4 is free while the instance runs and only bills
(~$0.010/hr) once stopped. The Cloud SQL connector authenticates via IAM over
TLS regardless. No authorized networks are configured, so the instance is not
reachable from the internet by password alone.

**Shared-core tier.** `db-f1-micro` carries no SLA and is ineligible for
committed-use discounts. Acceptable pre-launch.

**One container registry, not two.** `deploy.sh:497` pushes to
`gcr.io/$project_id/$service_name` while `cloudbuild.yaml` pushes to Artifact
Registry `document-intelligence`. Left alone, the manual and CI deploy paths
would populate two separate registries, both accumulating images and both
needing cleanup policies. `deploy.sh` is repointed at the Artifact Registry
repo so there is a single image store. This requires adding
`gcloud auth configure-docker us-central1-docker.pkg.dev` to
`build_and_push_image`, which currently runs a bare `docker push` that would
fail against Artifact Registry.

## Deferred — required before real user data

These are conscious trade-offs for a demo environment, not oversights:

1. **Automated backups are off.** `biz2bricks_infra/provision/provisioner.py:144`
   passes `--no-backup`. Enable backups and PITR before any customer data lands.
2. **The database password is weak** (`Pa**Word01`, carried over from the existing
   `.env.production`). Retained by explicit decision. Rotate before launch.
   Mitigated meanwhile by the no-authorized-networks posture above.
3. **No SLA.** Moving to `db-g1-small` or larger is required for a production
   commitment.

## Gaps in existing tooling

`biz2bricks provision full-setup` runs Cloud SQL, GCS, service account, and
secrets. It does **not** create an Artifact Registry repository, and
`cloudbuild.yaml` pushes to `us-central1-docker.pkg.dev/$PROJECT_ID/document-intelligence/backend-api`.
The repo must be created out of band or the first build fails. Once `deploy.sh`
is repointed (see Decisions), both deploy paths target this one repo.

Separately, `cloudbuild.yaml` references service account
`727735128283-compute@developer.gserviceaccount.com`, which belongs to project
`biz2bricksv1`, not `biz2bricks-dev-v1` (project number `726919062103`). This is
corrected as part of this work.

## Sequence

1. Store `JWT_SECRET_KEY` and `DATABASE_PASSWORD` in Secret Manager
2. Create the Artifact Registry repo `document-intelligence`; apply the
   committed cleanup policy
3. `biz2bricks provision full-setup` — Cloud SQL, bucket, service account, IAM
4. Repoint `deploy.sh` at Artifact Registry and add the `configure-docker` step
5. Correct the service account in `cloudbuild.yaml`
6. Deploy via `./deploy.sh --deploy`
7. Verify

Steps 1-3 create infrastructure and cost money. Steps 4-5 are repo changes and
are reviewable before anything is deployed.

## Verification

- `/health` returns 200
- `/status` reports PostgreSQL and GCS both reachable
- Tables exist — `DatabaseManager._ensure_tables` creates them on first boot
- A document upload round-trips to GCS
- `scripts/gcp/audit_costs.sh` shows exactly one Cloud SQL instance at
  `db-f1-micro`/ZONAL, one Cloud Run service at min-instances 0, and no VPC
  connectors

## Out of scope

The frontend Cloud Run service, the `doc_intelligence_ai_v3.0` service, the
other four GCP projects, and the ~$60/month bill whose source remains
unidentified. Two leads: project `biz2bricksv1` bills to a second billing
account (`015507-E08C96-E8EB69`) not readable by the `cwijay@` login, and
`dynamic-reef-473916-n3` has an Anthos / Config Controller stack enabled.
