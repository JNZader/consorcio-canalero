# Phase 2 Frontend Mutation Testing - Implementation Task Brief

**Status**: Ready for specialist implementation  
**Priority**: High  
**Complexity**: Medium-High  
**Estimated Effort**: 4-6 hours

---

## Objective

Complete Phase 2 of frontend mutation testing for consorcio-web project, achieving ≥80% mutation score for all 9 React hooks.

---

## Current Status

### Completed ✅
1. **Stryker Phase 2 Configuration** - Created `stryker-phase-2.config.json`
2. **8 of 9 Hook Test Files** - All tests PASS:
   - ✅ `useSelectedImage.test.ts` (localStorage persistence, validation)
   - ✅ `useAuth.test.ts` (auth store integration, Zustand)
   - ✅ `useCaminosColoreados.test.ts` (road coloring API)
   - ✅ `useContactVerification.test.ts` (contact flow)
   - ✅ `useGEELayers.test.ts` (GEE layers integration)
   - ✅ `useImageComparison.test.ts` (image comparison logic)
   - ✅ `useInfrastructure.test.ts` (infrastructure data fetching)
   - ✅ `useMapReady.test.ts` (Leaflet map lifecycle)

### Blocked ⚠️
- **`useJobStatus.test.ts`** - 2 tests failing due to Vitest fake timers not properly resolving async promises in setInterval callbacks

---

## Key Problem: useJobStatus Timer Mocking

### The Issue
The `useJobStatus` hook:
- Sets up a 2-second polling interval
- Calls an async `checkStatus()` function inside the interval
- Test expects state to update after timer advancement

Tests using `vi.advanceTimersByTime()` and `vi.advanceTimersByTimeAsync()` don't properly resolve the promises from mocked `apiFetch` calls.

### Current Failing Tests (2)
```
× "catches mutation: should set isLoading to false on SUCCESS"
× "catches mutation: should set isLoading to false on FAILURE"
```

Both expect `isLoading` to be `false` after advancing timers 2000ms, but state doesn't update.

### Why Some Tests Pass
Tests checking callbacks (`onCompleted`) or simple facts PASS:
- "should call onCompleted callback" → ✓ PASS
- "should not call onCompleted if result is undefined" → ✓ PASS

This suggests the async functions ARE executing, but state updates aren't being captured.

### Root Cause Analysis
1. `apiFetch` is a mock that resolves/rejects immediately
2. When `checkStatus()` is called via `setInterval`, it awaits `apiFetch`
3. The promise resolves, but the state setter (`setIsLoading(false)`) happens asynchronously
4. Timer advancement doesn't guarantee React state updates are flushed

### Solution Approaches to Evaluate

**Option A**: Use `waitFor` with real timers (simpler but slower)
```typescript
const { result } = renderHook(() => useJobStatus('job-1'));

await waitFor(() => {
  expect(result.current.isLoading).toBe(false);
}, { timeout: 5000 });
```

**Option B**: Mock `apiFetch` to resolve synchronously (hacky)
```typescript
mockApiFetch.mockImplementation(async () => ({
  job_id: 'job-1',
  status: 'SUCCESS',
}));
```

**Option C**: Refactor hook to not use async in interval (requires hook change)
- Have hook call sync `checkStatus` that starts async work in parallel
- Not ideal for production code

**Option D**: Use custom timer wrapper that properly handles async (complex)
```typescript
await act(async () => {
  await vi.runAllTimersAsync(); // Maybe this?
});
```

### Recommended Path
**Option A** (`waitFor` with real timers) is most maintainable and least invasive:
- Tests become:

```typescript
it('catches mutation: should set isLoading to false on SUCCESS', async () => {
  vi.useRealTimers(); // Use real timers for this test
  
  mockApiFetch.mockResolvedValue({
    job_id: 'job-1',
    status: 'SUCCESS',
    result: 'done',
  });

  const { result } = renderHook(() => useJobStatus('job-1'));

  // Wait for async operation to complete naturally
  await waitFor(() => {
    expect(result.current.isLoading).toBe(false);
  }, { timeout: 5000 });
});
```

---

## Next Steps

### 1. Fix useJobStatus Tests (1-2 hours)
- [ ] Choose and implement one of the 4 approaches above
- [ ] Verify all 9 hook test files pass: `npm run test:run -- tests/hooks/`
- [ ] Commit: `test(hooks): fix useJobStatus timer handling`

### 2. Run Mutation Tests (1 hour)
- [ ] Run: `npm run mutation:run -- --configFile stryker-phase-2.config.json`
- [ ] Generate report: `consorcio-web/reports/phase-2-mutation/index.html`
- [ ] Document results by hook:
  ```
  Hook                    | Score | Status | Weak Tests
  ─────────────────────────┼───────┼────────┼──────────
  useSelectedImage        | 85%   | ✅     | -
  useAuth                 | 92%   | ✅     | -
  ...
  ```

### 3. Add Missing Tests (2-3 hours)
For any hook below 80%, identify "survived mutations" and add tests:
- Look at mutation report's "survived mutations" section
- Each survived mutation = test gap
- Add `describe.each()` parametrized test with boundary values:
  ```
  - Empty strings, null, undefined
  - Zero, negative, large numbers
  - Empty arrays, single item, multiple items
  - Error conditions (network, timeout, invalid data)
  ```

