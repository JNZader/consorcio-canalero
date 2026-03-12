# Mutation Testing Baselines

Official baseline tracking for mutation test scores across the Consorcio Canalero project.

**Last Updated**: 2026-03-10
**Status**: Backend complete ✅ | Frontend ready for Phase 2 📋

---

## Backend Baselines (Production Ready) ✅

### Overview

The backend has achieved **100% kill rate** across all critical modules, with comprehensive test coverage ensuring high-quality mutation testing.

| Status | Achievement | Date | Verified |
|--------|------------|------|----------|
| ✅ Baseline Set | 454/454 mutations killed | 2026-03-10 | Yes |
| ✅ Gate Active | Enforced in CI/CD | 2026-03-10 | Yes |
| ✅ Documentation | Complete and team-trained | 2026-03-10 | Yes |

### Module Baselines

#### Module 1: Reports (`app/api/v1/endpoints/reports.py`)

| Metric | Value | Status |
|--------|-------|--------|
| **Mutations Created** | 200+ | ✅ |
| **Mutations Killed** | 200+ | ✅ |
| **Kill Rate** | 100% | ✅ Production Ready |
| **Test File** | `tests/test_reports_contract.py` | ✅ |
| **Test Count** | 15+ parameterized tests | ✅ |
| **Last Verified** | 2026-03-10 | ✅ |

**Key Testing Strength**:
- Comprehensive contract testing for all report endpoints
- Edge case coverage: empty reports, null fields, boundary values
- Integration tests with real database
- Performance assertions on response times

**Monitored by CI/CD**: Yes ✅

---

#### Module 2: Sugerencias (`app/api/v1/endpoints/sugerencias.py`)

| Metric | Value | Status |
|--------|-------|--------|
| **Mutations Created** | 100+ | ✅ |
| **Mutations Killed** | 100+ | ✅ |
| **Kill Rate** | 100% | ✅ Production Ready |
| **Test File** | `tests/test_sugerencias_contract.py` | ✅ |
| **Test Count** | 10+ parameterized tests | ✅ |
| **Last Verified** | 2026-03-10 | ✅ |

**Key Testing Strength**:
- Contract tests for suggestion creation, validation, and filtering
- Validation error cases thoroughly tested
- State mutation tests (status transitions)
- Concurrency and race condition handling

**Monitored by CI/CD**: Yes ✅

---

#### Module 3: Schemas (`app/api/v1/schemas.py`)

| Metric | Value | Status |
|--------|-------|--------|
| **Mutations Created** | 50+ | ✅ |
| **Mutations Killed** | 50+ | ✅ |
| **Kill Rate** | 100% | ✅ Production Ready |
| **Test File** | `tests/test_tramites_schema.py` | ✅ |
| **Test Count** | 20+ parameterized tests | ✅ |
| **Last Verified** | 2026-03-10 | ✅ |

**Key Testing Strength**:
- Pydantic schema validation tests for all models
- Type coercion and parsing edge cases
- Boundary conditions on numeric fields
- String normalization and validation

**Monitored by CI/CD**: Yes ✅

---

### Aggregate Baseline

| Metric | Value | Status |
|--------|-------|--------|
| **Total Mutations** | **454** | ✅ |
| **Total Killed** | **454** | ✅ |
| **Overall Kill Rate** | **100%** | ✅ **Baseline Set** |
| **Regression Threshold** | <90% (>10% drop) | 🔴 Critical |
| **Warning Threshold** | <95% (>5% drop) | 🟠 High |
| **CI/CD Gate Status** | ✅ Enforced | |
| **Last Gate Verification** | 2026-03-10 | ✅ |

### How These Baselines Were Achieved

1. **Comprehensive Unit Tests**
   - Parametrized tests for major code paths
   - Edge case coverage (null, empty, boundaries)
   - Error condition handling

2. **Integration Tests**
   - Real database interactions
   - Contract testing for API endpoints
   - Request/response validation

3. **Strong Assertions**
   - Specific value checks (not just truthiness)
   - Type validation
   - Side effect verification (database state, call counts)

4. **Test Quality Standards**
   - Clear test names indicating what's being tested
   - Isolated test cases (no cross-contamination)
   - Proper setup/teardown
   - Descriptive failure messages

### Maintaining Baseline ✅

To maintain the 100% baseline going forward:

**On Every PR**:
- [ ] Run mutation tests locally before push
- [ ] Verify score = 100% or above
- [ ] If score < 100%, add parametrized tests
- [ ] Use specific assertions

**For New Features**:
- [ ] Write tests first (TDD approach)
- [ ] Include parametrized tests for variations
- [ ] Test error cases explicitly
- [ ] Run mutation tests before creating PR

**CI/CD Gate**:
- [ ] Automatic enforcement on every PR
- [ ] Blocks merge if score < 100%
- [ ] Blocks deploy if main branch < 100%
- [ ] Automatic rollback if >10% drop

---

## Frontend Baselines (Phase 2 Pending) 📋

### Overview

Frontend mutation testing configuration is ready. Implementation of comprehensive mutation testing across frontend modules is scheduled for Phase 2.

### Phase 1 Status

| Component | Status | Config | Spec |
|-----------|--------|--------|------|
| **Stryker Configuration** | ✅ Ready | `stryker.config.json` | ✅ |
| **GitHub Actions Workflow** | ✅ Ready | `.github/workflows/mutation-testing.yml` | ✅ |
| **Documentation** | ✅ Complete | `docs/MUTATION_TESTING.md` | ✅ |
| **Test Suite Foundation** | ✅ Ready | `vitest` configured | ✅ |

