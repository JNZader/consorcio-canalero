#!/usr/bin/env bash
#
# Weekly refresh of the geo data ETLs, run ON THE HOST of the deployment box.
#
# WHY THIS EXISTS
#   The canal data on the box went 2.5 months stale because every ETL was run by
#   hand. This script is the whole periodic refresh, in dependency order, with one
#   log line per step and a non-zero exit if ANY step failed — so the systemd
#   timer that drives it (`etl-refresh.timer`, Sundays 03:00) turns a silent drift
#   into a failed unit you can see in `systemctl status`.
#
# WHAT IT RUNS, AND WHY ONLY THESE
#   1. load_canales_consorcio      curated canal registry (canal_consorcio)
#   2. generate_canal_catchments   upstream basin per canal — MUST run AFTER (1):
#                                  it iterates canal_consorcio and FKs onto it
#   3. load_suelos_catastro        soils + REFRESH MATERIALIZED VIEW mv_suelos_por_zona
#                                  (independent of 1/2; last because it is cheap)
#
#   DELIBERATELY EXCLUDED:
#   * `scripts/etl_canales`, `scripts/etl_pilar_verde`, `scripts/etl_escuelas` —
#     offline KMZ -> static GeoJSON converters. They read KMZ files from the
#     operator's machine and write committed assets under `consorcio-web/public/`.
#     Neither the inputs nor the outputs exist on the box; they are a manual,
#     source-driven step, not a periodic refresh.
#   * `generate_chirps_normals` — its own docstring says it: the normals are STATIC
#     reference data that change only when the 1991-2020 period or the consorcio
#     extent changes. "There is no scheduled job and none is wanted." Re-running it
#     mints a fresh `version` over identical pixels and appends 13 geo_layers rows.
#
# NO --force, ON PURPOSE
#   `generate_canal_catchments` resumes by `version` = the id of the flow_dir layer
#   pointer. Unchanged pointer -> every stored catchment is SKIPPED, which is
#   exactly right for a weekly refresh: the expensive watershed delineation only
#   re-runs when the terrain input actually changed, and new/failed canals are
#   still picked up. `--force` exists for CAP changes (caps live outside the
#   version key) and is an operator decision, not a cron one — see README-etl-cron.md.
#
# IDEMPOTENCE
#   Every step converges on re-run: (1) UPSERTs on the string id, (2) resumes by
#   version, (3) is a DELETE+insert inside one transaction. Running this script
#   twice in a row is a no-op the second time (modulo the matview refresh).
#
# KNOWN GAPS (documented in deploy/README-etl-cron.md, not silently ignored)
#   * A failed run is visible in `systemctl status` and in the journal, but nothing
#     NOTIFIES anyone. No OnFailure= hook yet — see the README.
#   * A step that hangs is killed locally, but the python process inside the
#     container survives it. See the TIMEOUT branch below.
#
# Usage:  ./etl-refresh.sh            # normal run
#         STACK_DIR=/other ./etl-refresh.sh
#
# Environment overrides:
#   STACK_DIR               compose project dir            (default ~/stacks/consorcio)
#   ETL_SERVICE             container to exec into         (default geo-worker)
#   ETL_LOG_DIR             where run logs go               (default $STACK_DIR/logs/etl)
#   ETL_LOG_RETENTION_DAYS  purge logs older than this, 0=off        (default 90)
#   ETL_STACK_WAIT_S        how long to wait for the stack           (default 300)
#   ETL_STACK_POLL_S        seconds between stack polls              (default 10)
#   ETL_STEP_TIMEOUT_S      per-step wall-clock ceiling              (default 2100)
set -Eeuo pipefail

#: Directory holding the deployment's docker-compose.yml + .env (see DEPLOY.md).
STACK_DIR="${STACK_DIR:-$HOME/stacks/consorcio}"
#: The container the ETLs run in. NOT `backend`, which is what the module
#: docstrings say: `generate_canal_catchments` needs the WhiteboxTools binary and
#: the GDAL stack, and only the geo image (Dockerfile.geo) pre-downloads WBT at
#: build time. The loaders are container-agnostic (same `app/` code, same DATABASE_URL),
#: so running the three in one container keeps the refresh a single dependency.
SERVICE="${ETL_SERVICE:-geo-worker}"
#: One log file per run, kept next to the stack.
LOG_DIR="${ETL_LOG_DIR:-$STACK_DIR/logs/etl}"
#: Purge run logs older than this. 0 disables the purge. Same knob shape as
#: `BACKUP_RETENTION_DAYS` in scripts/backup_postgres.sh.
LOG_RETENTION_DAYS="${ETL_LOG_RETENTION_DAYS:-90}"

#: How long to wait for `$SERVICE` to be up before giving up (seconds), and how
#: long between polls. See `wait_for_stack` for why this exists at all.
STACK_WAIT_S="${ETL_STACK_WAIT_S:-300}"
STACK_POLL_S="${ETL_STACK_POLL_S:-10}"

#: Per-step wall-clock ceiling (seconds). The arithmetic is deliberate and must
#: stay under the unit's `TimeoutStartSec=2h`: 300 s of stack wait + 3 steps x
#: 2100 s = 110 min < 120 min, so a hung step is reported by THIS script (which
#: can name the module) instead of by systemd killing the whole run.
STEP_TIMEOUT_S="${ETL_STEP_TIMEOUT_S:-2100}"
#: Exit code GNU `timeout` uses when it had to kill the command.
readonly TIMEOUT_EXIT=124

