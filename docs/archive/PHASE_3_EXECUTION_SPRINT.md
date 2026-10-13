# Phase 3.1 + 3.2: Complete Sprint Execution Plan

**Start Date**: March 11, 2026
**Status**: ✅ INITIATED
**Branch**: `sdd/backend-mutation-fixes`

---

## PHASE 3.1: Priority Components (4-5 hours)

### Target: Get 3-5 components to 50%+ kill rate

**Strategic Components** (by testability & impact):
1. **LoginForm.tsx** - High logic, manageable mutations
2. **ProfilePanel.tsx** - Moderate complexity
3. **AdminDashboard.tsx** - Core admin logic
4. **MapControls.tsx** - Map-specific logic
5. **ImageUploadModal.tsx** - Modal with validation

### Execution Pattern Per Component:
1. Run Stryker baseline
2. Analyze escaped mutations
3. Strengthen tests:
   - Exact value assertions (`toBe()` not `toBeTruthy()`)
   - Parametrized tests for branches
   - Edge cases: null, undefined, empty values
   - Error paths explicit
4. Re-run Stryker until 50%+ achieved
5. Atomic commits after each improvement
6. Document findings

---

## PHASE 3.2: High-ROI Utilities (5-8 hours)

### Target: Get 8-15 utilities to 80%+ kill rate

**Strategic Utilities** (by ROI & impact):
1. **src/lib/api/core.ts** - API core functions (highest impact)
2. **src/lib/formatters.ts** - Data formatting
3. **src/lib/validators.ts** - Validation functions
4. **src/lib/typeGuards.ts** - Type guards
5. **src/utils/helpers.ts** - General helpers
6. **src/lib/errorHandler.ts** - Error utilities
7. **src/lib/constants.ts** - Constants (if applicable)
8. Additional utilities as time permits (10-15 total)

### Execution Pattern Per Utility:
1. Analyze existing tests
2. Run Stryker baseline
3. Identify ALL escaped mutations
4. Strengthen tests AGGRESSIVELY:
   - **Exact values ONLY**: `toBe()` not `toBeTruthy()`
   - **Parametrized tests**: `test.each([...])` for all branches
   - **Edge cases**: null, undefined, empty, boundaries
   - **Error cases**: Invalid inputs, type mismatches
   - **Assertions on every line**: Every mutation caught
5. Re-run Stryker until 80%+ achieved
6. Atomic commits
7. Document patterns

---

## Current Status

### Prepared
- ✅ Branch `sdd/backend-mutation-fixes` active
- ✅ Test suite mostly clean (2 unrelated hook failures to fix separately)
- ✅ Stryker baseline configs ready
- ✅ Phase 3 plan documented

### Ready to Execute
- Component test files exist for all Phase 3.1 targets
- Utility test files exist for Phase 3.2 targets
- Stryker infrastructure in place

---

## Metrics to Track

### Per Component (Phase 3.1)
- Component | Before | After | Target | Status
- LoginForm.tsx | ? | ? | 50%+ | 🚀
- ProfilePanel.tsx | ? | ? | 50%+ | 🚀
- AdminDashboard.tsx | ? | ? | 50%+ | 🚀
- MapControls.tsx | ? | ? | 50%+ | 🚀
- ImageUploadModal.tsx | ? | ? | 50%+ | 🚀

### Per Utility (Phase 3.2)
- Utility | Before | After | Target | Status
- api/core.ts | ? | ? | 80%+ | 🚀
- formatters.ts | ? | ? | 80%+ | 🚀
- validators.ts | ? | ? | 80%+ | 🚀
- typeGuards.ts | ? | ? | 80%+ | 🚀
- helpers.ts | ? | ? | 80%+ | 🚀
- errorHandler.ts | ? | ? | 80%+ | 🚀

---

## Next Steps

1. Start Phase 3.1: LoginForm baseline
2. Run mutation tests per component
3. Strengthen tests iteratively
4. Move to Phase 3.2 utilities
5. Document all patterns
6. Final PR with comprehensive summary

**ETA**: 8-12 hours total execution
