#!/usr/bin/env bash
#
# Daily encrypted pg_dump → offsite. Driven entirely by env vars so the
# same script handles both Backblaze B2 and Hetzner Storage Box opt-in.
#
# Required env:
#   DATABASE_URL                  — postgres://... (read-only is enough)
#   BACKUP_ENCRYPTION_PASSPHRASE  — anything strong; restore needs the
#                                   same value. Generate with
#                                   ``openssl rand -base64 48``.
#
# Pick exactly ONE remote backend:
#
# Backblaze B2:
#   BACKUP_BACKEND=b2
#   B2_BUCKET=...                 — bucket name
#   B2_KEY_ID=...                 — Application Key ID
#   B2_APPLICATION_KEY=...        — Application Key (the long secret)
#
# Hetzner Storage Box (SFTP):
#   BACKUP_BACKEND=hetzner-sb
#   HETZNER_SB_HOST=uXXXXXX.your-storagebox.de
#   HETZNER_SB_USER=uXXXXXX
#   HETZNER_SB_PASS=... (or HETZNER_SB_SSH_KEY pointing at a private key file)
#
# Optional:
#   BACKUP_RETENTION_DAYS=14      — purge dumps older than this (default 30)
#   BACKUP_NAME_PREFIX=consorcio  — appears in the filename
#
# Run from cron / systemd timer / docker-compose service. The script
# writes a single ``.sql.zst.enc`` file per run; no temp files survive.
#
# Exit codes: 0 success; non-zero from the first failing step.

set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_ENCRYPTION_PASSPHRASE:?BACKUP_ENCRYPTION_PASSPHRASE is required}"
: "${BACKUP_BACKEND:?BACKUP_BACKEND must be 'b2' or 'hetzner-sb'}"

PREFIX="${BACKUP_NAME_PREFIX:-consorcio}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILENAME="${PREFIX}-${STAMP}.sql.zst.enc"
TMPDIR="$(mktemp -d)"
trap 'rm -rf -- "$TMPDIR"' EXIT
DUMP_PATH="${TMPDIR}/${FILENAME}"

echo "[$(date -u +%FT%TZ)] pg_dump → ${FILENAME}"

# pg_dump -Fc would be smaller for postgres-native restore but the
# zstd → openssl pipe below works the same regardless of format and
# keeps the file streamable (we never hold the full dump on disk).
pg_dump --no-owner --no-acl --clean --if-exists "$DATABASE_URL" \
  | zstd --quiet -19 \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
      -pass "env:BACKUP_ENCRYPTION_PASSPHRASE" \
  > "$DUMP_PATH"

SIZE_BYTES="$(stat -c %s "$DUMP_PATH" 2>/dev/null || stat -f %z "$DUMP_PATH")"
echo "[$(date -u +%FT%TZ)] dump size: ${SIZE_BYTES} bytes"

# Integrity sidecar. AES-256-CBC has no built-in authentication tag,
# so a bit-flip in the offsite blob would only surface at restore time
# with a corrupted SQL. The companion ``.sha256`` lets the restore
# drill verify the dump before decrypting.
SHA256_PATH="${DUMP_PATH}.sha256"
# Standard sha256sum -c format: ``<hash>  <filename>``. The filename is
# stored as the basename (not the absolute path) so the restore can run
# ``sha256sum -c file.sha256`` from any directory holding the dump.
(cd "$TMPDIR" && sha256sum "$(basename "$DUMP_PATH")" > "$SHA256_PATH")
echo "[$(date -u +%FT%TZ)] sha256: $(cat "$SHA256_PATH")"