RUN_TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="$LOG_DIR/etl-refresh-$RUN_TS.log"

#: ETL modules, in dependency order. Order is load-bearing: catchments AFTER canales.
ETL_MODULES=(
  "app.domains.geo.etl.load_canales_consorcio"
  "app.domains.geo.etl.generate_canal_catchments"
  "app.domains.geo.etl.load_suelos_catastro"
)

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE"
}

#: True while `$SERVICE` has a running container in this compose project.
service_is_running() {
  docker compose ps --status running --format '{{.Service}}' 2>/dev/null \
    | grep -qx "$SERVICE"
}

wait_for_stack() {
  # WHY THIS LOOP EXISTS (the catch-up race, seen in production).
  # `Persistent=true` is the whole point of the timer: if the box was off on
  # Sunday, systemd fires the unit at the next boot. But at boot the stack is not
  # up yet — geo-worker waits on postgres being HEALTHY and on the migrate job
  # completing, which is tens of seconds to minutes. The unit only orders itself
  # after docker.service (the DAEMON), which is ready long before the containers
  # are. Without this wait the catch-up run fires immediately, all three steps
  # fail on "service not running", `Restart=no` means nothing retries, and the
  # refresh we skipped is skipped AGAIN for another week — the exact failure the
  # timer was built to prevent.
  local waited=0
  while ! service_is_running; do
    if [[ $waited -ge $STACK_WAIT_S ]]; then
      log "FATAL service=$SERVICE not running after ${waited}s — the stack never came up."
      log "FATAL check it with: cd $STACK_DIR && docker compose ps"
      return 1
    fi
    log "WAIT  service=$SERVICE not running yet (${waited}s/${STACK_WAIT_S}s) — retrying in ${STACK_POLL_S}s"
    sleep "$STACK_POLL_S"
    waited=$((waited + STACK_POLL_S))
  done
  log "READY service=$SERVICE running after ${waited}s"
  return 0
}

purge_old_logs() {
  [[ "$LOG_RETENTION_DAYS" -gt 0 ]] || return 0
  local purged
  purged=$(find "$LOG_DIR" -maxdepth 1 -type f -name 'etl-refresh-*.log' \
    -mtime "+$LOG_RETENTION_DAYS" -print -delete 2>/dev/null | wc -l || true)
  # ^ || true: bajo pipefail+errexit, un find no-cero (log de otro uid, EACCES
  #   transitorio) haria fallar la ASIGNACION y abortar la corrida ENTERA antes
  #   del primer paso de ETL. La limpieza de logs jamas debe costar el refresh.
  [[ "$purged" -gt 0 ]] && log "PURGE removed=$purged retention_days=$LOG_RETENTION_DAYS"
  return 0
}

main() {
  # STACK_DIR is checked BEFORE anything creates directories: LOG_DIR defaults to
  # a path INSIDE STACK_DIR, so an `mkdir -p` first would silently create the very
  # directory whose absence this guard is meant to report, and the guard could
  # never fire on the default configuration.
  if [[ ! -d "$STACK_DIR" ]]; then
    printf 'FATAL stack_dir=%s does not exist\n' "$STACK_DIR" >&2
    return 1
  fi
  mkdir -p "$LOG_DIR"
  : >"$LOG_FILE"
  cd "$STACK_DIR"

  log "START stack_dir=$STACK_DIR service=$SERVICE steps=${#ETL_MODULES[@]}"
  purge_old_logs
  wait_for_stack || { log "END   result=FAILED reason=stack-not-up log=$LOG_FILE"; return 1; }

  local failed=0 module status
  for module in "${ETL_MODULES[@]}"; do
    log "STEP  module=$module"
    # `-T` because there is no TTY under systemd. The exit code captured here is
    # the MODULE's own (docker compose exec propagates it), never a pipe's:
    # everything is appended to the log with `>>`, deliberately not piped.
    set +e
    timeout "$STEP_TIMEOUT_S" docker compose exec -T "$SERVICE" python -m "$module" \
      >>"$LOG_FILE" 2>&1
    status=$?
    set -e
    if [[ $status -eq $TIMEOUT_EXIT ]]; then
      # HONEST about what this does NOT do: `timeout` kills the local `docker
      # compose exec` CLIENT. `docker compose exec` does not forward the signal to
      # the process inside the container, so the python ETL may still be running
      # in `$SERVICE` — holding DB locks and, worse, still writing. There is no
      # clean fix without redesigning the invocation (a `docker exec`-side PID we
      # can kill, or moving the schedule into the container). Until then the log
      # must at least not lie about it.
      log "TIMEOUT module=$module after ${STEP_TIMEOUT_S}s — ATTENTION: the process may STILL BE RUNNING inside the container (docker compose exec does not propagate the signal)."
      log "TIMEOUT check it with: cd $STACK_DIR && docker compose top $SERVICE"
    fi
    log "DONE  module=$module exit=$status"
    if [[ $status -ne 0 ]]; then
      # Keep going: the steps are independent enough that a broken loader must not
      # hide the state of the rest, and the final exit still reports the failure.
      failed=$((failed + 1))
    fi
  done

  if [[ $failed -ne 0 ]]; then
    log "END   result=FAILED failed_steps=$failed log=$LOG_FILE"
    return 1
  fi
  log "END   result=OK log=$LOG_FILE"
  return 0
}

main "$@"
