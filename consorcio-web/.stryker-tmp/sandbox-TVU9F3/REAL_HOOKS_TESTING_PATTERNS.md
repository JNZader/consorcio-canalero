# Real Hooks Testing Patterns Reference

**Quick lookup table for Phase 2 hook testing patterns**

---

## Hook Complexity & Effort Matrix

| Hook | Lines | Complexity | Dependencies | Setup Time | Test Time | Mutation Score Focus |
|------|-------|------------|--------------|-----------|-----------|----------------------|
| useAuth | 243 | ⭐⭐⭐ CRITICAL | Zustand, authLib | 1.5h | 3h | Role logic, memoization |
| useSelectedImage | 206 | ⭐⭐ MEDIUM | localStorage, typeGuards | 1h | 2.5h | Validation, storage sync |
| useJobStatus | 68 | ⭐⭐ MEDIUM | apiFetch, timers | 0.5h | 2.5h | Polling, clearInterval |
| useMapReady | 91 | ⭐⭐ MEDIUM | react-leaflet | 1h | 2.5h | Cleanup, scheduling |
| useInfrastructure | 57 | ⭐⭐ MEDIUM | apiFetch, Promise.all | 0.5h | 2h | Dual endpoint, POST |
| useGEELayers | 166 | ⭐⭐⭐ COMPLEX | API, validation, fetch | 1h | 2.5h | Validation, partial load |
| useImageComparison | 168 | ⭐⭐ MEDIUM | localStorage, state | 1h | 2.5h | State preservation, flags |
| useContactVerification | 206 | ⭐⭐⭐ COMPLEX | Supabase, notifications, validation | 1.5h | 2.5h | OAuth, OTP, callbacks |
| useCaminosColoreados | 116 | ⭐⭐ MEDIUM | API, parsing | 0.5h | 2h | Response parsing, metadata |

**Total Setup**: ~9 hours | **Total Testing**: ~21 hours | **Total Effort**: ~23 hours

---

## Mock Implementation Complexity

| Mock | Required For | Difficulty | Key Functions |
|------|--------------|-----------|----------------|
| `mockLocalStorage()` | useSelectedImage, useImageComparison | ⭐ EASY | getItem, setItem, removeItem, clear |
| `mockAuthStore()` | useAuth, useContactVerification | ⭐⭐ MEDIUM | User, profile, role, loading, initialized, initialize, reset |
| `mockFetchAPI()` | useJobStatus, useInfrastructure, useGEELayers, useCaminosColoreados | ⭐⭐ MEDIUM | Parametrized responses per endpoint |
| `mockSupabaseClient()` | useContactVerification | ⭐⭐ MEDIUM | auth.signInWithOAuth, auth.signInWithOtp, auth.signOut |
| `mockLeafletMap()` | useMapReady | ⭐ EASY | invalidateSize, getContainer |
| Vitest FakeTimers | useJobStatus, useMapReady | ⭐⭐ MEDIUM | vi.useFakeTimers(), vi.runAllTimers(), setTimeout, setInterval |
| EventListener Spies | useSelectedImage, useImageComparison, useMapReady | ⭐⭐ MEDIUM | window.addEventListener, dispatchEvent, StorageEvent |
| ResizeObserver | useMapReady | ⭐ EASY | vi.fn(() => ({observe, disconnect})) |

---

## Test Scenario Categories

### 1. Initialization & Mounting
**Hooks Using**: useAuth, useSelectedImage, useJobStatus, useGEELayers, useCaminosColoreados

```typescript
describe('Initialization', () => {
  it('loads state from storage on mount', () => {
    renderHook(() => useSelectedImage());
    expect(localStorage.getItem).toHaveBeenCalled();
  });

  it('auto-initializes store on mount when enabled', () => {
    renderHook(() => useAuth({ autoInitialize: true }));
    expect(mockAuthStore.initialize).toHaveBeenCalled();
  });
});
```

**Mutation Detection**: 
- Removing initialization calls
- Skipping effect dependencies
- Removing condition checks

---

### 2. State Management & Updates
**Hooks Using**: useAuth, useSelectedImage, useImageComparison, useContactVerification, useJobStatus

```typescript
describe('State Updates', () => {
  it('updates state when action called', () => {
    const { result } = renderHook(() => useSelectedImage());
    act(() => {
      result.current.setSelectedImage(mockImage);
    });
    expect(result.current.selectedImage).toBe(mockImage);
  });
});
```

**Mutation Detection**:
- Assignment operators (= to nothing)
- State update timing
- Callback invocation

---

### 3. Async Operations & Polling
**Hooks Using**: useJobStatus, useInfrastructure, useGEELayers, useCaminosColoreados

```typescript
describe('Async Operations', () => {
  it('polls status with correct interval', () => {
    const { unmount } = renderHook(
      () => useJobStatus('job123'),
      { wrapper: ({ children }) => <Provider>{children}</Provider> }
    );
    
    vi.advanceTimersByTime(2000);
    expect(mockFetchAPI).toHaveBeenCalledWith('/jobs/job123');
    
    unmount();
    expect(mockClearInterval).toHaveBeenCalled();
  });
});
```

