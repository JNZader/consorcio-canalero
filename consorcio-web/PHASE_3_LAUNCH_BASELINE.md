# Phase 3.1 Mutation Testing - Components Baseline Report

**Date**: March 11, 2026  
**Phase**: 3.1 (Components)  
**Status**: ✅ Baseline Complete

---

## Executive Summary

Successfully established mutation testing baselines for the first 3 priority components. 

**Key Findings**:
- ✅ **ThemeToggle.tsx**: 65.22% kill rate (close to 70% threshold)
- ❌ **ErrorBoundary.tsx**: 26.92% kill rate (needs significant strengthening)
- ⚠️ **Header.tsx**: Unable to establish baseline due to dynamic imports (will address separately)

---

## Component Baseline Results

### 1. ErrorBoundary.tsx

**Baseline Kill Rate**: 26.92% (21/78 mutations killed)

**Status**: ❌ BELOW 70% THRESHOLD

**Metrics**:
- Total Mutations: 78
- Killed: 21
- Survived: 57
- No Coverage: 0
- Errors: 0

**Key Escaped Mutations** (High Priority to Fix):
1. **Object/Array Literals**: Many mutations to style objects and empty objects survive
   - `{{ maxHeight: 200, overflow: 'auto' }}` → `{}` ❌
   - `{ hasError: false, error: null, errorInfo: null }` → `{}` ❌

2. **Conditional Branches**: Error handling conditions not fully tested
   - `if (import.meta.env.DEV) { ... }` mutations survive
   - Error state checks not triggered

3. **String/Property Mutations**: Text and attribute changes survive
   - Button labels can change without test failure
   - className mutations survive

4. **Method Calls**: Handler function calls not verified
   - `handleReset` click handler not properly asserted
   - `location.reload()` call not verified in context

**Next Steps**:
1. Strengthen assertions on error rendering
2. Add more specific tests for error UI elements
3. Test error state transitions more thoroughly
4. Add tests for edge cases (null children, missing props)
5. Add more specific assertions for callbacks

---

### 2. ThemeToggle.tsx

**Baseline Kill Rate**: 65.22% (15/23 mutations killed)

**Status**: ⚠️ BELOW 70% THRESHOLD (Close!)

**Metrics**:
- Total Mutations: 23
- Killed: 15
- Survived: 8
- No Coverage: 0
- Errors: 0

**Key Escaped Mutations** (Medium Priority to Fix):
1. **Conditional Logic**: `if (!mounted)` mutations survive
   - Loading state return not properly tested

2. **String Literals**: Tooltip/aria-label text changes survive
   - `'Modo claro'` can change without test failure
   - `'Modo oscuro'` changes not detected

3. **Style Objects**: Empty style objects survive mutations
   - `{ width: 18, height: 18 }` → `{}` ❌

4. **Ternary Operations**: Some branches not fully exercised
   - `isDark ? ... : ...` variations

**Next Steps**:
1. Add assertions for tooltip text content
2. Verify mounted state loading behavior
3. Test theme button dimensions/styling
4. Add more specific aria-label assertions
5. Test all ternary branches explicitly

**Confidence**: High - only needs 5.78% improvement to reach 70%!

---

### 3. Header.tsx

**Status**: ⚠️ UNABLE TO ESTABLISH BASELINE

**Issue**: Dynamic imports with `lazy(() => import())` cause mutation analysis to break.

**Error**: Stryker mutations turn import statements into invalid code:
```typescript
// Original:
const UserMenu = lazy(() => import('./UserMenu'));

// After mutation:
const UserMenu = lazy(() => import(""));  // ❌ Invalid!
```

**Solution Approach**:
- Option 1: Exclude dynamic imports from mutation analysis
- Option 2: Refactor to remove lazy loading (not recommended - breaks perf)
- Option 3: Use custom Stryker configuration to ignore lazy import paths
- Option 4: Focus on testing Header logic that doesn't involve lazy loading

