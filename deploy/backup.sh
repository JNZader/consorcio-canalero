#!/usr/bin/env bash
# INF-02 / INF-13: daily offsite backup. Writes a success stamp only if both
# compose backup services exit 0. The age check (backup-age-check.sh) alerts
# when that stamp is older than 26 h.
set -euo pipefail

STACK_DIR="${STACK_DIR:-/home/javier/stacks/consorcio}"
STAMP_FILE="${BACKUP_STAMP_FILE:-${STACK_DIR}/logs/backup-last-success}"
COMPOSE_FILE="${COMPOSE_FILE:-${STACK_DIR}/docker-compose.yml}"

cd "${STACK_DIR}"
docker compose -f "${COMPOSE_FILE}" --profile backup run --rm backup-postgres
docker compose -f "${COMPOSE_FILE}" --profile backup run --rm backup-volumes

mkdir -p "$(dirname "${STAMP_FILE}")"
date -u +%Y-%m-%dT%H:%M:%SZ > "${STAMP_FILE}"
echo "backup OK stamp=${STAMP_FILE}"
