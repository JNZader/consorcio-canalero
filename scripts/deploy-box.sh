#!/usr/bin/env bash
# =============================================================================
# deploy-box.sh — update the single Consorcio box from origin/main
# =============================================================================
# Runs ON the box (/home/javier/stacks/consorcio). The laptop does not build
# these images. This is the local-build path in docs/RUNBOOK.md §2.2, with the
# guards the bare `git pull` does not have.
#
# What it does, in order, and it stops at the first failure:
#   1. Preflight. The stack dir is a git checkout and consorcio-backend is up.
#   2. Save docker-compose.yml. That file is the box override (production
#      target, no --reload, REDIS_PASSWORD required). origin/main is still the
#      development compose. The script never takes compose from main.
#   3. git fetch origin main.
#   4. Dirty tree. Anything other than docker-compose.yml and untracked
#      backups/ aborts, unless ALLOW_DIRTY_TREE=1. That flag discards the
#      extra local edits. It still restores the saved compose afterwards.
#   5. pg_dump of the running Postgres, before git or docker change anything.
#   6. Tag the four running images as :pre-<sha> so a bad boot has a name.
#   7. git reset --hard origin/main, then put the saved compose back.
#      The checkout itself runs under umask 022. umask 077 stays for the
#      dump and the compose copy: geo-worker bind-mounts gee-backend/app
#      and runs as uid 100, so a 600 tree makes every terrain tile 500,
#      and the public proxy turns that into a 204. The map goes flat.
#   8. docker compose up -d --build of backend, worker, celery-beat, geo-worker.
#   9. Wait until `python -m app.healthcheck` inside consorcio-backend exits 0.
#      A curl to 127.0.0.1:8000/health is the wrong probe: production rejects
#      that Host header, while the container healthcheck sends HEALTHCHECK_HOST.
#
# What it never does: alembic, GHCR push, webhook, frontend. Schema changes
# stay a separate, explicit step. A failed health check prints the rollback
# and does not run it.
#
# The hostname of this VPS is ubuntu-8gb-hel1-1. Biogas uses that string as
# its production abort, and biogas-* containers do run on this same machine.
# Consorcio identifies its stack by STACK_DIR. Every container_name in this
# compose must start with consorcio-. A biogas container on the host is a
# warning, not a reason to skip the consorcio build: `docker compose` here
# only receives the four consorcio services.
#
#   ALLOW_DIRTY_TREE=1 bash /home/javier/stacks/deploy-box.sh
# =============================================================================

set -euo pipefail

STACK_DIR="${STACK_DIR:-/home/javier/stacks/consorcio}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
BACKUP_MIN_BYTES="${BACKUP_MIN_BYTES:-102400}"
BACKUP_MIN_TABLES="${BACKUP_MIN_TABLES:-10}"
ALLOW_DIRTY_TREE="${ALLOW_DIRTY_TREE:-0}"
HEALTH_TIMEOUT_SECS="${HEALTH_TIMEOUT_SECS:-180}"
PG_CONTAINER="${PG_CONTAINER:-consorcio-postgres}"
SERVICES=(backend worker celery-beat geo-worker)
IMAGES=(consorcio-backend consorcio-worker consorcio-celery-beat consorcio-geo-worker)

PREVIOUS_SHA=""
TARGET_SHA=""
BACKUP_FILE=""
COMPOSE_SAVED=""
STACK_MUTATED=0

umask 077

log()      { echo "[$(date -u +%FT%TZ)] $*"; }
log_step() { echo; echo "[$(date -u +%FT%TZ)] ===== $* ====="; }
die() {
  echo >&2
  echo "[$(date -u +%FT%TZ)] ############################################" >&2
  echo "[$(date -u +%FT%TZ)] # DEPLOY ABORTADO" >&2
  echo "[$(date -u +%FT%TZ)] # $*" >&2
  echo "[$(date -u +%FT%TZ)] ############################################" >&2
  if [ "$STACK_MUTATED" -eq 1 ]; then
    print_rollback
  fi
  exit 1
}

