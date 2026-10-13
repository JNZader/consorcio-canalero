#!/usr/bin/env bash
# INF-02: fail when the last successful backup stamp is missing or older than
# BACKUP_MAX_AGE_HOURS (default 26). systemd OnFailure notifies.
set -euo pipefail

STACK_DIR="${STACK_DIR:-/home/javier/stacks/consorcio}"
STAMP_FILE="${BACKUP_STAMP_FILE:-${STACK_DIR}/logs/backup-last-success}"
MAX_HOURS="${BACKUP_MAX_AGE_HOURS:-26}"

if [[ ! -f "${STAMP_FILE}" ]]; then
  echo "no backup stamp at ${STAMP_FILE}" >&2
  exit 1
fi

stamp_text="$(tr -d '[:space:]' < "${STAMP_FILE}")"
if [[ -z "${stamp_text}" ]]; then
  echo "empty backup stamp at ${STAMP_FILE}" >&2
  exit 1
fi

now="$(date -u +%s)"
then="$(date -u -d "${stamp_text}" +%s)"
age_hours="$(( (now - then) / 3600 ))"
if (( age_hours > MAX_HOURS )); then
  echo "backup stamp is ${age_hours}h old (max ${MAX_HOURS}h): ${stamp_text}" >&2
  exit 1
fi
echo "backup stamp age ${age_hours}h (${stamp_text})"
