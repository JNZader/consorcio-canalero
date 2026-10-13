# Phase 2 Adaptation Summary: Real Hooks

**Date**: 2026-03-09  
**Status**: PHASE 2 ADAPTED FOR REAL CONSORCIO-WEB HOOKS  
**Scope**: 9 production hooks from actual codebase  

---

## What Changed

### FROM (Original Plan)
- **8 theoretical hooks**: useDebounce, useLocalStorage, useTheme, useModal, usePagination, useForm, useAuth (generic), useAsync
- **~17 hours effort** (based on "typical" hooks)
- **Generic mocking patterns** (localStorage, timers, etc.)
- **Test count**: ~25 tests

### TO (Real Hooks)
- **9 REAL production hooks from consorcio-web**:
  1. useAuth.ts (243 lines, Zustand + role logic)
  2. useSelectedImage.ts (206 lines, localStorage + validation)
  3. useJobStatus.ts (68 lines, polling + async)
  4. useMapReady.ts (91 lines, Leaflet lifecycle)
  5. useInfrastructure.ts (57 lines, Promise.all + API)
  6. useGEELayers.ts (166 lines, GEE integration)
  7. useImageComparison.ts (168 lines, dual image state)
  8. useContactVerification.ts (206 lines, OAuth + OTP)
  9. useCaminosColoreados.ts (116 lines, domain-specific)

- **~23 hours effort** (realistic for production code)
- **Specialized mocking**: Zustand stores, Supabase client, GEE API, Leaflet, localStorage with validation
- **Test count**: ~70 tests
- **Real mutation detection** (not theoretical escape scenarios)

---

## Key Adaptations

### 1. Setup.ts Expanded
Added 3 new mock factories:
- ✅ `mockAuthStore()` - Zustand store structure
- ✅ `mockSupabaseClient()` - OAuth and OTP flows
- ✅ `mockLeafletMap()` - Leaflet lifecycle

### 2. Tasks Restructured
- **2.1**: Foundation (setup.ts) - 2 hours (was 1.5h)
- **2.2-2.10**: Real hook tests (9 hooks) - 18 hours (was 8 hooks × 2h)
- **2.11**: Stryker + Docs - 2.5 hours (was 2h as 2.10)

Total: **11 tasks** (was 10) | **23 hours** (was ~17h)

### 3. Mutation Detection Patterns
Real hooks catch production-grade mutations:
- **useAuth**: Zustand selector, role array checks, conditional logic
- **useSelectedImage**: JSON validation, storage event sync, guard functions
- **useJobStatus**: Polling interval, status comparisons, clearInterval
- **useMapReady**: Timer scheduling, event cleanup, RAF cancellation
- **useInfrastructure**: Promise.all order, endpoint assignments
- **useGEELayers**: Partial load success, validation logic
- **useImageComparison**: State preservation, isReady logic
- **useContactVerification**: Email validation guard, OAuth flow
- **useCaminosColoreados**: Response parsing, metadata extraction

### 4. Documentation Created
Three new reference documents:
- **PHASE_2_REAL_HOOKS.md**: Comprehensive hook-by-hook strategy
- **PHASE_2_IMPLEMENTATION_CHECKLIST.md**: Task-by-task execution guide
- **REAL_HOOKS_TESTING_PATTERNS.md**: Testing patterns reference

---

## Files Modified/Created

### Spec Files
- ✏️ `/openspec/changes/frontend-mutation-expansion/tasks.md` - Phase 2 section expanded (11 tasks)

### Documentation Created
- ✨ `/openspec/changes/frontend-mutation-expansion/PHASE_2_REAL_HOOKS.md` (395 lines)
- ✨ `consorcio-web/PHASE_2_IMPLEMENTATION_CHECKLIST.md` (500+ lines)
- ✨ `consorcio-web/REAL_HOOKS_TESTING_PATTERNS.md` (450+ lines)

---

## Success Metrics

### Phase 2 Targets
| Metric | Target | Rationale |
|--------|--------|-----------|
| Hook test files | 9 | All real production hooks covered |
| Total test cases | 70+ | ~8 tests per hook |
| Mutation score per hook | ≥80% | Production-grade quality |
| Setup time | 2h | More mocks = longer setup |
| Test writing time | 18h | Real hooks are more complex |
| Stryker execution | <2 min | ~70 tests × 2 hooks = 140 mutations |
| Zero killed tests | 100% | All tests must pass |
| Documentation | 3 guides | Implementation, patterns, reference |

