# CLAUDE.md - Developer Context & Setup

Quick reference guide for Claude AI working on the Consorcio Canalero project.

## Project Overview

**Consorcio Canalero 10 de Mayo** - Sistema integral de gestión para el Consorcio Canalero 10 de Mayo, Bell Ville, Córdoba, Argentina.

### Stack
- **Frontend**: React 19, TypeScript, Vite, Mantine UI, Leaflet (consorcio-web/)
- **Backend**: FastAPI, Python 3.11, Google Earth Engine (gee-backend/)
- **Database**: Supabase (PostgreSQL)
- **Testing**: Pytest (backend), Vitest (frontend), Cosmic-Ray (mutations), Stryker (mutations)
- **CI/CD**: GitHub Actions

### Key Directories
```
consorcio-canalero/
├── consorcio-web/          # React frontend (Vite)
├── gee-backend/            # FastAPI backend
├── docs/                   # Documentation
├── openspec/               # Spec-Driven Development specs
├── .github/workflows/      # CI/CD pipelines
└── nginx/                  # Nginx config
```

---

## Quick Setup

### Prerequisites
```bash
# Check versions
node --version          # >= 20
python3 --version       # >= 3.11
docker --version
```

### Development Environment
```bash
# Backend
cd gee-backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Frontend
cd consorcio-web
npm install
npm run dev
```

### Key Commands

**Backend**:
```bash
cd gee-backend
pytest                              # Run all tests
pytest -v --cov=app                 # With coverage
python3 scripts/cosmic_gate.py       # Mutation tests
uvicorn app.main:app --reload       # Dev server
```

**Frontend**:
```bash
cd consorcio-web
npm run dev                          # Dev server
npm run test                         # Unit tests
npm run test:ui                      # Test UI
npm run mutation:test                # Mutation tests (when ready)
npm run build                        # Production build
```

---

## 🧪 Mutation Testing

Critical for ensuring test quality and catching subtle logic bugs.

### What is Mutation Testing?

Mutation testing introduces intentional bugs into code and checks if your tests catch them:
- **Kill** = Test caught the mutation (good) ✅
- **Survive** = Test missed the mutation (bad) ❌

### Backend Status: Production Ready ✅

**Current Baselines:**
| Module | Kill Rate | Status |
|--------|-----------|--------|
| reports.py | 100% | ✅ |
| sugerencias.py | 100% | ✅ |
| schemas.py | 100% | ✅ |
| **Total** | **100%** | ✅ **Baseline Set** |

**Test Run**: `cd gee-backend && python3 scripts/cosmic_gate.py --min-kill-rate 1.0`
**Config**: `gee-backend/.cosmic-ray.toml`
**Tools**: Cosmic-Ray + pytest

**CI/CD Gates**:
- ✅ Enforced on every PR to main
- ✅ Blocks merge if kill rate < 100%
- ✅ Automatic rollback if >10% drop
- ✅ Manual review required for 5-10% drops

### Frontend Status: Phase 2 Ready 📋

**Configuration**: Ready but implementation pending

**Target Baselines** (Phase 2):
| Category | Target | Status |
|----------|--------|--------|
| Utilities | 5 files, ≥80% | 📋 Ready |
| Hooks | 8 hooks, ≥80% | 📋 Ready |
| Components | 9 files, ≥80% | 📋 Ready |

**When Phase 2 Launches**:
- `cd consorcio-web && npm run mutation:test`
- Config: `stryker.config.json`
- Tool: Stryker JS
- Same CI/CD enforcement as backend

### Reading Reports

**Backend**: After running cosmic-ray
```bash
cd gee-backend
python3 scripts/cosmic_gate.py --min-kill-rate 1.0
# Output shows: Kill rate: X% (required >= 100%)
```

**Frontend** (Phase 2): After running stryker
```bash
cd consorcio-web
npm run mutation:test
# Reports in: consorcio-web/reports/mutation/index.html
```

### Team Training Checklist ✓

Before working with mutation testing:

- [ ] Read [docs/MUTATION_TESTING.md](docs/MUTATION_TESTING.md) (15 min)
- [ ] Read [docs/MUTATION_ROLLBACK.md](docs/MUTATION_ROLLBACK.md) (10 min)
- [ ] Review [docs/MUTATION_TESTING_BASELINE.md](docs/MUTATION_TESTING_BASELINE.md) (5 min)
- [ ] Understand mutation score ≠ code coverage
- [ ] Know what "escaped mutation" means
- [ ] Familiar with parametrized tests (pytest/vitest)
- [ ] Know that weak assertions allow mutations to survive
- [ ] Can run mutation tests locally
- [ ] Know the CI/CD gates (100% backend, 80% frontend)
- [ ] Know how to request threshold exceptions (rare!)
- [ ] Reviewed example of strong vs weak tests (in MUTATION_TESTING.md)

