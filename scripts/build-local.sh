#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

has_docker_access() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
}

if has_docker_access; then
  echo "[build-local] Docker disponible; ejecutando build completo"
  exec make -C "$ROOT_DIR" build
fi

echo "[build-local] Docker no disponible en este entorno; compilando frontend y omitiendo backend dockerizado"
exec make -C "$ROOT_DIR" frontend-build
