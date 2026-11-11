#!/usr/bin/env bash
# Corre la regresión visual dentro de la imagen de Playwright que usa CI.
# Cualquier argumento se reenvía a Playwright, por ejemplo:
#   ./scripts/visual-regression.sh --update-snapshots
set -euo pipefail

IMAGE="mcr.microsoft.com/playwright:v1.65.0-noble"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

exec docker run --rm --ipc=host \
  -v "${ROOT}:/work" \
  -w /work \
  --user "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -e CI="${CI:-}" \
  -e PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 \
  "${IMAGE}" \
  npm run test:visual -- "$@"
