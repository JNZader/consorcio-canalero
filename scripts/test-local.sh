#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/gee-backend"
FRONTEND_DIR="$ROOT_DIR/consorcio-web"

if command -v make >/dev/null 2>&1; then
  exec make -C "$ROOT_DIR" test
fi

echo "[test-local] 'make' no disponible; ejecutando tests backend/frontend directamente"

backend_rc=0
if [ -x "$BACKEND_DIR/venv/bin/python" ]; then
  (
    cd "$BACKEND_DIR"
    ./venv/bin/python -m pytest tests/new/ -v \
      --cov=app \
      --cov-report=term-missing \
      --cov-report=html:coverage_html \
      --cov-fail-under=70
  ) || backend_rc=$?
elif command -v python3 >/dev/null 2>&1; then
  (
    cd "$BACKEND_DIR"
    python3 -m pytest tests/new/ -v \
      --cov=app \
      --cov-report=term-missing \
      --cov-report=html:coverage_html \
      --cov-fail-under=70
  ) || backend_rc=$?
else
  echo "[test-local] Python no disponible para tests backend" >&2
  backend_rc=127
fi

frontend_rc=0
if [ -d "$FRONTEND_DIR/node_modules" ] || command -v npm >/dev/null 2>&1; then
  (
    cd "$FRONTEND_DIR"
    npm run test:run
  ) || frontend_rc=$?
else
  echo "[test-local] npm no disponible para tests frontend" >&2
  frontend_rc=127
fi

if [ "$backend_rc" -ne 0 ] || [ "$frontend_rc" -ne 0 ]; then
  echo "[test-local] backend_rc=${backend_rc} frontend_rc=${frontend_rc}" >&2
  if [ "$backend_rc" -ne 0 ]; then
    exit "$backend_rc"
  fi
  exit "$frontend_rc"
fi
