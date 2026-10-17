#!/usr/bin/env bash
# INF-02: monthly restore drill. Refuses live database names.
#
# Default mode prints the procedure and exits 0 after the name check.
# --execute runs it against RESTORE_DRILL_DATABASE (never the live DB).
# Record the timing in docs/runbooks/infra-cicd-v6.md under "Último simulacro".
set -euo pipefail

LIVE_NAMES=(
  consorcio
  consorcio_canalero
  postgres
  template0
  template1
)
TARGET="${RESTORE_DRILL_DATABASE:-consorcio_restore_drill}"
STACK_DIR="${STACK_DIR:-/home/javier/stacks/consorcio}"
POSTGRES_SERVICE="${POSTGRES_SERVICE:-postgres}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-shared-postgres}"

refuse_live_target() {
  local name
  for name in "${LIVE_NAMES[@]}"; do
    if [[ "${TARGET}" == "${name}" ]]; then
      echo "refusing to restore into live database: ${TARGET}" >&2
      exit 2
    fi
  done
  if [[ ! "${TARGET}" =~ ^[a-z_][a-z0-9_]{0,62}$ ]]; then
    echo "refusing unsafe database name: ${TARGET}" >&2
    exit 2
  fi
}

if [[ "${1:-}" == "--check-target" ]]; then
  TARGET="${2:?database name required}"
  refuse_live_target
  echo "target ok: ${TARGET}"
  exit 0
fi

refuse_live_target

cat <<EOF
Simulacro de restore hacia '${TARGET}' (no es una base de producción).
RTO objetivo: 4 h. RPO: 24 h (backup diario; alerta a las 26 h).

1. Confirmar un backup fresco:
     ${STACK_DIR}/logs/backup-last-success
2. Bajar el último dump cifrado a un directorio scratch (ver docs/RUNBOOK.md §3.6).
3. Verificar el sidecar .sha256 antes de descifrar.
4. Crear la base de simulacro y restaurar ahí, nunca en la base viva.
5. Contar filas (denuncias, canales) y anotar la duración.
6. DROP DATABASE ${TARGET} al terminar.

EOF

if [[ "${1:-}" != "--execute" ]]; then
  echo "Modo lectura. Para ejecutarlo: RESTORE_DRILL_DATABASE=${TARGET} $0 --execute"
  exit 0
fi

if [[ "${CONFIRM_RESTORE_DRILL:-}" != "restore-drill" ]]; then
  echo "set CONFIRM_RESTORE_DRILL=restore-drill to execute" >&2
  exit 2
fi

cd "${STACK_DIR}"
if docker compose config --services 2>/dev/null | grep -qx "${POSTGRES_SERVICE}"; then
  # shellcheck disable=SC2016
  docker compose exec -T "${POSTGRES_SERVICE}" \
    psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-consorcio}" -d postgres \
    -c "DROP DATABASE IF EXISTS \"${TARGET}\";" \
    -c "CREATE DATABASE \"${TARGET}\";"
elif docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "${POSTGRES_CONTAINER}"; then
  # shellcheck disable=SC2016
  docker exec -i "${POSTGRES_CONTAINER}" \
    psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-consorcio}" -d postgres \
    -c "DROP DATABASE IF EXISTS \"${TARGET}\";" \
    -c "CREATE DATABASE \"${TARGET}\";"
else
  echo "service '${POSTGRES_SERVICE}' is not in this compose, and container '${POSTGRES_CONTAINER}' was not found" >&2
  echo "docker-compose.prod.yml keeps Postgres outside the stack (shared-postgres)." >&2
  echo "Create ${TARGET} with docker exec against that container. See docs/runbooks/infra-cicd-v6.md." >&2
  exit 2
fi
echo "created ${TARGET}; continue with the decrypt/psql steps in docs/RUNBOOK.md §3.6 pointed at this database, then DROP it"