---

## Real Hook Complexity Analysis

```
useAuth (243 lines)
├── Zustand store selector (useShallow optimization)
├── Role checking utilities (5 memoized functions)
├── Auth actions (5 async functions via authLib)
├── Derived state (3 computed values)
└── Mutation Tests: 14+ (highest priority)

useSelectedImage (206 lines)
├── localStorage read/write with validation
├── Custom event dispatch for same-tab sync
├── Storage event listener for cross-tab sync
├── Type guard integration (isValidSelectedImage)
├── 2 hook variants (read/write vs read-only)
└── Mutation Tests: 12+

useJobStatus (68 lines)
├── Polling interval (setInterval)
├── Status transitions (PENDING → SUCCESS/FAILURE)
├── onCompleted callback with dependency handling
├── API integration (apiFetch)
└── Mutation Tests: 12+

useMapReady (91 lines)
├── 5 invalidateSize scheduling paths
├── 3 event listeners (resize, visibilitychange, custom event)
├── ResizeObserver integration
├── RAF scheduling with cleanup
└── Mutation Tests: 10+

useInfrastructure (57 lines)
├── Promise.all dual API fetch
├── Loading state management
├── createAsset POST action
└── Mutation Tests: 10+

useGEELayers (166 lines)
├── Parallel layer loading
├── GeoJSON validation (parseFeatureCollection)
├── Partial load handling
├── Derived state (layersArray)
└── Mutation Tests: 11+

useImageComparison (168 lines)
├── Dual image state (left + right)
├── localStorage persistence
├── State preservation logic (||)
├── Event dispatching
└── Mutation Tests: 12+

useContactVerification (206 lines)
├── OAuth flow (signInWithOAuth)
├── Magic link OTP flow (signInWithOtp)
├── Email validation guard
├── Mantine notifications integration
├── Supabase client integration
└── Mutation Tests: 12+

useCaminosColoreados (116 lines)
├── GEE caminos endpoint
├── Response structure parsing
├── Consorcios metadata extraction
└── Mutation Tests: 10+
```

**Total Real Hook Code**: ~1,321 lines  
**Total Test Code Target**: ~1,400 lines (≈103 test cases)

---

## Phase 2 Execution Plan

### Wave 1: Setup (Day 1)
- [ ] Create `src/hooks/__tests__/setup.ts` (2h)
  - 6 mock factories: renderHookWithProviders, mockLocalStorage, mockAuthStore, mockSupabaseClient, mockFetchAPI, mockLeafletMap
  - All using Vitest (`vi.fn()`, `vi.useFakeTimers()`)

### Wave 2: Hook Tests (Days 2-4)
Parallel after 2.1 complete:
- [ ] useAuth (3h) - Zustand, roles, memoization
- [ ] useSelectedImage (2.5h) - Storage, validation, sync
- [ ] useJobStatus (2.5h) - Polling, timers, callbacks
- [ ] useMapReady (2.5h) - Lifecycle, cleanup, listeners
- [ ] useInfrastructure (2h) - Promise.all, API, state
- [ ] useGEELayers (2.5h) - Validation, partial load
- [ ] useImageComparison (2.5h) - State preservation
- [ ] useContactVerification (2.5h) - OAuth, OTP, validation
- [ ] useCaminosColoreados (2h) - Parsing, metadata

### Wave 3: Mutation Testing (Day 5)
- [ ] Create `stryker-batch-2.config.json` (0.5h)
- [ ] Run Stryker: `npm run test:mutation:batch-2` (1h execution)
- [ ] Fix any mutations <80% per hook (1-2h)
- [ ] Update documentation (1h)

---

## Testing Strategy by Hook

### High Priority (Complex)
1. **useAuth** - Core authentication, role-based access
   - Zustand shallow selector memoization
   - Role checking arrays and boolean flags
   - Auth action callbacks

2. **useContactVerification** - Oauth flow critical
   - signInWithOAuth redirect handling
   - Magic link OTP validation
   - Email guard function

### Medium Priority (Standard)
3. **useSelectedImage** - Core feature (image selection)
4. **useJobStatus** - Job polling critical for long operations
5. **useGEELayers** - Data loading with validation

### Lower Priority (Infrastructure)
6. **useMapReady** - Leaflet lifecycle
7. **useInfrastructure** - API integration
8. **useImageComparison** - Optional feature
9. **useCaminosColoreados** - Optional feature