**Recommendation**: Use Option 1 - create focused baseline without testing the lazy loading mechanism itself.

---

## Test Coverage Quality Assessment

### ErrorBoundary.test.tsx (26 tests)
- **Strength**: Good organization by category (rendering, error handling, recovery, etc.)
- **Weakness**: Assertions too generic (using `toBeDefined()`, `toBeInTheDocument()`)
- **Issue**: Tests don't verify specific behavior, just presence

### ThemeToggle.test.tsx (19 tests)
- **Strength**: Tests both light and dark modes
- **Strength**: Tests keyboard accessibility
- **Weakness**: Missing assertions for exact aria-label values
- **Weakness**: Tooltip content not asserted

### Header.test.tsx (21 tests)
- **Strength**: Comprehensive navigation link testing
- **Strength**: Tests mobile and desktop variants
- **Weakness**: Many assertions are presence checks, not behavior
- **Weakness**: Event listeners not fully tested

---

## Phase 3.1 Execution Plan

### Priority Order

1. **ThemeToggle.tsx** (FIRST)
   - Closest to 70% threshold
   - Simpler component
   - Can achieve ≥70% with 5-8 test improvements
   - **Est. Effort**: 1-2 hours

2. **ErrorBoundary.tsx** (SECOND)
   - More complex but isolated
   - Needs significant test strengthening
   - Good learning opportunity for error testing
   - **Est. Effort**: 2-3 hours

3. **Header.tsx** (THIRD)
   - Must resolve Stryker dynamic import issue first
   - More complex interactions
   - May need refactoring for testability
   - **Est. Effort**: 2-4 hours

---

## Key Patterns to Fix (from Phase 2)

### Weak Assertion Patterns

```typescript
// ❌ Weak - only checks existence
expect(screen.getByText('text')).toBeInTheDocument();
expect(button).toBeDefined();

// ✅ Strong - checks specific behavior
expect(screen.getByText('exact text')).toHaveClass('active');
expect(onClick).toHaveBeenCalledWith(expectedArg);
expect(localStorage.getItem('key')).toBe('expectedValue');
```

### Missing Edge Cases

```typescript
// ❌ Weak - only happy path
test('renders button', () => {
  render(<ThemeToggle />);
  expect(screen.getByRole('button')).toBeInTheDocument();
});

// ✅ Strong - tests all states
test.each([
  { isDark: true, expectedLabel: 'Cambiar a modo claro' },
  { isDark: false, expectedLabel: 'Cambiar a modo oscuro' },
])('displays correct label for $isDark', ({ isDark, expectedLabel }) => {
  mockHook.mockReturnValue({ colorScheme: isDark ? 'dark' : 'light' });
  render(<ThemeToggle />);
  expect(screen.getByRole('button')).toHaveAttribute('aria-label', expectedLabel);
});
```

---

## Next Steps

1. ✅ **Baselines Established** (this document)
2. 📋 **Strengthen Tests** (starting with ThemeToggle)
3. 🔄 **Re-run Stryker** after each round
4. 📊 **Track Progress** with incremental improvements
5. ✅ **Achieve ≥70%** for each component
6. 📝 **Commit** with message: `test: component mutation testing for <ComponentName>`

---

## Mutation Testing Thresholds

- **High**: 85%+ (excellent - focus on edge cases)
- **Medium**: 70-85% (good - target for Phase 3)
- **Low**: <70% (needs work - current state)

---

## Estimated Timeline

- **ThemeToggle**: 30-60 minutes
- **ErrorBoundary**: 60-120 minutes  
- **Header**: 90-180 minutes

**Total Phase 3.1 (3 components)**: 3-6 hours

---

## Related Documents

- `PHASE_3_PLAN.md` - Overall Phase 3 roadmap
- `PHASE_2_FINAL_REPORT.md` - Hook mutation testing patterns
- `MUTATION_TESTING.md` - Complete mutation testing guide

---

**Report Generated**: March 11, 2026 @ 13:21 UTC

