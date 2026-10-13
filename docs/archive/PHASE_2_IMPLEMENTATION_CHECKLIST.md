# Phase 2: Real Hooks Implementation Checklist

**Quick Start Guide for /sdd:apply**  
**Target**: 9 real hooks, 70+ tests, 80%+ mutation score per hook

---

## Pre-Implementation Setup

- [ ] **Review PHASE_2_REAL_HOOKS.md** for hook-specific details
- [ ] **Review tasks.md Phase 2 section** (2.1 - 2.11)
- [ ] **Navigate to consorcio-web**: `cd /home/javier/consorcio-canalero/consorcio-web`
- [ ] **Branch ready**: Currently on `sdd/backend-mutation-fixes`, create feature branch if needed

---

## Task 2.1: Setup.ts (Foundation, 2 hours)

**File to Create**: `src/hooks/__tests__/setup.ts`

**Mocks Needed**:
- [ ] `renderHookWithProviders()` - Wrapper for hook rendering
- [ ] `mockLocalStorage()` - with getItem, setItem, removeItem, clear, length, key
- [ ] `mockAuthStore()` - Zustand authStore mock with all fields
- [ ] `mockSupabaseClient()` - auth.signInWithOAuth, auth.signInWithOtp, auth.signOut
- [ ] `mockFetchAPI()` - apiFetch wrapper
- [ ] `mockLeafletMap()` - invalidateSize, getContainer methods

**Testing Framework**: Vitest  
**Dependencies**: 
- @testing-library/react
- vitest 
- zustand (for authStore)

**Verification**: `grep -c "export function" src/hooks/__tests__/setup.ts` should show ≥6 exports

---

## Task 2.2: useAuth.test.ts (3 hours)

**Hook File**: `src/hooks/useAuth.ts`

**Test Scenarios** (14+ tests):
- [ ] Auto-initialization on mount
- [ ] Skip init if already initialized
- [ ] Login/logout/register actions
- [ ] Role checking (hasRole single & array)
- [ ] Role booleans (isAdmin, isOperador, isStaff, isCiudadano)
- [ ] canAccess with allowed roles
- [ ] isAuthenticated derived state (user && !loading && initialized)
- [ ] Memoization with useShallow
- [ ] Error state handling

**Key Mocks**:
- `mockAuthStore()` with user/profile/role data
- Zustand store selector override

**Mutation Focus**:
- Role array includes → !includes
- Conditional logic (&&, ||)
- Role === comparisons

**Verification**: 
```bash
npm test -- useAuth.test.ts
npm run test:mutation:batch-2:watch -- useAuth
```

---

## Task 2.3: useSelectedImage.test.ts (2.5 hours)

**Hook File**: `src/hooks/useSelectedImage.ts`

**Test Scenarios** (12+ tests):
- [ ] Load from localStorage on mount
- [ ] JSON validation with guard function
- [ ] Write with timestamp (selected_at)
- [ ] Clear clears state and storage
- [ ] Custom event dispatch (selectedImageChange)
- [ ] Storage event listener (cross-tab)
- [ ] Invalid data cleanup
- [ ] hasSelectedImage flag
- [ ] useSelectedImageListener variant
- [ ] getSelectedImageSync sync function

**Key Mocks**:
- `mockLocalStorage()` with controlled responses
- `window.addEventListener` spies
- `JSON.parse` error simulation

**Mutation Focus**:
- removeItem calls
- JSON.stringify presence
- Event detail assignments
- Guard function logic

**Verification**:
```bash
npm test -- useSelectedImage.test.ts
# Check both setSelectedImage and useSelectedImageListener
```

---

## Task 2.4: useJobStatus.test.ts (2.5 hours)

**Hook File**: `src/hooks/useJobStatus.ts`

**Test Scenarios** (12+ tests):
- [ ] Initial IDLE state with null jobId
- [ ] Reset to IDLE on jobId change to null
- [ ] Polling starts with jobId
- [ ] First check after 2000ms
- [ ] SUCCESS sets result and calls callback
- [ ] FAILURE sets error message
- [ ] Polling stops after final status
- [ ] clearInterval on unmount
- [ ] API error handling
- [ ] Dependency array: jobId changes
- [ ] Callback dependency handling

**Key Mocks**:
- `vi.useFakeTimers()` for polling intervals
- `mockFetchAPI()` with status responses
- Interval cleanup verification

**Mutation Focus**:
- Interval delay (2000 ms)
- Status comparisons (=== vs !==)
- clearInterval placement
- Callback invocation

**Verification**:
```bash
npm test -- useJobStatus.test.ts -- --clearCache
vi.runAllTimers() must clear polling
```

---

## Task 2.5: useMapReady.test.ts (2.5 hours)

**Hook File**: `src/hooks/useMapReady.ts`