### Common Issues & Fixes

**Low mutation score** → Usually means weak tests:
```python
# ❌ Weak: Only checks if result exists
assert calculate_fee(100) is not None

# ✅ Strong: Checks exact value
assert calculate_fee(100) == 90
assert calculate_fee(0) == 0
```

**Escaped mutations** → Missing edge cases:
```python
# ❌ Weak: Only tests happy path
def test_process_order():
    result = process_order(valid_order)
    assert result.success

# ✅ Strong: Tests all paths
@pytest.mark.parametrize("order,expected", [
    (valid_order, True),
    (None, False),
    ({}, False),
    (order_with_invalid_amount, False),
])
def test_process_order(order, expected):
    assert process_order(order).success == expected
```

### Documentation Links

| Document | Purpose | Audience |
|----------|---------|----------|
| [MUTATION_TESTING.md](docs/MUTATION_TESTING.md) | Complete guide, team processes | Everyone |
| [MUTATION_ROLLBACK.md](docs/MUTATION_ROLLBACK.md) | Emergency procedures, post-mortems | Team leads, on-call |
| [MUTATION_TESTING_BASELINE.md](docs/MUTATION_TESTING_BASELINE.md) | Baseline tracking, history | Team leads, QA |

### When Things Go Wrong

**PR fails with "Kill rate below threshold"**:
1. Check the error message - it shows actual vs required
2. Review failed mutations in CI output
3. Add parametrized tests to fix gaps
4. Push updated tests
5. CI re-runs automatically

**Multiple modules affected simultaneously**:
1. Don't merge - it's blocked in CI
2. Contact team lead
3. May need rollback + post-mortem

**Production regression detected**:
1. Automatic rollback triggered
2. Post-mortem issue created
3. Follow post-mortem template (see docs)

---

## Spec-Driven Development (SDD)

We use SDD for significant changes. See `openspec/` directory.

### Current Changes

| Change | Status | Type |
|--------|--------|------|
| **Consolidation Mutation Testing** | ✅ Phase 1 Complete | Documentation & Gates |
| **Frontend Mutation Expansion** | 📋 Ready for Phase 2 | Frontend Implementation |

### SDD Commands

```bash
# Explore an idea (no files)
/sdd:explore mutation-testing-improvements

# Start a new change
/sdd:new mutation-testing-consolidation

# Continue to next phase
/sdd:continue mutation-testing-consolidation

# View specs
openspec/changes/consolidation-mutation-testing/spec.md
openspec/changes/consolidation-mutation-testing/design.md
openspec/changes/consolidation-mutation-testing/tasks.md
```

---

## CI/CD Pipeline

### Workflows

| Workflow | Trigger | Duration | Key Gates |
|----------|---------|----------|-----------|
| **Backend** | Push/PR to main | ~15min | Lint, Type, Test, Contract, Mutation, Security |
| **Frontend** | Push/PR to main | ~10min | Lint, Type, Test, Build |
| **Mutation** | Push/PR to main | ~35min | Backend 100%, Frontend TBD |
| **Deploy** | Push to main | ~5min | All tests must pass |

### Pre-Push Checks

Before pushing to origin:

```bash
# Backend
cd gee-backend
ruff check .                              # Lint
ruff format --check .                     # Format
mypy app/ --ignore-missing-imports        # Type check
pytest tests/ -v --cov=app                # Unit tests
python3 scripts/cosmic_gate.py             # Mutation tests ✅ IMPORTANT!

# Frontend
cd consorcio-web
npm run lint                              # ESLint + format
npm run type-check                        # TypeScript
npm run test                              # Unit tests
# npm run mutation:test                   # When Phase 2 ready
npm run build                             # Production build check
```

---

## Git Workflow

### Branch Strategy

```
main (production)
  ↑
  ├── feature/mutation-testing-improvements
  ├── fix/backend-performance-issue
  └── docs/update-guides
```

### Commit Conventions

```bash
git commit -m "feat: add mutation testing documentation"
git commit -m "fix: improve test coverage for reports module"
git commit -m "docs: update MUTATION_TESTING baseline"
git commit -m "test: add parametrized tests for edge cases"
```

### PR Process

1. Create feature branch
2. Commit regularly with atomic commits
3. Run local tests + mutation tests
4. Push to origin
5. Create PR with description
6. Wait for CI (all workflows must pass)
7. Request review from team
8. Address feedback
9. Merge when approved
10. CI/CD auto-deploys to staging