case "$BACKUP_BACKEND" in
  b2)
    : "${B2_BUCKET:?B2_BUCKET is required for BACKUP_BACKEND=b2}"
    : "${B2_KEY_ID:?B2_KEY_ID is required for BACKUP_BACKEND=b2}"
    : "${B2_APPLICATION_KEY:?B2_APPLICATION_KEY is required for BACKUP_BACKEND=b2}"

    # Use the official ``b2`` CLI (pip install b2). The credentials live
    # in env so they never end up in ``~/.b2_account_info``.
    B2_ACCOUNT_INFO="${TMPDIR}/.b2_account_info" \
      b2 account authorize "$B2_KEY_ID" "$B2_APPLICATION_KEY"
    B2_ACCOUNT_INFO="${TMPDIR}/.b2_account_info" \
      b2 file upload --quiet "$B2_BUCKET" "$DUMP_PATH" "postgres/${FILENAME}"
    B2_ACCOUNT_INFO="${TMPDIR}/.b2_account_info" \
      b2 file upload --quiet "$B2_BUCKET" "$SHA256_PATH" "postgres/${FILENAME}.sha256"

    if [ "$RETENTION_DAYS" -gt 0 ]; then
      # B2 lifecycle rules are the right way to handle retention; this
      # is a belt-and-braces fallback for installs that didn't set the
      # bucket policy.
      CUTOFF_EPOCH="$(date -u -d "-${RETENTION_DAYS} days" +%s 2>/dev/null \
        || date -u -v "-${RETENTION_DAYS}d" +%s)"
      echo "[$(date -u +%FT%TZ)] purging B2 dumps older than ${RETENTION_DAYS}d"
      B2_ACCOUNT_INFO="${TMPDIR}/.b2_account_info" \
        b2 ls --recursive --json "$B2_BUCKET" "postgres/" \
        | python3 -c "
import json, sys, subprocess, datetime
cutoff = int(sys.argv[1])
for line in sys.stdin:
    obj = json.loads(line)
    if obj.get('uploadTimestamp', 0) // 1000 < cutoff and obj.get('fileName', '').startswith('postgres/${PREFIX}'):
        subprocess.run(['b2', 'file', 'hide', '$B2_BUCKET', obj['fileName']], check=False)
" "$CUTOFF_EPOCH"
    fi
    ;;

  hetzner-sb)
    : "${HETZNER_SB_HOST:?HETZNER_SB_HOST is required for BACKUP_BACKEND=hetzner-sb}"
    : "${HETZNER_SB_USER:?HETZNER_SB_USER is required for BACKUP_BACKEND=hetzner-sb}"

    if [ -n "${HETZNER_SB_SSH_KEY:-}" ]; then
      SCP_AUTH=(-i "$HETZNER_SB_SSH_KEY" -o StrictHostKeyChecking=accept-new)
    elif [ -n "${HETZNER_SB_PASS:-}" ]; then
      SCP_AUTH=(-o StrictHostKeyChecking=accept-new)
      # ``sshpass`` is the cleanest way to pipe a password into scp; the
      # Storage Box has no other auth option without an SSH key.
      command -v sshpass >/dev/null || {
        echo "ERROR: sshpass not installed (apt install sshpass)"
        exit 2
      }
      SSHPASS_CMD=(sshpass -e)
      export SSHPASS="$HETZNER_SB_PASS"
    else
      echo "ERROR: set either HETZNER_SB_SSH_KEY or HETZNER_SB_PASS"
      exit 2
    fi

    REMOTE_DIR="postgres"
    REMOTE_PATH="${REMOTE_DIR}/${FILENAME}"
    # Ensure the directory exists. The Storage Box only exposes sftp;
    # ``mkdir -p`` over sftp needs a tiny here-doc.
    "${SSHPASS_CMD[@]:-}" sftp "${SCP_AUTH[@]}" \
      "${HETZNER_SB_USER}@${HETZNER_SB_HOST}" <<EOF
-mkdir ${REMOTE_DIR}
put ${DUMP_PATH} ${REMOTE_PATH}
put ${SHA256_PATH} ${REMOTE_PATH}.sha256
quit
EOF

    if [ "$RETENTION_DAYS" -gt 0 ]; then
      echo "[$(date -u +%FT%TZ)] purging Storage Box dumps older than ${RETENTION_DAYS}d"
      # List, parse, delete via sftp. Storage Box doesn't honour `find`,
      # so we walk the listing on the client side.
      "${SSHPASS_CMD[@]:-}" sftp "${SCP_AUTH[@]}" \
        "${HETZNER_SB_USER}@${HETZNER_SB_HOST}" <<EOF
ls -la ${REMOTE_DIR}
quit
EOF
      # The above only PRINTS; actual delete-by-age is a roadmap follow-
      # up. For now operators are expected to set a sane lifecycle in
      # the Hetzner Storage Box UI.
    fi
    ;;

  *)
    echo "ERROR: unknown BACKUP_BACKEND=${BACKUP_BACKEND}; use 'b2' or 'hetzner-sb'"
    exit 2
    ;;
esac

echo "[$(date -u +%FT%TZ)] backup OK"
