#!/usr/bin/env bash
#
# Encrypted incremental backups of the file-backed Docker volumes using
# ``restic``. Default scope: denuncia photos + geo-data (DEM tiles,
# processed rasters, bundle imports). Configurable via env.
#
# Required env:
#   RESTIC_PASSWORD               — passphrase. Generate with
#                                   ``openssl rand -base64 48``.
#   RESTIC_REPOSITORY             — restic repo URI. Examples:
#                                     b2:my-bucket:/restic/consorcio
#                                     sftp:u123456@u123456.your-storagebox.de:/restic/consorcio
#                                     s3:s3.eu-central-1.amazonaws.com/my-bucket/consorcio
#   B2_ACCOUNT_ID, B2_ACCOUNT_KEY (when RESTIC_REPOSITORY starts with b2:)
#
# Optional:
#   BACKUP_SOURCES                — colon-separated list of paths to back
#                                   up; defaults to
#                                   ``/app/uploads:/data/geo``.
#   BACKUP_RETENTION_KEEP_DAILY=7
#   BACKUP_RETENTION_KEEP_WEEKLY=4
#   BACKUP_RETENTION_KEEP_MONTHLY=6
#
# Exit codes: 0 success; non-zero from the first failing restic step.

set -euo pipefail

: "${RESTIC_PASSWORD:?RESTIC_PASSWORD is required}"
: "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY is required}"

SOURCES_RAW="${BACKUP_SOURCES:-/app/uploads:/data/geo}"
IFS=':' read -ra SOURCES <<<"$SOURCES_RAW"

# Filter to paths that exist — backing up a missing source is a fast
# fail and aborts the run; we want partial coverage to still ship the
# parts we do have.
EXISTING_SOURCES=()
for src in "${SOURCES[@]}"; do
  if [ -d "$src" ]; then
    EXISTING_SOURCES+=("$src")
  else
    echo "[$(date -u +%FT%TZ)] skipping missing source: $src"
  fi
done

if [ "${#EXISTING_SOURCES[@]}" -eq 0 ]; then
  echo "ERROR: none of the BACKUP_SOURCES exist (${SOURCES_RAW})"
  exit 2
fi

# First run on a fresh repo needs ``restic init``. Detect by trying a
# stats call; on failure, init. ``restic`` returns non-zero for "repo
# does not exist" so we wrap the check.
if ! restic snapshots --quiet --no-lock >/dev/null 2>&1; then
  echo "[$(date -u +%FT%TZ)] initialising restic repo at ${RESTIC_REPOSITORY}"
  restic init
fi

echo "[$(date -u +%FT%TZ)] backing up: ${EXISTING_SOURCES[*]}"
restic backup --quiet --tag "consorcio" "${EXISTING_SOURCES[@]}"

echo "[$(date -u +%FT%TZ)] applying retention"
restic forget --quiet --prune \
  --keep-daily "${BACKUP_RETENTION_KEEP_DAILY:-7}" \
  --keep-weekly "${BACKUP_RETENTION_KEEP_WEEKLY:-4}" \
  --keep-monthly "${BACKUP_RETENTION_KEEP_MONTHLY:-6}" \
  --tag consorcio

echo "[$(date -u +%FT%TZ)] integrity check (1% sample)"
restic check --read-data-subset=1%

echo "[$(date -u +%FT%TZ)] backup OK"
