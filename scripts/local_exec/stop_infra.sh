#!/usr/bin/env bash
# Stop the local development infrastructure.
#   ./stop_infra.sh          # stop containers, KEEP data
#   ./stop_infra.sh --wipe   # stop and DESTROY data volumes (asks first)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env.local"
[[ -f "$ENV_FILE" ]] && { set -a; source "$ENV_FILE"; set +a; }
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-unused-at-teardown}"

dc() { docker compose -f "$SCRIPT_DIR/docker-compose.infra.yml" --project-name b2blocal "$@"; }

if [[ "${1:-}" == "--wipe" ]]; then
    echo "This DESTROYS the local database and cache volumes. Data cannot be recovered."
    read -r -p "Type 'WIPE' to confirm: " c
    [[ "$c" == "WIPE" ]] || { echo "Aborted."; exit 1; }
    dc down -v
    echo "Stopped and volumes destroyed."
else
    dc down
    echo "Stopped. Data volumes kept — ./setup_infra.sh brings it back."
fi
