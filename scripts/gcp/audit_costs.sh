#!/bin/bash
# =============================================================================
# Audit Recurring GCP Costs
# =============================================================================
# Read-only. Reports the resources that bill by the hour whether or not anyone
# is using them -- the usual cause of a bill that does not track traffic.
#
# Usage:
#   ./scripts/gcp/audit_costs.sh
#   ./scripts/gcp/audit_costs.sh --project=my-project
#
# Nothing here mutates infrastructure; every command is a list or describe.
# =============================================================================

set -uo pipefail

PROJECT_ID="${PROJECT_ID:-biz2bricks-dev-v1}"
REGION="${REGION:-us-central1}"

while [[ $# -gt 0 ]]; do
    case $1 in
        --project=*) PROJECT_ID="${1#*=}"; shift ;;
        --region=*)  REGION="${1#*=}"; shift ;;
        --help|-h)
            echo "Usage: $0 [--project=PROJECT_ID] [--region=REGION]"
            exit 0
            ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

hdr() { echo ""; echo "=== $1 ==="; }

echo "Cost audit for project: $PROJECT_ID (region: $REGION)"

hdr "Cloud SQL instances"
echo "Watch for: a tier above db-f1-micro, REGIONAL availability (doubles cost),"
echo "and PRIMARY in the IP list (a public IPv4 is ~\$7.30/month, billed even"
echo "while the instance is stopped)."
gcloud sql instances list \
    --project="$PROJECT_ID" \
    --format="table(
        name,
        settings.tier,
        settings.availabilityType,
        settings.dataDiskSizeGb,
        settings.dataDiskType,
        settings.backupConfiguration.enabled,
        ipAddresses[].type.list(),
        state
    )" 2>&1 | sed 's/^/  /'

hdr "Serverless VPC Access connectors"
echo "Each connector runs >=2 always-on instances (~\$9-15/month) and is only"
echo "needed for PRIVATE Cloud SQL. Cloud Run's Direct VPC egress replaces it"
echo "at no cost. If this project connects over PUBLIC, any connector is waste."
gcloud compute networks vpc-access connectors list \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --format="table(name,network,minInstances,maxInstances,machineType,state)" 2>&1 | sed 's/^/  /'

hdr "Cloud Run services"
echo "Watch for: minScale above 0 (pays for an idle container 24/7) and"
echo "cpu-throttling=false (bills CPU outside request handling)."
gcloud run services list \
    --project="$PROJECT_ID" \
    --format="table(
        metadata.name,
        metadata.annotations['autoscaling.knative.dev/minScale']:label=MIN,
        spec.template.metadata.annotations['autoscaling.knative.dev/maxScale']:label=MAX,
        spec.template.metadata.annotations['run.googleapis.com/cpu-throttling']:label=THROTTLED,
        spec.template.spec.containers[0].resources.limits.cpu:label=CPU,
        spec.template.spec.containers[0].resources.limits.memory:label=MEM
    )" 2>&1 | sed 's/^/  /'

hdr "Artifact Registry repositories"
echo "Storage is \$0.10/GB/month beyond 0.5GB free and grows with every build"
echo "unless a cleanup policy is set. See setup_cleanup_policy.sh."
gcloud artifacts repositories list \
    --project="$PROJECT_ID" \
    --format="table(name.basename():label=REPO,format,location,sizeBytes.size(units_out=M):label=SIZE_MB)" 2>&1 | sed 's/^/  /'

hdr "Reserved static IP addresses"
echo "An IP reserved but not attached to anything still bills hourly."
gcloud compute addresses list \
    --project="$PROJECT_ID" \
    --format="table(name,region,address,status,users.len():label=ATTACHED)" 2>&1 | sed 's/^/  /'

hdr "Persistent disks not attached to an instance"
gcloud compute disks list \
    --project="$PROJECT_ID" \
    --filter="-users:*" \
    --format="table(name,zone.basename(),sizeGb,type.basename())" 2>&1 | sed 's/^/  /'

hdr "Next step"
cat <<'NEXT'
  For the authoritative number, the billing console breaks cost down by SKU:
    https://console.cloud.google.com/billing -> Reports
    Group by "SKU", filter to this project, set the range to last 30 days.

  That is the only view that says exactly where the money went; everything
  above just narrows down where to look.
NEXT
