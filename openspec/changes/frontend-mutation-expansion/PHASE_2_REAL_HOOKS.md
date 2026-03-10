# Phase 2: Real Hooks Testing Strategy

**Status**: ADAPTED FOR REAL CONSORCIO-WEB HOOKS  
**Date**: 2026-03-09  
**Scope**: 9 actual production hooks from consorcio-web  
**Total Test Cases Target**: 70+ tests across 9 hooks  
**Mutation Score Target**: ≥80% per hook file  

---

## Hook Testing Priority & Complexity

### Priority 1: Critical (Complex Zustand + Role Logic)
1. **useAuth.ts** (Complex: Zustand integration, role checking utilities)
   - Zustand store selector (useShallow optimization)
   - Role derivation and memoization
   - canAccess permission checking
   - Auto-initialization on mount

### Priority 2: High (Storage + State Validation)
2. **useSelectedImage.ts** (Medium: localStorage persistence, validation)
   - localStorage read/write with JSON validation
   - isValidSelectedImage guard function
   - Custom event dispatch for same-tab sync
   - Storage event listener for cross-tab sync
   - useSelectedImageListener variant

3. **useImageComparison.ts** (Medium: dual image state)
   - Similar pattern to useSelectedImage but with 2 images
   - setLeftImage / setRightImage state updates
   - isReady flag (both images set)

4. **useJobStatus.ts** (Medium: polling + async)
   - Polling interval (2 second checks)
   - Status transitions (PENDING → SUCCESS/FAILURE)
   - onCompleted callback handling
   - Cleanup on unmount (clearInterval)

### Priority 3: Medium (API + Async)
5. **useInfrastructure.ts** (Medium: Promise.all, API fetching)
   - Dual API endpoint fetch with Promise.all
   - Loading state transitions
   - createAsset POST action
   - Error handling

6. **useGEELayers.ts** (Complex: GEE integration, validation)
   - Multiple layer endpoints
   - parseFeatureCollection validation
   - Partial load handling
   - layersArray derived state

7. **useCaminosColoreados.ts** (Medium: domain-specific GEE)
   - CaminosColoreados response parsing
   - Consorcios array extraction
   - Metadata aggregation

### Priority 4: Medium (Lifecycle + External Libraries)
8. **useMapReady.ts** (Medium: Leaflet lifecycle)
   - invalidateSize scheduling (multiple timers)
   - ResizeObserver integration
   - window resize listener
   - document visibilitychange listener
   - requestAnimationFrame cleanup

9. **useContactVerification.ts** (Complex: OAuth + email OTP)
   - Supabase OAuth flow (signInWithOAuth)
   - Magic link OTP flow (signInWithOtp)
   - Email validation
   - Mantine notifications integration
   - authStore state derivation

---

## Setup.ts Requirements for Real Hooks

File: `src/hooks/__tests__/setup.ts`

```typescript
// Core utilities
export function renderHookWithProviders(hook, options?) { }
export function setupFakeTimers() { }

// LocalStorage mock
export function mockLocalStorage() {
  return {
    getItem: vi.fn(),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
    length: 0,
    key: vi.fn(),
  };
}

// Zustand authStore mock
export function mockAuthStore() {
  return {
    user: null,
    session: null,
    profile: null,
    loading: false,
    initialized: false,
    error: null,
    initialize: vi.fn(),
    reset: vi.fn(),
  };
}

// Supabase client mock (for useContactVerification)
export function mockSupabaseClient() {
  return {
    auth: {
      signInWithOAuth: vi.fn(),
      signInWithOtp: vi.fn(),
      signOut: vi.fn(),
    },
  };
}

// API fetch mock (for hooks using apiFetch)
export function mockFetchAPI(responses = {}) { }

// Leaflet map mock (for useMapReady)
export function mockLeafletMap() {
  return {
    invalidateSize: vi.fn(),
    getContainer: vi.fn(() => document.createElement('div')),
  };
}
```

---

## Test Scenarios by Hook

### 2.2: useAuth.test.ts (14+ tests, Zustand)

```
✓ Initialize on mount when autoInitialize=true
✓ Skip initialize if initialized=false initially
✓ Login action calls signInWithEmail
✓ Register action calls signUpWithEmail
✓ Logout action calls signOut
✓ hasRole(['admin']) returns true only if role='admin' and authenticated
✓ isAdmin memoized based on hasRole
✓ isOperador memoized based on hasRole
✓ isStaff returns true for admin OR operador
✓ isCiudadano returns true for ciudadano role
✓ canAccess returns true when user has one of allowedRoles
✓ canAccess returns false when allowedRoles empty (no restriction)
✓ isAuthenticated = !!user && !loading && initialized
✓ Error state propagates to hook return
✓ useShallow prevents unnecessary re-renders
```

**Key Mutations to Catch**:
- Role array includes → !includes
- Role === check → !== check
- && to || in isAuthenticated
- Removing initialized check

---

### 2.3: useSelectedImage.test.ts (12+ tests, Storage)