**Mutation Detection**:
- Interval delays (2000 → 1000 or 3000)
- Missing polling stops
- clearInterval not called
- Dependency array changes

---

### 4. Storage & Persistence
**Hooks Using**: useSelectedImage, useImageComparison

```typescript
describe('Storage Persistence', () => {
  it('persists to localStorage after update', () => {
    const { result } = renderHook(() => useSelectedImage());
    act(() => {
      result.current.setSelectedImage(mockImage);
    });
    expect(localStorage.setItem).toHaveBeenCalledWith(
      'consorcio_selected_image',
      JSON.stringify(expect.objectContaining({ ...mockImage }))
    );
  });

  it('syncs from other tabs via storage event', () => {
    const { result } = renderHook(() => useSelectedImage());
    
    act(() => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: 'consorcio_selected_image',
        newValue: JSON.stringify(mockImage),
      }));
    });
    
    expect(result.current.selectedImage).toEqual(mockImage);
  });
});
```

**Mutation Detection**:
- Missing setItem/removeItem calls
- Incorrect storage key
- Missing event listeners
- Validation bypass

---

### 5. Validation & Guards
**Hooks Using**: useSelectedImage, useImageComparison, useGEELayers, useContactVerification

```typescript
describe('Validation', () => {
  it('rejects invalid data on load', () => {
    localStorage.getItem.mockReturnValue(JSON.stringify({ invalid: true }));
    
    renderHook(() => useSelectedImage());
    
    expect(localStorage.removeItem).toHaveBeenCalled();
  });

  it('prevents magic link send with invalid email', async () => {
    const { result } = renderHook(() => useContactVerification());
    
    await act(async () => {
      await result.current.sendMagicLink('not-an-email');
    });
    
    expect(mockSupabaseClient.auth.signInWithOtp).not.toHaveBeenCalled();
  });
});
```

**Mutation Detection**:
- Guard function negation (!validator)
- Missing validation calls
- Early returns not executed
- Guard condition flip

---

### 6. Derived State & Memoization
**Hooks Using**: useAuth, useImageComparison

```typescript
describe('Derived State', () => {
  it('computes isAuthenticated from user, loading, initialized', () => {
    const { result } = renderHook(() => useAuth());
    
    expect(result.current.isAuthenticated).toBe(false); // user=null
    
    // Update store to have user but still loading
    mockAuthStore.user = mockUser;
    mockAuthStore.loading = true;
    
    // isAuthenticated should still be false
    expect(result.current.isAuthenticated).toBe(false);
  });

  it('memoizes role checks to prevent unnecessary re-renders', () => {
    const { result, rerender } = renderHook(() => useAuth());
    const firstIsAdmin = result.current.isAdmin;
    
    rerender();
    
    expect(result.current.isAdmin).toBe(firstIsAdmin); // Reference equal
  });
});
```

**Mutation Detection**:
- Missing && conditions
- Conditional order change
- Missing memoization (useCallback, useMemo)

---

### 7. Lifecycle & Cleanup
**Hooks Using**: useMapReady, useJobStatus, useSelectedImage

```typescript
describe('Lifecycle & Cleanup', () => {
  it('clears intervals on unmount', () => {
    const { unmount } = renderHook(() => useJobStatus('job123'));
    
    unmount();
    
    expect(mockClearInterval).toHaveBeenCalled();
  });

  it('removes event listeners on unmount', () => {
    const removeEventListenerSpy = vi.spyOn(window, 'removeEventListener');
    const { unmount } = renderHook(() => useSelectedImage());
    
    unmount();
    
    expect(removeEventListenerSpy).toHaveBeenCalledWith('storage', expect.any(Function));
  });
});
```

**Mutation Detection**:
- Missing cleanup functions
- Cleanup function call removed
- Missing return in useEffect
- Listener not removed

---

### 8. Error Handling
**Hooks Using**: useInfrastructure, useGEELayers, useContactVerification, useJobStatus

```typescript
describe('Error Handling', () => {
  it('catches API errors and sets error state', async () => {
    mockFetchAPI.mockRejectedValue(new Error('Network error'));
    
    const { result } = renderHook(() => useInfrastructure());
    
    await waitFor(() => {
      expect(result.current.error).toBe('Error cargando infraestructura');
    });
  });

  it('handles partial load gracefully', () => {
    mockFetchAPI
      .mockResolvedValueOnce({ type: 'FeatureCollection', features: [] }) // zona OK
      .mockRejectedValueOnce(new Error('Not found')); // candil failed
    
    const { result } = renderHook(() => useGEELayers({ 
      layerNames: ['zona', 'candil'] 
    }));
    
    // Should have zona, not error (partial load OK)
    expect(result.current.layers.zona).toBeDefined();
    expect(result.current.error).toBeNull();
  });
});
```

**Mutation Detection**:
- Missing error assignment
- Error swallowed (catch not executed)
- Wrong error message
- Partial success treated as failure

---

### 9. Dependency Array Correctness
**Hooks Using**: useAuth, useJobStatus, useGEELayers, useInfrastructure

