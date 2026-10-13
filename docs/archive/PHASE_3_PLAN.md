# Phase 3: Mutation Testing Expansion - Plan & Roadmap

**Date**: March 11, 2026  
**Status**: Ready to Launch  
**Prerequisite**: Phase 2 Complete (All 9 hooks ≥70%)

---

## 📊 Phase 2 Completion Summary

**Status**: ✅ **COMPLETE**

| Hook | Before | After | Status |
|------|--------|-------|--------|
| useInfrastructure | 88.46% | 88.46% | ✅ PASS |
| useMapReady | 84.21% | 84.21% | ✅ PASS |
| useAuth | 76.39% | 76.39% | ✅ PASS |
| useImageComparison | 75.00% | 75.00% | ✅ PASS |
| useSelectedImage | 75.73% | 75.73% | ✅ PASS |
| useJobStatus | 73.68% | 73.68% | ✅ PASS |
| **useCaminosColoreados** | **41.67%** | **79.17%** | ✅ PASS |
| **useContactVerification** | **58.72%** | **87.16%** | ✅ PASS |
| **useGEELayers** | **21.18%** | **70.77%** | ✅ PASS |

**Results**:
- ✅ All 9/9 hooks at ≥70% mutation kill rate
- ✅ Total improvement: +119 mutations killed (+23.15%)
- ✅ Code refactored for better testability
- ✅ 71+ new comprehensive unit tests

---

## 🎯 Phase 3: Goals & Objectives

Phase 3 expands mutation testing to **components** and **utilities**, building on Phase 2's success.

### Primary Objectives

1. **Expand mutation testing to components** (React components)
   - Target: 15-20 critical components
   - Goal: ≥70% mutation kill rate per component
   - Effort: Medium-High

2. **Expand mutation testing to utilities/helpers** (Pure functions)
   - Target: 10-15 utility files
   - Goal: ≥80% mutation kill rate (utilities should be higher)
   - Effort: Low-Medium

3. **Establish mutation testing CI/CD gates**
   - Enforce ≥70% kill rate on all components
   - Enforce ≥80% kill rate on utilities
   - Block PRs that drop kill rate
   - Effort: Low

4. **Create mutation testing documentation & patterns**
   - Update CLAUDE.md with component testing patterns
   - Create style guide for strong assertions
   - Document common weak test patterns
   - Effort: Low-Medium

---

## 📋 Phase 3 Implementation Plan

### Phase 3.1: Components Mutation Testing (Week 1-2)

**Goal**: Get 15-20 critical components to ≥70% kill rate

**Priority Components** (by impact):
1. **MapaLeaflet.tsx** - Core map component, heavy logic
2. **MapaPage.tsx** - Map page container
3. **FormularioReporte.tsx** - Report form with validation
4. **FormularioSugerencia.tsx** - Suggestion form
5. **Header.tsx** - Navigation, auth state
6. **ProfilePanel.tsx** - User profile logic
7. **AdminDashboard.tsx** - Admin logic
8. **DashboardEstadisticas.tsx** - Stats calculations
9. **LoginForm.tsx** - Auth form logic
10. **ContactVerificationSection.tsx** - Verification logic
11. **ErrorBoundary.tsx** - Error handling
12. **ThemeToggle.tsx** - Theme switching
13. **ReportsPanel.tsx** - Reporting logic
14. **PadronPanel.tsx** - Padrón management
15. **TramitesPanel.tsx** - Process management

**Execution per Component**:
1. Run Stryker for the component
2. Analyze escaped mutations
3. Strengthen tests using Phase 2 patterns
4. Achieve ≥70% kill rate
5. Commit with message: `test: component mutation testing for <ComponentName>`

**Effort**: ~2-3 hours per component = 30-45 hours total

**Expected Result**: 15-20 components at ≥70% kill rate

---

### Phase 3.2: Utilities Mutation Testing (Week 3)

**Goal**: Get 10-15 utility files to ≥80% kill rate

**Priority Utilities** (by impact):
1. `src/lib/api/core.ts` - API request logic
2. `src/lib/errorHandler.ts` - Error handling
3. `src/lib/formatters.ts` - Data formatting
4. `src/lib/validators.ts` - Validation functions
5. `src/lib/typeGuards.ts` - Type guards
6. `src/lib/query.ts` - Query utilities
7. `src/lib/auth.ts` - Auth utilities
8. `src/lib/notifications.ts` - Notification system
9. `src/constants/index.ts` - Constants
10. `src/constants/mapStyles.ts` - Map styles
11. `src/lib/logger.ts` - Logging utility
12. `src/lib/theme.ts` - Theme utilities
13. `src/lib/basePath.ts` - Path utilities
14. `src/lib/env.ts` - Environment utilities
15. `src/lib/mantine.ts` - Mantine configuration

**Execution per Utility**:
1. Run Stryker for the file
2. Analyze escaped mutations
3. Strengthen tests (utilities usually simpler)
4. Achieve ≥80% kill rate
5. Commit with message: `test: utility mutation testing for <filename>`

**Effort**: ~1-2 hours per utility = 15-30 hours total

**Expected Result**: 10-15 utilities at ≥80% kill rate

---

### Phase 3.3: CI/CD Integration (Week 4)

**Goal**: Enforce mutation testing as part of CI/CD pipeline

