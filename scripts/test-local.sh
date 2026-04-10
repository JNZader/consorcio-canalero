#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/gee-backend"
FRONTEND_DIR="$ROOT_DIR/consorcio-web"

if command -v make >/dev/null 2>&1; then
  exec make -C "$ROOT_DIR" test
fi

echo "[test-local] 'make' no disponible; ejecutando tests backend/frontend directamente"

if [ -x "$BACKEND_DIR/venv/bin/python" ]; then
  (
    cd "$BACKEND_DIR"
    ./venv/bin/python -m pytest tests/new/ -v \
      --cov=app \
      --cov-report=term-missing \
      --cov-report=html:coverage_html \
      --cov-fail-under=70
  )
elif command -v python3 >/dev/null 2>&1; then
  (
    cd "$BACKEND_DIR"
    python3 -m pytest tests/new/ -v \
      --cov=app \
      --cov-report=term-missing \
      --cov-report=html:coverage_html \
      --cov-fail-under=70
  )
else
  echo "[test-local] Python no disponible para tests backend" >&2
  exit 127
fi

(
  cd "$FRONTEND_DIR"
  npm run test
)