print_rollback() {
  cat >&2 <<EOF

--------------------------------------------------------------------------
ROLLBACK (manual — este script no revierte solo)
--------------------------------------------------------------------------
SHA anterior : ${PREVIOUS_SHA:-<desconocido>}
SHA objetivo : ${TARGET_SHA:-<desconocido>}
Compose      : ${COMPOSE_SAVED:-<no se guardo>}
Dump         : ${BACKUP_FILE:-<no se llego a crear>}

Las imagenes previas quedaron tageadas :pre-${PREVIOUS_SHA:-<sha>} cuando
el tag existia. Para volver el arbol y reusar esas imagenes:

  cd "$STACK_DIR"
  cp "${COMPOSE_SAVED:-<compose-guardado>}" docker-compose.yml
  git reset --hard ${PREVIOUS_SHA:-<SHA_ANTERIOR>}
  cp "${COMPOSE_SAVED:-<compose-guardado>}" docker-compose.yml
  docker tag consorcio-backend:pre-${PREVIOUS_SHA:-<sha>} consorcio-backend
  docker tag consorcio-worker:pre-${PREVIOUS_SHA:-<sha>} consorcio-worker
  docker tag consorcio-celery-beat:pre-${PREVIOUS_SHA:-<sha>} consorcio-celery-beat
  docker tag consorcio-geo-worker:pre-${PREVIOUS_SHA:-<sha>} consorcio-geo-worker
  docker compose up -d --no-build backend worker celery-beat geo-worker

No corre alembic ni en el deploy ni en este rollback.
EOF
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "falta el comando '$1'"
}

allowed_dirt_line() {
  case "$1" in
    " M ${COMPOSE_FILE}"|"M  ${COMPOSE_FILE}"|"MM ${COMPOSE_FILE}") return 0 ;;
    "?? backups"|"?? backups/"*) return 0 ;;
    *) return 1 ;;
  esac
}

assert_tree_is_only_the_compose_override() {
  local line extra=0
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    if allowed_dirt_line "$line"; then
      continue
    fi
    extra=1
    log "dirty: $line"
  done < <(git status --porcelain)
  if [ "$extra" -eq 1 ] && [ "$ALLOW_DIRTY_TREE" != "1" ]; then
    die "el arbol tiene cambios ademas de ${COMPOSE_FILE}. No es un pull. Revisa, o vuelve a correr con ALLOW_DIRTY_TREE=1 si ya aceptaste descartarlos."
  fi
  if [ "$extra" -eq 1 ]; then
    log "ALLOW_DIRTY_TREE=1: esos cambios se descartan en el reset. ${COMPOSE_FILE} se restaura desde la copia."
  fi
}

save_compose() {
  local stamp dir
  [ -f "$COMPOSE_FILE" ] || die "no esta ${STACK_DIR}/${COMPOSE_FILE}"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  dir="${BACKUP_DIR}/compose"
  mkdir -p "$dir"
  COMPOSE_SAVED="${dir}/docker-compose.yml.${stamp}"
  cp -p "$COMPOSE_FILE" "$COMPOSE_SAVED"
  cp -p "$COMPOSE_FILE" "${dir}/docker-compose.yml.latest"
  log "compose guardado en ${COMPOSE_SAVED}"
}

backup_database() {
  local size tables partial
  docker inspect "$PG_CONTAINER" >/dev/null 2>&1 \
    || die "el container '$PG_CONTAINER' no esta. Sin base viva no hay backup, y sin backup no hay deploy."
  mkdir -p "$BACKUP_DIR"
  BACKUP_FILE="${BACKUP_DIR}/consorcio-predeploy-$(date -u +%Y%m%dT%H%M%SZ).dump"
  partial="${BACKUP_FILE}.partial"
  log "pg_dump -Fc -> ${BACKUP_FILE}"
  if ! docker exec "$PG_CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" -Fc -d "$POSTGRES_DB"' > "$partial"; then
    die "pg_dump fallo. No se toco el arbol ni las imagenes."
  fi
  size="$(wc -c < "$partial" | tr -d ' ')"
  if [ "$size" -lt "$BACKUP_MIN_BYTES" ]; then
    mv "$partial" "${BACKUP_FILE}.SOSPECHOSO"
    die "el dump pesa ${size} bytes, debajo de ${BACKUP_MIN_BYTES}. Archivo: ${BACKUP_FILE}.SOSPECHOSO"
  fi
  tables="$(docker exec -i "$PG_CONTAINER" pg_restore --list < "$partial" 2>/dev/null \
    | grep -c 'TABLE DATA' | tr -d ' ' || true)"
  tables="${tables:-0}"
  if [ "$tables" -lt "$BACKUP_MIN_TABLES" ]; then
    mv "$partial" "${BACKUP_FILE}.SOSPECHOSO"
    die "el dump lista ${tables} tablas, debajo de ${BACKUP_MIN_TABLES}. Archivo: ${BACKUP_FILE}.SOSPECHOSO"
  fi
  mv "$partial" "$BACKUP_FILE"
  log "backup OK: ${BACKUP_FILE} (${size} bytes, ${tables} tablas en el TOC)"
}