**Tasks**:
1. Create GitHub Actions workflow for component mutation tests
2. Create GitHub Actions workflow for utility mutation tests
3. Set thresholds: 70% for components, 80% for utilities
4. Configure branch protection rules
5. Add status checks to PR requirements
6. Document exceptions process (rare)

**Effort**: ~5-8 hours

**Expected Result**:
- All mutation tests run on every PR
- PRs cannot merge if kill rate drops
- Clear pass/fail status in GitHub checks

---

### Phase 3.4: Documentation & Patterns (Ongoing)

**Goal**: Document mutation testing best practices for the team

**Tasks**:
1. **Update CLAUDE.md** with component testing patterns
2. **Create COMPONENT_TESTING_PATTERNS.md** with examples
3. **Create UTILITY_TESTING_PATTERNS.md** with examples
4. **Add mutation testing FAQ** to docs
5. **Create troubleshooting guide** for low kill rates

**Example Patterns**:
```typescript
// ❌ Weak - Component tests
expect(component).toBeTruthy();
expect(props).toBeDefined();

// ✅ Strong - Component tests
expect(screen.getByText('Expected Text')).toBeInTheDocument();
expect(screen.getByRole('button')).toHaveClass('active');
fireEvent.click(screen.getByRole('button'));
expect(onClickSpy).toHaveBeenCalledWith(expectedArg);
```

**Effort**: ~5-8 hours

**Expected Result**: Team has clear patterns and examples

---

## 📈 Success Metrics

### Quantitative Targets

| Metric | Target | Status |
|--------|--------|--------|
| Components at ≥70% kill rate | 15/15 | Pending |
| Utilities at ≥80% kill rate | 10/10 | Pending |
| Overall frontend kill rate | ≥75% | Pending |
| CI/CD mutation gates | Enforced | Pending |
| Documentation coverage | 100% | Pending |

### Qualitative Targets

- ✅ Team comfortable with mutation testing
- ✅ Weak tests identified and fixed
- ✅ Code quality improved
- ✅ Catch subtle bugs earlier
- ✅ Confidence in refactoring improvements

---

## 🔄 Timeline

| Phase | Duration | Status |
|-------|----------|--------|
| 3.1 - Components | Week 1-2 (30-45 hrs) | 📋 Ready |
| 3.2 - Utilities | Week 3 (15-30 hrs) | 📋 Ready |
| 3.3 - CI/CD | Week 4 (5-8 hrs) | 📋 Ready |
| 3.4 - Docs | Ongoing (5-8 hrs) | 📋 Ready |
| **TOTAL** | **4-5 weeks** | **~75-95 hrs** |

**Recommended Pace**:
- Phase 3.1: 1-2 components per day
- Phase 3.2: 2-3 utilities per day
- Phase 3.3: 1 day focused sprint
- Phase 3.4: Distribute across phases

---

## 📚 Reference Materials

### From Phase 2

All patterns from Phase 2 apply:
- Exact value assertions (not `toBeDefined()`)
- Parametrized tests for multiple cases
- Explicit error path testing
- Dependency array verification
- Strong branch coverage

See: Phase 2 commits with "test:" prefix

### Phase 2 Patterns to Reuse

1. **Extract helper functions** for testable logic
2. **Use test.each()** for parametrized variations
3. **Test error conditions** explicitly
4. **Verify state transitions** completely
5. **Use vi.mock()** for external dependencies

---

## 🚀 Getting Started with Phase 3

### Step 1: Set Up Stryker for Components
```bash
cd ~/consorcio-canalero/consorcio-web

# Create component-specific Stryker config
cp stryker-phase-2.config.json stryker-phase-3-components.config.json

# Update to target components instead of hooks
# mutate: ["src/components/**/*.tsx"]
# testPatterns: ["tests/components/**/*.test.tsx"]
```

### Step 2: Run Baseline
```bash
npx stryker run stryker-phase-3-components.config.json

# Check: reports/phase-3-mutation/
```

### Step 3: Start with Priority Component
```bash
# Pick MapaLeaflet.tsx - most critical
./run-stryker-for-component.sh MapaLeaflet

# Analyze escaped mutations
# Strengthen tests
# Re-run Stryker
# Commit
```

### Step 4: Document Progress
Update this file with actual results as you progress

---

## ✅ Decision Point: Continue with Phase 3?

**Prerequisites Met**:
- ✅ Phase 2 complete (9/9 hooks ≥70%)
- ✅ Refactoring patterns established
- ✅ Team familiar with mutation testing
- ✅ CI/CD infrastructure ready

**Recommendation**:
**YES - Proceed with Phase 3.1 (Components)**

Start with MapaLeaflet.tsx and establish component mutation testing pattern, then expand systematically.

---

## 📞 Support & Questions

For Phase 3 work:
- Questions on patterns? → Check Phase 2 commits
- Need help with component? → Ask in #engineering-practices
- Blocked on technical issues? → Contact @javier
- Want to propose different approach? → Create discussion issue

---

## 📝 Change Log

| Date | Change |
|------|--------|
| 2026-03-11 | Phase 3 plan created post-Phase 2 completion |
| 2026-03-11 | Ready for implementation |

---

**Next**: Begin Phase 3.1 - Components Mutation Testing