```typescript
describe('Dependency Array', () => {
  it('refetches when jobId changes', async () => {
    const { rerender } = renderHook(
      ({ jobId }) => useJobStatus(jobId),
      { initialProps: { jobId: 'job1' } }
    );
    
    expect(mockFetchAPI).toHaveBeenCalledTimes(1);
    
    rerender({ jobId: 'job2' });
    
    expect(mockFetchAPI).toHaveBeenCalledTimes(2);
    expect(mockFetchAPI).toHaveBeenLastCalledWith('/jobs/job2');
  });

  it('does not refetch if dependency not in array', () => {
    const callback = vi.fn();
    const { rerender } = renderHook(
      ({ cb }) => useJobStatus('job1', cb),
      { initialProps: { cb: callback } }
    );
    
    const initialCallCount = mockFetchAPI.mock.calls.length;
    
    rerender({ cb: vi.fn() }); // New callback reference
    
    // Should not refetch (callback not in deps)
    expect(mockFetchAPI.mock.calls.length).toBe(initialCallCount);
  });
});
```

**Mutation Detection**:
- Missing dependency
- Extra dependency causing unnecessary re-runs
- Empty dependency array (should have deps)

---

## Parametrized Test Examples

### Pattern 1: Status Transitions
```typescript
describe('Status Transitions', () => {
  const cases = [
    { status: 'PENDING', expected: true },
    { status: 'STARTED', expected: true },
    { status: 'SUCCESS', expected: false },
    { status: 'FAILURE', expected: false },
  ];

  test.each(cases)(
    'keeps polling while status=$status is active (expected=$expected)',
    ({ status, expected }) => {
      mockFetchAPI.mockResolvedValue({ status, result: null });
      // ... test implementation
    }
  );
});
```

### Pattern 2: Email Validation
```typescript
describe('Email Validation', () => {
  const cases = [
    { email: 'user@example.com', valid: true },
    { email: 'invalid@', valid: false },
    { email: '', valid: false },
    { email: 'user+tag@example.com', valid: true },
  ];

  test.each(cases)(
    'validates email=$email -> $valid',
    async ({ email, valid }) => {
      const { result } = renderHook(() => useContactVerification());
      await act(async () => {
        if (valid) {
          await result.current.sendMagicLink(email);
          expect(mockSupabaseClient.auth.signInWithOtp).toHaveBeenCalled();
        } else {
          await result.current.sendMagicLink(email);
          expect(mockSupabaseClient.auth.signInWithOtp).not.toHaveBeenCalled();
        }
      });
    }
  );
});
```

---

## Stryker Mutation Test Cases

### Critical Mutations to Catch

| Mutation Type | Hook | Example | Detection |
|---------------|------|---------|-----------|
| Operator Flip | useInfrastructure | `Promise.all` → `Promise.race` | Wrong endpoint resolved |
| Conditional Negate | useAuth | `isAuthenticated = !!user` → `!user` | Should be authenticated |
| Guard Removal | useContactVerification | Remove `if (!isValidEmail())` guard | Invalid email accepted |
| Interval Timing | useJobStatus | 2000 → 1000 | Status checks too frequent |
| Array Mutation | useImageComparison | `[...prev, new]` → `[new]` | Lost previous image |
| Storage Key | useSelectedImage | `'consorcio_selected_image'` → `'image'` | Wrong key accessed |
| Comparison Op | useMapReady | `hasInitialized = true` → `false` | Double initialization |
| Return Value | useGEELayers | `return [name, null]` → `return null` | Breaks array destructuring |
| Null Check | useInfrastructure | `intersections || null` → `null` | Always null |
| Event Detail | useSelectedImage | `{ detail: image }` → `{ detail: null }` | Listener sees null |

---

## Performance Targets

| Hook | Test Count | Execution Time | Coverage |
|------|-----------|-----------------|----------|
| useAuth | 14 | 200ms | 95%+ |
| useSelectedImage | 12 | 150ms | 90%+ |
| useJobStatus | 12 | 180ms | 85%+ |
| useMapReady | 10 | 200ms | 90%+ |
| useInfrastructure | 10 | 150ms | 85%+ |
| useGEELayers | 11 | 180ms | 85%+ |
| useImageComparison | 12 | 150ms | 90%+ |
| useContactVerification | 12 | 200ms | 85%+ |
| useCaminosColoreados | 10 | 150ms | 85%+ |
| **TOTAL** | **103** | **~1500ms** | **~88%** |

**Stryker Batch 2 Execution**: <2 minutes for full mutation test

---

## Common Test Patterns Checklist

When writing Phase 2 tests, ensure you cover:

- [ ] Initialization/mounting behavior
- [ ] State updates with act()
- [ ] Async operations with proper waiting
- [ ] Storage read/write operations
- [ ] Event listener attachment/removal
- [ ] Cleanup functions (useEffect return)
- [ ] Error handling and fallbacks
- [ ] Memoization and reference equality
- [ ] Dependency array correctness
- [ ] Parametrized test cases for boundaries
- [ ] Integration with external mocks (Zustand, Supabase, apiFetch)
- [ ] Custom event dispatch/listening
- [ ] Validation guard functions