```
✓ Load from localStorage on mount with validation
✓ Invalid JSON in localStorage triggers removeItem
✓ setSelectedImage adds timestamp (selected_at)
✓ setSelectedImage persists to localStorage
✓ clearSelectedImage removes from storage
✓ dispatchEvent called with selectedImageChange
✓ Storage event listener syncs across tabs
✓ hasSelectedImage boolean flag
✓ useSelectedImageListener loads from storage
✓ getSelectedImageSync returns null for invalid data
✓ JSON.parse error triggers cleanup
✓ Custom event validation in listener
```

**Key Mutations to Catch**:
- removeItem calls (delete vs keep)
- JSON.stringify → null or empty string
- Event detail assignments
- Guard function negation

---

### 2.4: useJobStatus.test.ts (12+ tests, Polling)

```
✓ Initial state is IDLE when jobId=null
✓ Reset to IDLE when jobId becomes null
✓ Polling starts with jobId set
✓ First check happens after 2000ms
✓ SUCCESS status sets result and calls onCompleted
✓ FAILURE status sets error message
✓ Polling stops after SUCCESS
✓ Polling stops after FAILURE
✓ clearInterval called on unmount
✓ API error caught and sets error state
✓ Dependency array: jobId change triggers new polling
✓ Callback dependency: onCompleted change updates closure
```

**Key Mutations to Catch**:
- Polling interval (2000 → 1000 or 3000)
- Status comparisons (=== to !==)
- clearInterval missing
- onCompleted not called

---

### 2.5: useMapReady.test.ts (10+ tests, Lifecycle)

```
✓ invalidateSize called immediately
✓ Scheduled timeouts at 0, 100, 300ms
✓ RAF called for smooth invalidation
✓ Window resize listener attached
✓ Window resize listener triggers invalidateSize
✓ Visibility change listener attached
✓ Visibility 'visible' triggers invalidation
✓ ResizeObserver observes container
✓ All timeouts cleared on cleanup
✓ RAF cancelled on cleanup
✓ hasInitialized prevents double RAF
✓ All event listeners removed on cleanup
```

**Key Mutations to Catch**:
- Timeout delays (0 → 50, 100 → 200)
- Missing RAF cancellation
- Missing listener cleanup
- ResizeObserver.disconnect() missing

---

### 2.6: useInfrastructure.test.ts (10+ tests, Promise.all)

```
✓ Load assets and intersections with Promise.all
✓ Loading state: false → true → false
✓ setAssets updates state
✓ setIntersections updates state
✓ createAsset POST request
✓ createAsset adds to assets array
✓ Error handling sets error state
✓ Fetch error message propagated
✓ Refresh function re-runs fetchInfrastructure
✓ Dependency array: calls on mount
```

**Key Mutations to Catch**:
- Promise.all → Promise.race
- setLoading(false) placement (after vs before)
- Array spread [...prev, newAsset] vs [newAsset, ...prev]

---

### 2.7: useGEELayers.test.ts (11+ tests, GEE API)

```
✓ Load layers on mount
✓ layerNames option filters which layers load
✓ enabled=false skips loading
✓ reload function reloads all layers
✓ parseFeatureCollection validates GeoJSON
✓ Invalid layer returns null (partial load)
✓ layersArray derived from layers map
✓ Error set when no layers load successfully
✓ Dependency: layerNames change triggers reload
✓ Dependency: enabled change triggers reload
✓ Logger.warn called on failed layer
```

**Key Mutations to Catch**:
- Validation negation (!validatedData)
- Error message presence check (loadedCount === 0)
- Dependency array incomplete
- Logger function call missing

---

### 2.8: useImageComparison.test.ts (12+ tests, Dual State)

```
✓ Load from localStorage with validation
✓ setLeftImage updates left, keeps right
✓ setRightImage updates right, keeps left
✓ setEnabled toggles comparison.enabled
✓ clearComparison clears state and storage
✓ dispatchEvent with imageComparisonChange
✓ Storage event listener syncs across tabs
✓ isReady true only when both images set
✓ useImageComparisonListener reads from storage
✓ JSON.parse error triggers cleanup
✓ Custom event validation
✓ localStorage.setItem called with JSON
```

**Key Mutations to Catch**:
- setLeftImage with/without right preservation
- isReady logic (&&, both images must exist)
- Custom event vs storage event handling

---

### 2.9: useContactVerification.test.ts (12+ tests, OAuth + OTP)

```
✓ contactoVerificado derived from user state
✓ loginWithGoogle calls signInWithOAuth
✓ loginWithGoogle passes redirectTo
✓ loginWithGoogle error shows notification
✓ sendMagicLink validates email with isValidEmail
✓ sendMagicLink invalid email shows notification
✓ sendMagicLink calls signInWithOtp
✓ sendMagicLink success sets magicLinkSent
✓ sendMagicLink success shows notification
✓ logout calls signOut
✓ resetVerificacion clears state
✓ onVerified callback on verified
```

