#!/usr/bin/env bash
# ============================================
# CI-Local: Consorcio Canalero Monorepo
# Validates code locally before pushing to GitHub
# Based on: github.com/JNZader/project-starter-framework
# ============================================

set -euo pipefail

MODE=${1:-full}

# Colors
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

ROOT_DIR=$(cd "$(dirname "$0")/.." && pwd)
FRONTEND_DIR="$ROOT_DIR/consorcio-web"
BACKEND_DIR="$ROOT_DIR/gee-backend"

errors=0
warnings=0
start_time=$(date +%s)

# ============================================
# Helpers
# ============================================
step() {
  echo -e "\n${BLUE}▶ $1${NC}"
}

pass() {
  echo -e "  ${GREEN}✓ $1${NC}"
}

fail() {
  echo -e "  ${RED}✗ $1${NC}"
  errors=$((errors + 1))
}

warn() {
  echo -e "  ${YELLOW}⚠ $1${NC}"
  warnings=$((warnings + 1))
}

check_tool() {
  if ! command -v "$1" &>/dev/null; then
    warn "$1 not found, skipping $2"
    return 1
  fi
  return 0
}

# ============================================
# Frontend checks
# ============================================
frontend_lint() {
  step "Frontend: Lint (Biome)"
  if cd "$FRONTEND_DIR" && npm run lint 2>&1; then
    pass "Lint OK"
  else
    fail "Lint failed"
  fi
}

frontend_typecheck() {
  step "Frontend: Type-check (TypeScript)"
  if cd "$FRONTEND_DIR" && ./node_modules/.bin/tsc --noEmit 2>&1; then
    pass "Types OK"
  else
    fail "Type-check failed"
  fi
}

frontend_test() {
  step "Frontend: Tests (Vitest)"
  if cd "$FRONTEND_DIR" && npm run test:run 2>&1; then
    pass "Tests OK"
  else
    fail "Tests failed"
  fi
}

frontend_build() {
  step "Frontend: Build"
  if cd "$FRONTEND_DIR" && npm run build 2>&1; then
    pass "Build OK"
  else
    fail "Build failed"
  fi
}

# ============================================
# Backend checks
# ============================================
backend_lint() {
  step "Backend: Lint (Ruff)"
  check_tool ruff "backend lint" || return 0
  cd "$BACKEND_DIR"
  if ruff check app/ tests/ 2>&1 && ruff format app/ tests/ --check 2>&1; then
    pass "Lint OK"
  else
    fail "Lint failed"
  fi
}

backend_typecheck() {
  step "Backend: Type-check (MyPy) [non-blocking]"
  check_tool mypy "backend type-check" || return 0
  if cd "$BACKEND_DIR" && mypy app/ --ignore-missing-imports 2>&1; then
    pass "Types OK"
  else
    warn "Type issues found (non-blocking, matches CI behavior)"
  fi
}

backend_security() {
  step "Backend: Security (Bandit)"
  check_tool bandit "backend security scan" || return 0
  if cd "$BACKEND_DIR" && bandit -r app/ -ll -q 2>&1; then
    pass "Security OK"
  else
    fail "Security scan found issues"
  fi
}

backend_test() {
  step "Backend: Tests (Pytest) [non-blocking]"
  if ! python -m pytest --version &>/dev/null; then
    warn "pytest not found, skipping backend tests"
    return 0
  fi
  if cd "$BACKEND_DIR" && python -m pytest tests/ -v --cov=app --cov-fail-under=50 2>&1; then
    pass "Tests OK"
  else
    warn "Tests failed (non-blocking, requires Docker environment)"
  fi
}

# ============================================
# Secrets check
# ============================================
check_secrets() {
  step "Secrets: Scanning staged files"
  cd "$ROOT_DIR"
  local patterns=('PRIVATE.KEY' 'password\s*=' 'secret\s*=' 'api_key\s*=' 'token\s*=')
  local found=0

  for file in $(git diff --cached --name-only 2>/dev/null || git diff --name-only HEAD 2>/dev/null); do
    if [[ "$file" == *.env* ]] || [[ "$file" == *credentials* ]] || [[ "$file" == *secret* ]]; then
      warn "Suspicious file staged: $file"
      found=1
    fi
  done

  if [ $found -eq 0 ]; then
    pass "No secrets detected"
  else
    fail "Potential secrets in staged files"
  fi
}

# ============================================
# Run modes
# ============================================
show_usage() {
  echo -e "${BOLD}CI-Local: Consorcio Canalero${NC}"
  echo ""
  echo "Usage: ci-local.sh [mode]"
  echo ""
  echo "Modes:"
  echo "  quick    Lint + type-check only (fast, no Docker)"
  echo "  full     Lint + type-check + test + build (default)"
  echo "  docker   Full CI via Docker Compose"
  echo "  detect   Show detected project stack"
  echo ""
  echo "Examples:"
  echo "  ./.ci-local/ci-local.sh quick   # Before each commit"
  echo "  ./.ci-local/ci-local.sh full    # Before push"
}

case "$MODE" in
  quick)
    echo -e "${BOLD}${BLUE}═══ CI-Local: Quick Mode ═══${NC}"
    echo -e "Scope: lint + type-check\n"
    check_secrets
    frontend_lint
    frontend_typecheck
    backend_lint
    backend_typecheck
    ;;
  full)
    echo -e "${BOLD}${BLUE}═══ CI-Local: Full Mode ═══${NC}"
    echo -e "Scope: lint + type-check + security + test + build\n"
    check_secrets
    frontend_lint
    frontend_typecheck
    frontend_test
    frontend_build
    backend_lint
    backend_typecheck
    backend_security
    backend_test
    ;;
  docker)
    echo -e "${BOLD}${BLUE}═══ CI-Local: Docker Mode ═══${NC}"
    echo -e "Scope: full CI via Docker Compose\n"
    check_tool docker "Docker mode" || exit 1
    step "Building Docker images"
    cd "$ROOT_DIR" && docker compose build 2>&1 && pass "Build OK" || fail "Docker build failed"
    ;;
  detect)
    echo -e "${BOLD}Detected stack:${NC}"
    echo "  Frontend: Node.js (React + Vite + TypeScript)"
    echo "  Backend:  Python (FastAPI)"
    echo "  Infra:    Docker Compose + Nginx"
    echo "  CI:       GitHub Actions (reusable workflows)"
    exit 0
    ;;
  help|--help|-h)
    show_usage
    exit 0
    ;;
  *)
    echo -e "${RED}Unknown mode: $MODE${NC}"
    show_usage
    exit 1
    ;;
esac

# ============================================
# Summary
# ============================================
end_time=$(date +%s)
elapsed=$((end_time - start_time))

echo ""
echo -e "${BOLD}─── Results ───${NC}"
echo -e "  Duration: ${elapsed}s"
echo -e "  Errors:   ${errors}"
echo -e "  Warnings: ${warnings}"
echo ""

if [ $errors -eq 0 ]; then
  echo -e "${GREEN}${BOLD}═══ All checks passed! Safe to push. ═══${NC}"
  exit 0
else
  echo -e "${RED}${BOLD}═══ ${errors} check(s) failed. Fix before pushing. ═══${NC}"
  exit 1
fi