**Test Scenarios** (10+ tests):
- [ ] invalidateSize called immediately
- [ ] Scheduled timeouts (0, 100, 300ms)
- [ ] RAF scheduling
- [ ] Window resize listener
- [ ] Visibility change listener
- [ ] ResizeObserver for container
- [ ] Cleanup: all timeouts cleared
- [ ] Cleanup: RAF cancelled
- [ ] Cleanup: listeners removed
- [ ] hasInitialized flag

**Key Mocks**:
- `mockLeafletMap()` with invalidateSize spy
- `vi.useFakeTimers()` for scheduling
- `requestAnimationFrame` mock
- `ResizeObserver` mock
- `window.addEventListener` spies

**Mutation Focus**:
- Timeout delays
- Cleanup function calls
- RAF cancellation
- Listener removal

**Verification**:
```bash
npm test -- useMapReady.test.ts
# Verify all 5 cleanup paths tested
```

---

## Task 2.6: useInfrastructure.test.ts (2 hours)

**Hook File**: `src/hooks/useInfrastructure.ts`

**Test Scenarios** (10+ tests):
- [ ] Load assets and intersections with Promise.all
- [ ] Loading state: false → true → false
- [ ] setAssets updates state
- [ ] setIntersections updates state
- [ ] createAsset POST request
- [ ] createAsset adds to array
- [ ] Error handling
- [ ] Refresh function
- [ ] Dependency array behavior

**Key Mocks**:
- `mockFetchAPI()` with dual endpoints:
  - `/infrastructure/assets`
  - `/infrastructure/potential-intersections`

**Mutation Focus**:
- Promise.all order
- Loading state placement
- Array mutations ([...prev] vs [])

**Verification**:
```bash
npm test -- useInfrastructure.test.ts
# Both endpoints must be called
```

---

## Task 2.7: useGEELayers.test.ts (2.5 hours)

**Hook File**: `src/hooks/useGEELayers.ts`

**Test Scenarios** (11+ tests):
- [ ] Load layers on mount
- [ ] layerNames option filters
- [ ] enabled=false skips loading
- [ ] reload function
- [ ] parseFeatureCollection validation
- [ ] Invalid layer returns null
- [ ] layersArray derived state
- [ ] Error when no layers load
- [ ] Dependency: layerNames
- [ ] Dependency: enabled
- [ ] Logger warn calls

**Key Mocks**:
- `mockFetchAPI()` with layer endpoints:
  - `/api/v1/gee/layers/{name}` for each layer
- `parseFeatureCollection` validation

**Mutation Focus**:
- Validation logic (!validatedData)
- Error message conditions
- Dependency array
- Partial load handling

**Verification**:
```bash
npm test -- useGEELayers.test.ts
# Test partial load (1/2 layers) shouldn't error
```

---

## Task 2.8: useImageComparison.test.ts (2.5 hours)

**Hook File**: `src/hooks/useImageComparison.ts`

**Test Scenarios** (12+ tests):
- [ ] Load from localStorage
- [ ] setLeftImage keeps right
- [ ] setRightImage keeps left
- [ ] setEnabled toggles
- [ ] clearComparison clears all
- [ ] Custom event dispatch
- [ ] Storage event listener
- [ ] isReady flag (both images set)
- [ ] useImageComparisonListener variant
- [ ] JSON error cleanup
- [ ] Custom event validation

**Key Mocks**:
- `mockLocalStorage()` 
- Event listener spies

**Mutation Focus**:
- Image state preservation (||)
- isReady logic (&&, not ||)
- Event dispatch detail

**Verification**:
```bash
npm test -- useImageComparison.test.ts
# setLeftImage must NOT clear right image
```

---

## Task 2.9: useContactVerification.test.ts (2.5 hours)

**Hook File**: `src/hooks/useContactVerification.ts`

**Test Scenarios** (12+ tests):
- [ ] contactoVerificado from authStore user
- [ ] loginWithGoogle OAuth flow
- [ ] loginWithGoogle error handling
- [ ] sendMagicLink email validation
- [ ] sendMagicLink invalid email
- [ ] sendMagicLink OTP call
- [ ] sendMagicLink success state
- [ ] logout signOut call
- [ ] resetVerificacion clears state
- [ ] onVerified callback
- [ ] metodoVerificacion switching

**Key Mocks**:
- `mockSupabaseClient()` with auth methods
- `mockAuthStore()` with user/profile
- `notifications.show()` spy (Mantine)
- `isValidEmail()` behavior

**Mutation Focus**:
- Email validation guard (!isValidEmail)
- Notification color values
- State assignments
- Callback conditions

**Verification**:
```bash
npm test -- useContactVerification.test.ts
# Email validation must prevent OTP send
```

---

## Task 2.10: useCaminosColoreados.test.ts (2 hours)

**Hook File**: `src/hooks/useCaminosColoreados.ts`

**Test Scenarios** (10+ tests):
- [ ] Load on mount
- [ ] Parse CaminosColoreados response
- [ ] Extract consorcios array
- [ ] Extract metadata
- [ ] Loading state transitions
- [ ] Error handling
- [ ] reload function
- [ ] FeatureCollection construction
- [ ] Dependency array
- [ ] Logger calls