**Key Mutations to Catch**:
- Email validation negation (!isValidEmail)
- Notification color values
- State assignments (metodoVerificacion, magicLinkEmail)
- Callback invocation conditions

---

### 2.10: useCaminosColoreados.test.ts (10+ tests, Domain-Specific)

```
✓ Load caminos on mount
✓ Parse CaminosColoreados response
✓ Extract consorcios array
✓ Extract metadata object
✓ Loading state transitions
✓ Error handling on fetch failure
✓ reload function re-fetches
✓ FeatureCollection constructed from response
✓ Dependency array triggers reload
✓ Logger called on error
```

**Key Mutations to Catch**:
- Response structure parsing
- Metadata field extraction
- Error message content

---

## Mock Implementation Patterns

### Pattern 1: localStorage Mock

```typescript
beforeEach(() => {
  Object.defineProperty(window, 'localStorage', {
    value: mockLocalStorage(),
    writable: true,
  });
});
```

### Pattern 2: Zustand Store Mock

```typescript
vi.mock('../stores/authStore', () => ({
  useAuthStore: vi.fn((selector) => selector(mockAuthStore())),
}));
```

### Pattern 3: API Mock

```typescript
vi.mock('../lib/api', () => ({
  apiFetch: vi.fn(async (url) => {
    if (url.includes('/jobs/')) return { status: 'SUCCESS', result: {} };
    throw new Error('Not found');
  }),
}));
```

### Pattern 4: Leaflet Map Mock

```typescript
vi.mock('react-leaflet', () => ({
  useMap: () => mockLeafletMap(),
}));
```

---

## Stryker Configuration: Batch 2

File: `stryker-batch-2.config.json`

```json
{
  "testRunner": "vitest",
  "testPathPattern": "src/hooks/__tests__/.*\\.test\\.ts",
  "files": ["src/hooks/use*.ts"],
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
  "mutator": "typescript",
  "checkers": ["typescript"],
  "reporters": ["html", "json", "progress"],
  "reporterOptions": {
    "htmlReporter": {
      "baseDir": "coverage/mutation-report/batch-2"
    }
  },
  "thresholds": {
    "high": 80,
    "low": 75,
    "break": 70
  },
  "timeoutMS": 10000,
  "timeout": "30m"
}
```

---

## Real Hook Peculiarities & Mutation Detection

### 1. useAuth: useShallow Optimization
- **Risk**: Removing useShallow causes selector to re-run on every state change
- **Test**: Verify selector called only when specific fields change
- **Mutation**: `useShallow()` → `(state) => ({...})` (breaking memoization)

### 2. useSelectedImage: Timestamp Generation
- **Risk**: Forgetting to add `selected_at` timestamp
- **Test**: Verify timestamp is ISO string and current
- **Mutation**: Removing `selected_at` field from imageWithTimestamp

### 3. useJobStatus: Polling Termination
- **Risk**: Missing clearInterval prevents test cleanup
- **Test**: Verify interval cleared when status is final
- **Mutation**: Removing `else { clearInterval(interval) }`

### 4. useMapReady: Multiple Cleanup Points
- **Risk**: Forgetting to cancel RAF or remove one listener
- **Test**: Mock all 5 cleanup functions and verify each called
- **Mutation**: Removing any of the 5 cleanup steps

### 5. useInfrastructure: Promise.all Order
- **Risk**: Swapping order causes wrong endpoint assignment
- **Test**: Verify assets from /assets endpoint, intersections from /potential-intersections
- **Mutation**: Reversing [assetsData, intersectionsData] assignment

### 6. useGEELayers: Partial Load Success
- **Risk**: Treating partial load as error
- **Test**: When 1 of 2 layers loads, should not set error (only if 0/2)
- **Mutation**: Changing `loadedCount === 0` to `loadedCount < 1` (same but catches different mutation)

### 7. useImageComparison: Dual Image Preservation
- **Risk**: setLeftImage overwrites right image
- **Test**: Set left, verify right unchanged; set right, verify left unchanged
- **Mutation**: Using `prev?.right || image` should preserve, not default

### 8. useContactVerification: Email Validation Guard
- **Risk**: Skipping email validation
- **Test**: Invalid email should return early with notification
- **Mutation**: Removing `if (!isValidEmail(email))` guard

### 9. useCaminosColoreados: Response Structure
- **Risk**: Incorrectly extracting nested fields
- **Test**: Mock response with specific structure, verify extraction
- **Mutation**: Accessing wrong field names from response

---

## Success Criteria for Phase 2

- ✅ 9 hook test files created (one per hook)
- ✅ 70+ total test cases across all files
- ✅ Each hook achieves ≥80% mutation score
- ✅ No killed tests (all pass)
- ✅ Stryker execution completes in <2 minutes
- ✅ HTML report generated at `coverage/mutation-report/batch-2.html`
- ✅ All mocks properly isolated in setup.ts
- ✅ Real hook logic fully tested (no theoretical hooks)
- ✅ MUTATION_TESTING.md updated with Phase 2 results