### Phase 2 Targets (Implementation Pending)

#### Target 1: Utility Functions

| Category | Target Files | Status | Target Score |
|----------|-------------|--------|---------------|
| **Utilities** | 5 utility files | 📋 Spec Ready | ≥80% |
| Example files | `src/lib/api/*.ts` (reportsResolve, tramitesCanonical, etc.) | | |
| Tests required | Parametrized tests for edge cases, boundaries | | |
| Timeline | Phase 2 Sprint 1 | | |

#### Target 2: Custom React Hooks

| Category | Target Files | Status | Target Score |
|----------|-------------|--------|---------------|
| **Hooks** | 8 custom React hooks | 📋 Spec Ready | ≥80% |
| Example files | `src/hooks/*.ts` (useStore, useAsync, useTheme, etc.) | | |
| Tests required | Hook testing library, async handling, state updates | | |
| Timeline | Phase 2 Sprint 2 | | |

#### Target 3: Store & Components

| Category | Target Files | Status | Target Score |
|----------|-------------|--------|---------------|
| **Components** | 9 key components | 📋 Spec Ready | ≥80% |
| Example files | Store modules, UI components with complex logic | | |
| Tests required | Component testing, prop variations, user interactions | | |
| Timeline | Phase 2 Sprint 3 | | |

### Phase 2 Implementation Plan

**See**: [Frontend Mutation Expansion - Phase 2 Real Hooks](../openspec/changes/frontend-mutation-expansion/PHASE_2_REAL_HOOKS.md)

**Key Deliverables**:
- [ ] Mutation tests for 5 utility functions
- [ ] Mutation tests for 8 React hooks
- [ ] Mutation tests for 9 key components
- [ ] Achieve ≥80% kill rate on each module
- [ ] Update this baseline tracking document
- [ ] CI/CD gates activated for frontend

**Expected Timeline**: Q2 2026

### Stryker Configuration (Ready)

Current stryker.config.json:
```json
{
  "testRunner": "command",
  "commandRunner": {
    "command": "npm run test:run -- <test-files>"
  },
  "mutate": [
    "src/lib/api/reportsResolve.ts",
    "src/components/admin/management/tramitesCanonical.ts"
  ],
  "thresholds": {
    "high": 80,
    "low": 70,
    "break": 80
  },
  "timeoutMS": 60000,
  "concurrency": 2
}
```

Will be enhanced during Phase 2 to include additional files and stricter thresholds.

---

## Baseline Updates

### How to Update This Document

After any phase completion or baseline change:

1. **Update the metric table** with new values
2. **Record the date** of verification
3. **Add any notes** about changes
4. **Commit with clear message**: `docs: update mutation baseline - {phase} complete`

### Update Template

```markdown
#### Module: [Name] (`file/path.ts`)

| Metric | Value | Status |
|--------|-------|--------|
| **Mutations Created** | XXX | ✅ |
| **Mutations Killed** | XXX | ✅ |
| **Kill Rate** | XX% | ✅ |
| **Test File** | `tests/...` | ✅ |
| **Test Count** | XX tests | ✅ |
| **Last Verified** | YYYY-MM-DD | ✅ |
```

### Change History

| Date | Change | Phase | Verified By |
|------|--------|-------|-------------|
| 2026-03-10 | Backend baseline set: 454/454 (100%) | Phase 1 Complete | @javier |
| 2026-03-10 | Frontend Phase 1 configuration complete | Phase 1 Complete | @javier |
| TBD | Frontend Phase 2 implementation begins | Phase 2 Start | @javier |
| TBD | Frontend utility functions complete | Phase 2 Sprint 1 | TBD |
| TBD | Frontend React hooks complete | Phase 2 Sprint 2 | TBD |
| TBD | Frontend components complete | Phase 2 Sprint 3 | TBD |

---

## Monitoring & Alerts

### Current Monitoring

**Backend (Active)**:
- ✅ CI/CD gate enforces 100% kill rate
- ✅ Automatic rollback on >10% drop
- ✅ Manual review required on 5-10% drop
- ✅ Weekly metrics digest to team

**Frontend (Ready for Phase 2)**:
- 📋 CI/CD gate configured but not enforced yet
- 📋 Stryker reports generated in CI
- 📋 Will enforce ≥80% kill rate when Phase 2 begins

### Alert Thresholds

| Metric | Threshold | Action | Owner |
|--------|-----------|--------|-------|
| Backend kill rate drops >10% | <90% | Automatic rollback | @github-actions |
| Backend kill rate drops 5-10% | 90-95% | Manual review + fix | @team-lead |
| Backend kill rate drops <5% | 95-100% | Developer fixes | @developer |
| Multiple modules affected | Any | Escalate P1 incident | @devops-team |

---

## Related Documentation

- **[MUTATION_TESTING.md](MUTATION_TESTING.md)** - Complete guide and team processes
- **[MUTATION_ROLLBACK.md](MUTATION_ROLLBACK.md)** - Emergency rollback procedures
- **Backend Config**: `gee-backend/.cosmic-ray.toml`
- **Frontend Config**: `consorcio-web/stryker.config.json`
- **CI/CD Workflow**: `.github/workflows/mutation-testing.yml`
- **Phase 2 Plan**: `openspec/changes/frontend-mutation-expansion/PHASE_2_REAL_HOOKS.md`

---

## Contact & Questions

For baseline questions or updates:
- **Backend mutations**: @javier (owner)
- **Frontend mutations**: @javier (owner)
- **CI/CD gates**: @devops-team
- **Policy questions**: @team-lead

Last updated: 2026-03-10
Maintained by: @javier
