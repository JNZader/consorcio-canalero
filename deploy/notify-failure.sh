#!/usr/bin/env bash
# INF-10 / INF-02: OnFailure hook. Sends one JSON ping when a unit fails.
# Configure ALERT_WEBHOOK_URL and/or MAILTO in /etc/consorcio/notify.env.
# Does not interpolate the unit name into a shell command.
set -euo pipefail

unit="${1:-}"
if [[ ! "${unit}" =~ ^[A-Za-z0-9][A-Za-z0-9@._-]{0,127}$ ]]; then
  echo "refusing unsafe unit name" >&2
  exit 2
fi

if [[ -f /etc/consorcio/notify.env ]]; then
  # shellcheck disable=SC1091
  set -a
  source /etc/consorcio/notify.env
  set +a
fi

message="consorcio unit failed: ${unit} on $(hostname) at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "${message}"

sent=0
if [[ -n "${ALERT_WEBHOOK_URL:-}" ]]; then
  payload="$(python3 -c 'import json,sys; print(json.dumps({"text": sys.argv[1], "unit": sys.argv[2]}))' "${message}" "${unit}")"
  curl --fail --silent --show-error --max-time 15 \
    -H "Content-Type: application/json" \
    --data "${payload}" \
    "${ALERT_WEBHOOK_URL}"
  sent=1
fi
if [[ -n "${MAILTO:-}" ]] && command -v sendmail >/dev/null 2>&1; then
  sendmail -t <<EOF
To: ${MAILTO}
Subject: ${message}

${message}
EOF
  sent=1
fi
if (( sent == 0 )); then
  echo "no ALERT_WEBHOOK_URL or MAILTO configured; failure is only in the journal" >&2
  exit 1
fi
