#!/usr/bin/env bash
#
# Pre-push CI replacement. The GitHub Actions ``Backend`` /
# ``Build and Publish Images`` workflows are ``disabled_manually`` on
# this repo (GH Actions billing quota exceeded), so the Phase 4 gates
# (ruff + mypy + auth-gate regression + 60% coverage + 30% mutation
# kill-rate) are not enforced server-side. This script reproduces them
# locally so a developer can run it before ``git push`` and catch the
# same regressions the CI used to catch.
#
# Usage from gee-backend/:
#   bash scripts/preflight.sh             # ALL gates (~10min, default)
#   bash scripts/preflight.sh --fast      # skip the mutation gate (~30s)
#   bash scripts/preflight.sh --help
#
# The mutation gate is the default so it doesn't quietly rust. If you
# need the fast iteration path during local development, ``--fast`` is
# the explicit opt-out.
#
# Exit codes:
#   0   all enforced gates passed
#   1   one or more gates failed (see stderr for the failing step)
#   2   environment issue (no venv, no DB, missing tool)
#
# Reference: docs/RUNBOOK.md §2.1 deploy procedure.

set -euo pipefail

# ---------------------------------------------------------------------------
# Arg parsing
# ---------------------------------------------------------------------------

FAST=false
for arg in "$@"; do
    case "$arg" in
        --fast)
            FAST=true
            ;;
        --help|-h)
            cat <<'USAGE'
preflight.sh — local equivalent of the disabled GitHub Actions gates.

Always runs:
    1. ruff check
    2. mypy on the Phase 4 strict scope (auth + padron + denuncias)
    3. auth-gate regression suite (tests/new/test_auth_gates.py)
    4. backend coverage gate at 60% (tests/new/ + .coveragerc)
    5. cosmic-ray mutation gate at 0.30 kill-rate
       (denuncias.service, monitoring.service, tramites.schemas)

Total ~10min on a warm venv. Step 5 is the slow one.

With --fast: skip step 5 (~30s total) — use during inner-loop dev,
NEVER as a substitute for the full gate before ``git push``.

Exits 0 iff every enforced gate passes.
USAGE
            exit 0
            ;;
        *)
            echo "preflight.sh: unknown arg '$arg'. Try --help." >&2
            exit 2
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Environment sanity
# ---------------------------------------------------------------------------

if [[ ! -f "venv/bin/activate" ]]; then
    echo "preflight.sh: venv/bin/activate not found. Run from gee-backend/ and ensure the venv is created." >&2
    exit 2
fi

# shellcheck disable=SC1091
source venv/bin/activate

# Pytest uses testcontainers (Docker) OR TEST_DATABASE_URL to find a DB.
# We don't try to start Docker for the caller — just bail loudly so the
# user knows which knob to turn.
if ! docker info >/dev/null 2>&1 && [[ -z "${TEST_DATABASE_URL:-}" ]]; then
    echo "preflight.sh: neither Docker nor TEST_DATABASE_URL is available." >&2
    echo "  Either start Docker (testcontainers will spin postgis) or" >&2
    echo "  export TEST_DATABASE_URL=postgresql://test:test@localhost:5432/test_consorcio" >&2
    exit 2
fi

# ---------------------------------------------------------------------------
# Step runner
# ---------------------------------------------------------------------------

FAILED=()
run_step() {
    local label="$1"
    shift
    printf '\n══ %s\n' "$label"
    if "$@"; then
        printf '✔ %s passed\n' "$label"
    else
        printf '✘ %s FAILED\n' "$label" >&2
        FAILED+=("$label")
    fi
}

# ---------------------------------------------------------------------------
# 1. ruff
# ---------------------------------------------------------------------------

run_step "ruff check" ruff check .

# ---------------------------------------------------------------------------
# 2. mypy (strict scope mirrors .github/workflows/backend.yml line 55)
# ---------------------------------------------------------------------------

run_step "mypy strict scope" mypy app/auth app/domains/padron app/domains/denuncias

# ---------------------------------------------------------------------------
# 3. auth-gate regression suite (F4-D)
# ---------------------------------------------------------------------------

run_step "auth-gate tests" \
    python3 -m pytest tests/new/test_auth_gates.py -q --no-header -p no:cacheprovider

# ---------------------------------------------------------------------------
# 4. backend coverage gate at 60% (F4-A)
# ---------------------------------------------------------------------------

run_step "coverage >= 60%" \
    python3 -m pytest tests/new/ \
        --cov=app --cov-config=.coveragerc \
        --cov-fail-under=60 \
        -q --no-header --tb=short -p no:cacheprovider

# ---------------------------------------------------------------------------
# 5. mutation gate (F4-B) — default ON, --fast skips it
# ---------------------------------------------------------------------------

if [[ "$FAST" == "true" ]]; then
    printf '\n⏭  mutation gate skipped (--fast). Run without --fast before git push.\n'
else
    run_step "mutation kill-rate >= 0.30" \
        python3 scripts/cosmic_gate.py --min-kill-rate 0.30
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

printf '\n════════════════════════════════════════\n'
if [[ ${#FAILED[@]} -eq 0 ]]; then
    printf '✔ ALL ENFORCED GATES PASSED — safe to push.\n'
    exit 0
else
    printf '✘ %d gate(s) failed:\n' "${#FAILED[@]}" >&2
    for step in "${FAILED[@]}"; do
        printf '  - %s\n' "$step" >&2
    done
    exit 1
fi