**Key Mocks**:
- `mockFetchAPI()` for `/api/v1/gee/layers/caminos/coloreados`

**Mutation Focus**:
- Response structure parsing
- Metadata field access
- Error message conditions

**Verification**:
```bash
npm test -- useCaminosColoreados.test.ts
# Must extract consorcios and metadata properly
```

---

## Task 2.11: Run Stryker & Document (2.5 hours)

**Stryker Configuration**: Create `stryker-batch-2.config.json`

**Key Settings**:
- `testRunner`: vitest
- `testPathPattern`: `src/hooks/__tests__/.*\.test\.ts`
- `mutate`: All 9 hook files
- `thresholds.high`: 80
- `reporters`: ["html", "json", "progress"]

**Execution**:
```bash
npm run test:mutation:batch-2
# Should complete in <2 minutes
# HTML report: coverage/mutation-report/batch-2/index.html
```

**Documentation**: Update `MUTATION_TESTING.md`
- [ ] Add Batch 2 section header
- [ ] List all 9 hooks with mutation scores
- [ ] Total test count (≥70)
- [ ] Key patterns caught
- [ ] Execution time
- [ ] Links to HTML report

**Success Criteria**:
- ✅ All 9 hooks ≥80% mutation score
- ✅ 0 killed tests
- ✅ Execution time <2 min
- ✅ HTML report generated
- ✅ Documentation updated

---

## Testing Commands

```bash
# Run all Phase 2 tests
npm test src/hooks/__tests__

# Run specific hook test
npm test -- useAuth.test.ts

# Watch mode
npm test -- --watch

# Run Stryker (full batch)
npm run test:mutation:batch-2

# Run Stryker with watch (faster iteration)
npm run test:mutation:batch-2:watch

# View HTML report
open coverage/mutation-report/batch-2/index.html
```

---

## Common Issues & Solutions

### Issue: localStorage Mock Not Working
**Solution**: Set `Object.defineProperty(window, 'localStorage', {...})` in beforeEach

### Issue: Zustand Store Not Mocking
**Solution**: Mock the entire store module, not individual hooks
```typescript
vi.mock('../stores/authStore', () => ({
  useAuthStore: vi.fn((selector) => selector(mockStore()))
}));
```

### Issue: Timers Not Clearing
**Solution**: Always use `vi.useFakeTimers()` with `vi.runAllTimers()` in tests

### Issue: ResizeObserver Undefined
**Solution**: Mock at module level:
```typescript
global.ResizeObserver = vi.fn(() => ({
  observe: vi.fn(),
  disconnect: vi.fn(),
}));
```

### Issue: Custom Event Not Dispatching
**Solution**: Mock `window.dispatchEvent` and verify detail parameter

---

## Acceptance Criteria Checklist

- [ ] All 9 hook test files created
- [ ] 70+ total test cases across all files
- [ ] No test failures (all passing)
- [ ] Each hook ≥80% mutation score
- [ ] setup.ts with 6+ mock factories
- [ ] Stryker batch-2 config created
- [ ] HTML report generated
- [ ] MUTATION_TESTING.md Phase 2 section added
- [ ] No regressions on main tests

---

## Timeline Estimate

| Task | Effort | Dependencies |
|------|--------|--------------|
| 2.1 Setup | 2h | None |
| 2.2 useAuth | 3h | 2.1 |
| 2.3 useSelectedImage | 2.5h | 2.1 |
| 2.4 useJobStatus | 2.5h | 2.1 |
| 2.5 useMapReady | 2.5h | 2.1 |
| 2.6 useInfrastructure | 2h | 2.1 |
| 2.7 useGEELayers | 2.5h | 2.1 |
| 2.8 useImageComparison | 2.5h | 2.1 |
| 2.9 useContactVerification | 2.5h | 2.1 |
| 2.10 useCaminosColoreados | 2h | 2.1 |
| 2.11 Stryker & Docs | 2.5h | All above |
| **TOTAL** | **~23 hours** | Parallel after 2.1 |

---

## Next Steps After Phase 2

Once Phase 2 is complete:
1. ✅ Verify all 9 hooks ≥80% mutation score
2. ✅ Commit test files with message: "test(hooks): add mutation tests for 9 real hooks"
3. → Move to Phase 3 (Store & Components)
4. → Then Phase 4 (CI/CD Integration)

---

## Resources

- **Hook Implementation**: `/home/javier/consorcio-canalero/consorcio-web/src/hooks/`
- **Phase 2 Strategy**: `/home/javier/consorcio-canalero/openspec/changes/frontend-mutation-expansion/PHASE_2_REAL_HOOKS.md`
- **Full Tasks**: `/home/javier/consorcio-canalero/openspec/changes/frontend-mutation-expansion/tasks.md`
- **Stryker Docs**: https://stryker-mutator.io/

