# Proposal: Frontend Mutation Testing Expansion

## Intent

Expand mutation testing coverage from 2 files (currently at 100% mutation score) to 20+ critical frontend files to establish production-grade defect detection across utility libraries, custom hooks, state management, and key page components. This ensures code quality is validated not just by traditional unit tests, but by verifying that test suites can effectively catch introduced bugs and regressions.

## Scope

### In Scope

#### Core Deliverables
- Add 20+ files to Stryker mutation testing scope:
  - **Utility Libraries** (5 files): formatters.ts, validators.ts, query.ts, geeClient.ts, API helpers
  - **Custom Hooks** (8 files): useAuth.ts, useSelectedImage.ts, useComparison.ts, useGEELayers.ts, useJobStatus.ts, useColoreados.ts, useInfrastructure.ts, and 1 additional
  - **Store Utilities** (4 files): authStore.ts, mapStore.ts, dashboardStore.ts, and 1 additional
  - **Key Page Components** (3+ files): ReportCard.tsx, VerificationForm.tsx, AdminPanel.tsx

#### Test Coverage
- Write 50-100 new tests to support mutation coverage for added files
- Ensure all mutation-escape scenarios have test cases
- Increase frontend test count from 935 to ~1000+

#### CI/CD Integration
- Stryker report generation in GitHub Actions pipeline
- Mutation score tracking per file and overall
- Store mutation metrics for trend analysis

#### Quality Gates
- Minimum 80% mutation score across all added files
- Categorize and track all detected mutants
- Document defect detection improvements

### Out of Scope

- Refactoring existing code (only fixing to support mutation testing where necessary)
- Backend mutation testing expansion (future initiative)
- Visual regression testing (separate concern)
- Performance optimization based on mutation insights (future work)

## Approach

### Phase 1: Preparation
1. Analyze current Stryker configuration and scoring methodology
2. Identify file dependencies and test prerequisites
3. Create baseline mutation score expectations per file category

### Phase 2: Incremental Expansion
1. **Batch 1 (Utilities)**: formatters.ts, validators.ts, query.ts, geeClient.ts
   - Highest ROI, typically deterministic, fewer external dependencies
   - Write 15-20 new tests
2. **Batch 2 (Hooks)**: useAuth.ts, useSelectedImage.ts, useComparison.ts, useGEELayers.ts
   - Medium complexity, requires mock setup and React context
   - Write 20-30 new tests
3. **Batch 3 (Store & Components)**: Store utilities and page components
   - Higher complexity, requires state management mocks
   - Write 15-20 new tests

### Phase 3: Validation & Reporting
1. Generate Stryker reports with mutation matrix
2. Validate 80%+ mutation score across all files
3. Document defect detection rate improvements
4. Establish baseline for continuous monitoring

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `consorcio-web/src/lib/` | Modified | Add utilities (formatters, validators, query, geeClient) to mutation scope |
| `consorcio-web/src/hooks/` | Modified | Add 7-8 custom hooks to mutation scope |
| `consorcio-web/src/store/` | Modified | Add Zustand store utilities to mutation scope |
| `consorcio-web/src/pages/` | Modified | Add key page components (ReportCard, VerificationForm, AdminPanel) to mutation scope |
| `.stryker-config.json` | Modified | Update Stryker configuration to include new files |
| `consorcio-web/__tests__/` | New | Add 50-100 new test files to support mutation coverage |
| `.github/workflows/` | Modified | Update CI/CD to generate and track Stryker reports |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Mutation score < 80% on initial files | Medium | Start with utilities (lowest complexity), iterate if needed, add tests incrementally |
| Tests take too long to write | Low | Reuse existing test patterns from 2 baseline files, leverage testing utilities and mocks |
| CI/CD pipeline slowdown | Low | Run Stryker on schedule or for mutation-related PRs only; cache results |
| External API mocking complexity (GEE, API calls) | Medium | Use existing mock infrastructure; if missing, add mock setup in Phase 1 |
| State management testing complexity (Zustand) | Medium | Document store testing patterns; reuse hooks mocking patterns |

## Rollback Plan

1. **If mutation score < 80% on added files**: Remove those files from Stryker scope, iterate with more tests, and re-add
2. **If CI/CD breaks**: Disable Stryker in pipeline, diagnose in feature branch, re-enable once validated
3. **If test writing falls behind schedule**: Prioritize high-risk utilities first; defer hook/component expansion to next phase
4. **Complete revert**: Remove all new test files and revert `.stryker-config.json` to original state

## Dependencies

- Stryker configured and working (already done: reportsResolve.ts, tramitesCanonical.ts)
- Testing infrastructure in place (Jest, React Testing Library)
- Mock setup for external dependencies (GEE API, HTTP calls, Zustand stores)
- CI/CD pipeline with Node.js and npm (already deployed)

## Success Criteria

- [ ] All 20+ files added to Stryker scope and reporting
- [ ] Minimum 80% mutation score achieved across all added files
- [ ] 50-100 new tests written and passing
- [ ] Stryker reports generated in GitHub Actions (visible in PR checks)
- [ ] Mutant categorization documented (killed, survived, equivalent)
- [ ] Baseline established for ongoing mutation score monitoring
- [ ] Test count increases from 935 to 1000+
- [ ] Defect detection rate demonstrably improves (fewer escaped mutations vs. baseline)
- [ ] No regression in existing test suite (all 935 baseline tests still pass)

---

**Change**: frontend-mutation-expansion  
**Location**: openspec/changes/frontend-mutation-expansion/proposal.md  
**Status**: Ready for Review  
**Next Step**: Specification (sdd:spec) to detail requirements and acceptance criteria