---

## Testing Philosophy

### Mutation Testing vs Code Coverage

| Aspect | Code Coverage | Mutation Testing |
|--------|--------------|------------------|
| Measures | Lines executed | Test effectiveness |
| Can miss | Logic bugs | Weak assertions |
| Better for | Identifying gaps | Verifying quality |
| Target | 70-80% | 80-100% |

**Key insight**: 100% coverage with 50% mutation score = exercising code but not verifying it properly.

### Test Quality Checklist

For any new code/test:

- [ ] Tests exist (not just coverage)
- [ ] Parametrized tests for variations
- [ ] Edge cases covered (null, empty, boundaries)
- [ ] Error cases explicitly tested
- [ ] Assertions are specific (not just truthiness)
- [ ] Tests are readable and self-documenting
- [ ] No hard-coded test data duplication
- [ ] Mutation tests pass (90%+ kill rate minimum)

---

## Project Configuration

### Key Files

| File | Purpose |
|------|---------|
| `gee-backend/.cosmic-ray.toml` | Backend mutation testing config |
| `consorcio-web/stryker.config.json` | Frontend mutation testing config |
| `.github/workflows/backend.yml` | Backend CI/CD pipeline |
| `.github/workflows/frontend.yml` | Frontend CI/CD pipeline |
| `.github/workflows/mutation-testing.yml` | Mutation testing gates |
| `docs/MUTATION_TESTING.md` | Team guide |

### Environment Variables

**Backend** (`gee-backend/.env`):
```env
SUPABASE_URL=https://...
SUPABASE_SECRET_KEY=...
GEE_KEY_FILE_PATH=/app/credentials/gee-service-account.json
GEE_PROJECT_ID=cc10demayo
```

**Frontend** (`consorcio-web/.env`):
```env
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=https://...
VITE_SUPABASE_ANON_KEY=...
```

---

## Useful Resources

### Documentation
- [README.md](README.md) - Project overview
- [SETUP_GUIDE.md](docs/SETUP_GUIDE.md) - Detailed setup
- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines
- [docs/DEPLOY_GUIDE.md](docs/DEPLOY_GUIDE.md) - Deployment guide

### Testing Guides
- [docs/MUTATION_TESTING.md](docs/MUTATION_TESTING.md) - Mutation testing complete guide
- [docs/MUTATION_ROLLBACK.md](docs/MUTATION_ROLLBACK.md) - Rollback & post-mortem procedures
- [docs/MUTATION_TESTING_BASELINE.md](docs/MUTATION_TESTING_BASELINE.md) - Baseline tracking

### Specs (Spec-Driven Development)
- `openspec/changes/consolidation-mutation-testing/` - Phase 1 (complete)
- `openspec/changes/frontend-mutation-expansion/` - Phase 2 (ready)

---

## Support & Questions

### Getting Help

1. Check relevant documentation first (usually has answers)
2. Search recent PRs/issues for similar problems
3. Ask in #engineering-practices Slack
4. Escalate to @javier (mutation testing owner) if needed

### Reporting Issues

Create issue with:
- [ ] Clear title
- [ ] Reproduction steps (if bug)
- [ ] Expected vs actual behavior
- [ ] Environment (Python/Node version, OS)
- [ ] Screenshots/logs if applicable

### Reaching Out

- **Mutation testing questions**: @javier
- **Frontend issues**: @javier
- **Backend issues**: @javier
- **DevOps/CI/CD**: @devops-team
- **General questions**: Ask in Slack first

---

## Quick Reference

### Most Common Commands

```bash
# Check everything before pushing
./scripts/pre-push.sh                    # If exists

# Backend only
cd gee-backend
pytest tests/ -v
python3 scripts/cosmic_gate.py

# Frontend only
cd consorcio-web
npm test
npm run build

# View this file
cat CLAUDE.md
```

### Most Common Issues

| Issue | Fix |
|-------|-----|
| "Kill rate below threshold" | Add parametrized tests, use specific assertions |
| "Tests pass locally, fail in CI" | Check environment differences, run full test suite |
| "Git merge conflicts" | Resolve manually, test fully before re-pushing |
| "CI hangs/times out" | Check for infinite loops, long-running operations |

### When in Doubt

1. Read relevant docs in `docs/`
2. Check related spec in `openspec/`
3. Look at recent PRs for similar changes
4. Ask in Slack
5. Don't force-push to main 🚫

---

Last updated: 2026-03-10
Maintained by: @javier