### 4. Iterate Until All ≥80% (1-2 hours)
- [ ] Re-run mutation tests
- [ ] Fix remaining weak tests
- [ ] Commit: `test(mutation): Phase 2 hooks complete - all ≥80% score`

### 5. Final Validation (30 min)
- [ ] All unit tests pass: `npm run test:run -- tests/hooks/`
- [ ] All mutation tests ≥80%: `npm run mutation:run`
- [ ] No type errors: `npm run typecheck`
- [ ] No linting errors: `npm run lint`

---

## Test File Locations

```
consorcio-web/
├── src/hooks/
│   ├── useAuth.ts
│   ├── useSelectedImage.ts
│   ├── useJobStatus.ts ⚠️ (timer issue)
│   ├── useMapReady.ts
│   ├── useInfrastructure.ts
│   ├── useGEELayers.ts
│   ├── useImageComparison.ts
│   ├── useContactVerification.ts
│   └── useCaminosColoreados.ts
│
└── tests/hooks/
    ├── setup.ts (shared fixtures & mocks)
    ├── useAuth.test.ts ✅
    ├── useSelectedImage.test.ts ✅
    ├── useJobStatus.test.ts ⚠️ (2 failing)
    ├── useMapReady.test.ts ✅
    ├── useInfrastructure.test.ts ✅
    ├── useGEELayers.test.ts ✅
    ├── useImageComparison.test.ts ✅
    ├── useContactVerification.test.ts ✅
    └── useCaminosColoreados.test.ts ✅
```

---

## Setup & Mocking Reference

### Available Fixtures (in `setup.ts`)
```typescript
- mockSupabaseUser()                 // Mock Supabase user
- mockSupabaseSession()              // Mock auth session
- createMockAuthStore()              // Mock Zustand auth store
- createMockLeafletMap()             // Mock Leaflet map
- createMockApiClient()              // Mock API client
- createMockSupabaseClient()         // Mock Supabase client
- createMockFeatureCollection()      // Mock GEE feature collection
- createMockCaminosColoreados()      // Mock road coloring data
- setupHooksTests()                  // beforeEach cleanup
```

### Key Patterns
```typescript
// Parametrized tests for mutation catching
describe.each([
  { input: '', expected: false },
  { input: null, expected: false },
  { input: 'valid', expected: true },
])('validation', ({ input, expected }) => {
  // Test code
});

// Mock localStorage
localStorage.getItem = vi.fn();
localStorage.setItem = vi.fn();
localStorage.removeItem = vi.fn();

// Mock async operations
vi.mock('../../src/lib/api', () => ({
  apiFetch: vi.fn(),
}));
```

---

## Stryker Configuration

**File**: `consorcio-web/stryker-phase-2.config.json`

```json
{
  "testRunner": "command",
  "commandRunner": {
    "command": "npm run test:run -- tests/hooks/"
  },
  "mutate": [
    "src/hooks/useAuth.ts",
    "src/hooks/useSelectedImage.ts",
    "src/hooks/useJobStatus.ts",
    "src/hooks/useMapReady.ts",
    "src/hooks/useInfrastructure.ts",
    "src/hooks/useGEELayers.ts",
    "src/hooks/useImageComparison.ts",
    "src/hooks/useContactVerification.ts",
    "src/hooks/useCaminosColoreados.ts"
  ],
  "thresholds": {
    "high": 85,
    "low": 80,
    "break": 80
  }
}
```

---

## Commands Reference

```bash
# Run all hook tests
npm run test:run -- tests/hooks/

# Run specific hook test
npm run test:run -- tests/hooks/useSelectedImage.test.ts

# Run mutation tests
npm run mutation:run -- --configFile stryker-phase-2.config.json

# View mutation report
open reports/phase-2-mutation/index.html

# Type check
npm run typecheck

# Lint
npm run lint
```

---

## Success Criteria

- [ ] All 9 hooks have test files
- [ ] All unit tests pass (9/9): `npm run test:run -- tests/hooks/`
- [ ] All hooks ≥80% mutation score
- [ ] Mutation report generated: `reports/phase-2-mutation/index.html`
- [ ] No type errors: `npm run typecheck`
- [ ] No linting errors: `npm run lint`
- [ ] Clean git history: atomic commits with descriptive messages
- [ ] Documentation updated if needed

---

## Related Phase 1 Results

**Phase 1 (Utilities)**: ✅ Complete - 84.09% mutation score
- `src/lib/formatters.ts` - ✅ tested
- `src/lib/validators.ts` - ✅ tested

**Configuration Reference**: `stryker-phase-1.config.json`

---

## Questions & Escalation

If you encounter:
- **React testing library** issues → Consult `@testing-library/react` docs
- **Vitest timer** issues → Check Vitest docs on `useFakeTimers()`
- **Stryker** mutation issues → Review mutation report for specific escaped mutations
- **Architecture** questions → Refer to `/CLAUDE.md` mutation testing section
- **Git/CI** issues → Check `.github/workflows/`

---

**Ready for implementation. Good luck! 🚀**