---

## Mutation Test Targets

### Critical Mutations (Must Catch)
1. Removing validation guards (useSelectedImage, useContactVerification)
2. Changing polling interval (useJobStatus)
3. Missing cleanup functions (useMapReady)
4. Promise.all order (useInfrastructure)
5. Conditional negation (useAuth role checks)

### Important Mutations (Should Catch)
6. Storage key changes (useSelectedImage)
7. Event dispatch detail (useImageComparison)
8. Callback invocation conditions (useAuth, useContactVerification)
9. Loading state placement (useInfrastructure)
10. Array mutations ([prev] vs [] vs [...prev, new])

---

## Next Steps

### Immediate (Now)
1. ✅ Review PHASE_2_REAL_HOOKS.md for hook details
2. ✅ Review PHASE_2_IMPLEMENTATION_CHECKLIST.md for task breakdown
3. ✅ Review REAL_HOOKS_TESTING_PATTERNS.md for testing patterns

### This Sprint
1. `/sdd:apply frontend-mutation-expansion` - Run Phase 2 implementation
2. Start with Task 2.1 (setup.ts foundation)
3. Parallel tasks 2.2-2.10 after 2.1 complete
4. Task 2.11 (Stryker + docs)

### Success Criteria
- ✅ All 9 hooks ≥80% mutation score
- ✅ 70+ total test cases
- ✅ <2 min Stryker execution
- ✅ 0 killed tests
- ✅ Full documentation
- ✅ No main branch regressions

---

## Key Insights

1. **Real code is messier**: useAuth has memoization patterns (useShallow, useCallback) that theoretical examples miss

2. **External dependencies matter**: Testing Zustand, Supabase, Leaflet requires specific mock patterns

3. **Test coverage compounds**: 9 hooks with 8+ tests each = 70+ tests, but each test is 10-30 lines = ~1,400 lines of test code

4. **Mutation detection is context-specific**: 
   - useAuth needs role array checks
   - useSelectedImage needs storage sync validation
   - useJobStatus needs polling termination
   - Each hook has unique mutation patterns

5. **Effort scales with integration**: 
   - Simple hooks (useCaminosColoreados): 2h + 10 tests
   - Complex hooks (useAuth, useContactVerification): 3h + 14 tests

---

## Resources for Implementation

### Files to Reference
- Hook implementations: `src/hooks/use*.ts` (9 files)
- Existing tests: `src/lib/utils/__tests__/*.test.ts` (Phase 1 patterns)
- Phase 2 guide: `PHASE_2_REAL_HOOKS.md`
- Implementation checklist: `PHASE_2_IMPLEMENTATION_CHECKLIST.md`
- Testing patterns: `REAL_HOOKS_TESTING_PATTERNS.md`

### External References
- [Vitest Hooks Documentation](https://vitest.dev/guide/testing-library.html)
- [Zustand Testing Guide](https://github.com/pmndrs/zustand/blob/main/docs/testing.md)
- [Stryker JavaScript Documentation](https://stryker-mutator.io/docs/stryker-js/introduction/)
- [Supabase Client Testing](https://supabase.com/docs/reference/javascript/auth-signinwithoauth)

---

## Timeline Estimate

| Phase | Duration | Dependencies |
|-------|----------|--------------|
| Phase 1: Utilities (complete) | 12h | None |
| Phase 2: Real Hooks (this) | 23h | Phase 1 baseline |
| Phase 3: Store/Components | 20h | Phase 2 test patterns |
| Phase 4: CI/CD | 10h | Phase 3 complete |
| **TOTAL** | **~65 hours** | 6-8 working days |

---

## Success Criteria Checklist

Before moving to Phase 3:

- [ ] All 9 hook test files created (`2.2` - `2.10`)
- [ ] setup.ts with 6+ mock factories (`2.1`)
- [ ] 70+ total test cases across all hooks
- [ ] Each hook ≥80% mutation score
- [ ] stryker-batch-2.config.json created
- [ ] HTML report at `coverage/mutation-report/batch-2/`
- [ ] MUTATION_TESTING.md updated with Phase 2 section
- [ ] 0 killed tests (all passing)
- [ ] Stryker execution <2 minutes
- [ ] No regressions on Phase 1 tests

---

**Status**: Ready for `/sdd:apply frontend-mutation-expansion` Phase 2 implementation

