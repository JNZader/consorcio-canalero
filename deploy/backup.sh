#!/usr/bin/env bash
# INF-02 / INF-13: daily offsite backup. Writes a success stamp only if both
# compose backup services exit 0. The age check (backup-age-check.sh) alerts
# when that stamp is older than 26 h.
set -euo pipefail

STACK_DIR="${STACK_DIR:-/home/javier/stacks/consorcio}"
STAMP_FILE="${BACKUP_STAMP_FILE:-${STACK_DIR}/logs/backup-last-success}"
COMPOSE_FILE="${COMPOSE_FILE:-${STACK_DIR}/docker-compose.yml}"

cd "${STACK_DIR}"
COMPOSE_ENV_ARGS=()
if [[ -f "${STACK_DIR}/.env" ]]; then
  COMPOSE_ENV_ARGS+=(--env-file "${STACK_DIR}/.env")
fi
DIGEST_ENV_FILE="${DEPLOY_DIGEST_ENV:-${STACK_DIR}/deploy-digests.env}"
if [[ -f "${DIGEST_ENV_FILE}" ]]; then
  COMPOSE_ENV_ARGS+=(--env-file "${DIGEST_ENV_FILE}")
fi

docker compose "${COMPOSE_ENV_ARGS[@]}" -f "${COMPOSE_FILE}" --profile backup run --rm backup-postgres
docker compose "${COMPOSE_ENV_ARGS[@]}" -f "${COMPOSE_FILE}" --profile backup run --rm backup-volumes

mkdir -p "$(dirname "${STAMP_FILE}")"
date -u +%Y-%m-%dT%H:%M:%SZ > "${STAMP_FILE}"
echo "backup OK stamp=${STAMP_FILE}"