tag_running_images() {
  local image
  for image in "${IMAGES[@]}"; do
    if docker image inspect "$image" >/dev/null 2>&1; then
      docker tag "$image" "${image}:pre-${PREVIOUS_SHA}"
      log "tag ${image}:pre-${PREVIOUS_SHA}"
    else
      log "no hay imagen local ${image}; no se tagea"
    fi
  done
}

reset_tree_and_restore_compose() {
  local before after
  before="$(sha256sum "$COMPOSE_SAVED" | awk 'NR==1 {print $1}')"
  # 022 solo para el checkout. 077 en un archivo reescrito lo deja en 600,
  # y geo-worker (uid 100, bind mount de gee-backend/app) no lo puede leer.
  umask 022
  git reset --hard origin/main
  umask 077
  cp -p "$COMPOSE_SAVED" "$COMPOSE_FILE"
  after="$(sha256sum "$COMPOSE_FILE" | awk 'NR==1 {print $1}')"
  [ "$before" = "$after" ] || die "el compose restaurado no coincide con la copia ${COMPOSE_SAVED}"
  STACK_MUTATED=1
  TARGET_SHA="$(git rev-parse --short=8 HEAD)"
  log "HEAD ${TARGET_SHA}; compose del box restaurado"
}

build_services() {
  docker compose up -d --build "${SERVICES[@]}"
}

wait_for_health() {
  local deadline now
  deadline=$(( $(date +%s) + HEALTH_TIMEOUT_SECS ))
  while true; do
    if docker exec consorcio-backend python -m app.healthcheck >/dev/null 2>&1; then
      log "backend sano (python -m app.healthcheck)"
      return 0
    fi
    now="$(date +%s)"
    if [ "$now" -ge "$deadline" ]; then
      docker compose ps || true
      die "app.healthcheck no salio 0 en ${HEALTH_TIMEOUT_SECS}s"
    fi
    sleep 5
  done
}

main() {
  require_cmd git
  require_cmd docker
  require_cmd sha256sum
  cd "$STACK_DIR"
  [ -d .git ] || die "${STACK_DIR} no es un clon git"

  if docker ps --format '{{.Names}}' | grep -q '^biogas-'; then
    log "AVISO: hay containers biogas-* en este host. No se les pasa ningun comando."
  fi
  docker inspect consorcio-backend >/dev/null 2>&1 \
    || die "consorcio-backend no esta corriendo. No deployo un stack que no puedo identificar."
  local foreign
  foreign="$(docker compose config | awk '/container_name:/ {print $2}' | awk '!/^consorcio-/ {print}')"
  if [ -n "$foreign" ]; then
    die "el compose declara containers que no son de consorcio: ${foreign}"
  fi

  log_step "1/6 preflight"
  log "stack ${STACK_DIR} hostname $(hostname)"
  PREVIOUS_SHA="$(git rev-parse --short=8 HEAD)"
  log "HEAD actual ${PREVIOUS_SHA}"

  log_step "2/6 guardar compose"
  save_compose

  log_step "3/6 fetch y arbol"
  git fetch origin main
  assert_tree_is_only_the_compose_override

  log_step "4/6 backup de la base"
  backup_database

  log_step "5/6 reset a origin/main"
  tag_running_images
  reset_tree_and_restore_compose

  log_step "6/6 build y health"
  build_services
  wait_for_health

  log_step "DEPLOY OK"
  log "anterior ${PREVIOUS_SHA} -> ${TARGET_SHA}"
  log "dump ${BACKUP_FILE}"
  log "compose ${COMPOSE_SAVED}"
  log "sin alembic"
}

main "$@"
