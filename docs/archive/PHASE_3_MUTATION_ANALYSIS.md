# Mutation Testing Strength Engineering - Phase 3 Analysis

**Date**: March 10, 2026  
**Status**: In Progress - Test Strengthening Required

## Current Situation

### Baseline Mutation Scores (Fresh Run)
| Hook | Tests | Kill Rate | Status | Gap |
|------|-------|-----------|--------|-----|
| useJobStatus | 43 | 73.7% | ✓ PASS | Exceeds 70% |
| useMapReady | 43 | 26.3% | ✗ FAIL | -43.7% |
| useSelectedImage | 47 | 45.6% | ✗ FAIL | -24.4% |
| **TOTAL** | **133** | **50.0%** | ✗ FAIL | -20% |

### Problem Identified
- All unit tests **PASS** (100%)
- Mutation kill rate is **ONLY 50%** overall
- This indicates **WEAK TEST ASSERTIONS** - tests exercise code but don't verify it properly
- 99 mutations escaped (survived) without being caught by tests

### Root Cause: Weak Assertions
Tests like:
```typescript
// ❌ WEAK - Only checks existence
expect(result).toBeDefined()
expect(result.status).toBeTruthy()

// ✅ STRONG - Checks exact value
expect(result).toBe('SPECIFIC_VALUE')
expect(result.status).toBe('SUCCESS')
```

## Mutation Escape Analysis

### useJobStatus (15 escaped)
- ConditionalExpression: 7 mutations (branch logic not verified)
- BooleanLiteral: 3 mutations (true/false not explicitly tested)
- StringLiteral: 3 mutations (exact string values not verified)
- LogicalOperator: 1 mutation (|| vs &&)
- BlockStatement: 1 mutation (empty catch block)

### useMapReady (28 escaped) - HIGHEST FAILURE
- BlockStatement: 7 mutations (empty blocks in handlers)
- ConditionalExpression: 6 mutations (branch logic)
- ArrowFunction: 5 mutations (callback return values)
- BooleanLiteral: 3 mutations (true/false literals)
- StringLiteral, Arrays, Equality: Others

### useSelectedImage (56 escaped) - HIGHEST COUNT
- BlockStatement: 18 mutations (empty blocks in try/catch)
- ConditionalExpression: 19 mutations (branch logic)
- StringLiteral: 8 mutations (exact string values)
- ArrayDeclaration: 5 mutations (array contents)
- ObjectLiteral: 2 mutations (object structures)

## Test Strengthening Strategy

### Pattern 1: Replace Weak Assertions with Strong Ones
**Before:**
```typescript
it('should handle storage change', () => {
  expect(result.current.selectedImage).toBeDefined();
  expect(dispatchSpy).toHaveBeenCalled();
});
```

**After:**
```typescript
it('should handle storage change', () => {
  expect(result.current.selectedImage).toEqual(expectedImage);
  expect(result.current.hasSelectedImage).toBe(true);
  expect(dispatchSpy).toHaveBeenCalledWith(expectedEvent);
  expect(dispatchSpy).toHaveBeenCalledTimes(1);
});
```

### Pattern 2: Test Both Branches Explicitly
**Before:**
```typescript
it('should validate data', () => {
  isValidMock.mockReturnValue(true);
  // ... only tests true case
});
```

**After:**
```typescript
describe.each([
  { valid: true, shouldSet: true },
  { valid: false, shouldSet: false }
])('data validation ($valid)', ({ valid, shouldSet }) => {
  it('should set state correctly', () => {
    isValidMock.mockReturnValue(valid);
    // ... verify behavior for BOTH cases
  });
});
```

### Pattern 3: Verify Empty Blocks
**Before:**
```typescript
} catch {
  // Empty catch - tests don't verify it's hit
}
```

**After:**
```typescript
} catch (error) {
  loggerMock.error('Failed', error);
  // Test EXPLICITLY:
  expect(loggerMock.error).toHaveBeenCalled();
}
```

### Pattern 4: Exact Value Comparisons
**Before:**
```typescript
expect(event.detail).toBeTruthy();
expect(status).not.toBeUndefined();
```

**After:**
```typescript
expect(event.detail).toEqual(expectedImage);
expect(status).toBe('PENDING');  // or 'SUCCESS' or 'FAILURE'
```

## Implementation Plan

### Phase 3.1: Priority Hooks (Start Now)
1. **useMapReady** - Lowest score (26.3%) - Most mutations escaped
2. **useSelectedImage** - Second lowest (45.6%) - Most escape count
3. **useJobStatus** - Already above 70% but can optimize

### Phase 3.2: Test Files to Modify
```
tests/hooks/useMapReady.test.ts      [PRIORITY 1]
tests/hooks/useSelectedImage.test.ts [PRIORITY 2]
tests/hooks/useJobStatus.test.ts     [PRIORITY 3]
```

### Phase 3.3: Execution Steps
For each hook:
1. Analyze escaped mutations in mutation.json
2. Identify weak assertions in test file
3. Apply strengthening patterns
4. Run mutation test: `npm run mutation:run`
5. Verify score improvement
6. Commit changes with mutation fix message
7. Repeat until ≥70% achieved

## Success Criteria
- ✅ useMapReady: 26.3% → ≥70% (+43.7 points needed)
- ✅ useSelectedImage: 45.6% → ≥70% (+24.4 points needed)
- ✅ useJobStatus: 73.7% → Further optimization (optional)
- ✅ All 9 hooks eventually reach ≥70% (future phase)

## Expected Effort
- useMapReady: 2-3 hours (28 escaped mutations to fix)
- useSelectedImage: 2-3 hours (56 escaped mutations to fix)
- useJobStatus: 1-2 hours (optimization only)
- **Total: 5-8 hours for Phase 3 completion**

## Key Insights
1. **Testing is not just about coverage** - 100% unit test pass rate with 50% mutation kill rate
2. **Mutations reveal weak assertions** - Tests run code but don't verify behavior properly
3. **Systematic strengthening works** - Applying patterns consistently will improve all hooks
4. **Parametrized tests are key** - Testing both branches catches most mutations

---
Next Step: Begin test strengthening on useMapReady.ts
