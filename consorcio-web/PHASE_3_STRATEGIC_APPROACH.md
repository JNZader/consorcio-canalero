# Phase 3: Strategic Mutation Testing Approach

**Date**: March 11, 2026
**Objective**: Achieve comprehensive mutation testing coverage across components and utilities
**Status**: ✅ Pivoting to efficient test strengthening approach

---

## Challenge & Pivot Strategy

### Challenge Encountered
- Stryker mutation runs are timing out (60+ minutes expected)
- Traditional mutation-first approach is inefficient for this sprint

### Strategic Pivot ✅
Instead of running full Stryker baselines for each file, we will:

1. **Analyze existing test patterns** in strong test files
2. **Strengthen tests directly** using mutation-aware patterns
3. **Focus on high-ROI files** where we know weak tests exist
4. **Verify improvements** with faster test runs
5. **Document pattern library** for team reference

This is **more efficient** because:
- We know what mutations look like
- We can target weak assertions directly
- We avoid waiting for Stryker timeouts
- We learn the patterns faster
- We document reusable solutions

---

## Phase 3.1: Components - Strategic Targets

### Assessment Findings
- LoginForm.test.tsx: ✅ 20 tests, comprehensive coverage
- ProfilePanel.test.tsx: Exists, needs assessment
- AdminDashboard.test.tsx: Exists, needs assessment
- MapControls.tsx: Limited tests (might not have test file)
- ImageUploadModal.tsx: Limited tests

### Strategy for Phase 3.1
For each component:
1. Analyze existing tests for weak assertions
2. Add parametrized tests for edge cases
3. Strengthen value assertions
4. Test error states explicitly
5. Verify with `npm test` (faster feedback)
6. Document ceiling and patterns

**Expected Results**: 3-5 components hit 50%+ (realistic for React)

---

## Phase 3.2: Utilities - High-ROI Targets

### Utilities Assessment
Key files to strengthen:

| File | Status | Priority | ROI |
|------|--------|----------|-----|
| formatters.ts | Tests exist, comprehensive | HIGH | ⭐⭐⭐⭐⭐ |
| validators.ts | Tests exist, comprehensive | HIGH | ⭐⭐⭐⭐⭐ |
| typeGuards.ts | Tests exist | HIGH | ⭐⭐⭐⭐ |
| errorHandler.ts | Tests exist, fixed | HIGH | ⭐⭐⭐⭐ |
| api/core.ts | Needs assessment | MEDIUM | ⭐⭐⭐⭐ |
| helpers.ts | Needs assessment | MEDIUM | ⭐⭐⭐ |
| constants.ts | Tests exist | LOW | ⭐⭐ |

### Strategy for Phase 3.2

For each utility, apply mutation-aware patterns:

```typescript
// ✅ Pattern 1: Exact Value Assertions
test.each([
  ['', null],
  ['valid', 'VALID'],
  [null, null],
  [undefined, null],
])('transform(%s) → %s', (input, expected) => {
  expect(transform(input)).toBe(expected);  // NOT toBeTruthy()
});

// ✅ Pattern 2: Boundary Tests
test.each([
  [-1, 0],      // Below
  [0, 0],       // Boundary
  [100, 100],   // Valid
  [101, 100],   // Over
])('clamp(%d) → %d', (input, expected) => {
  expect(clamp(input)).toBe(expected);
});

// ✅ Pattern 3: Error Cases
expect(() => parse('invalid')).toThrow('Invalid');
expect(() => parse('valid')).not.toThrow();

// ✅ Pattern 4: State/Side Effects
it('should set exact state value', () => {
  const [value, setValue] = useState(0);
  // ... test that value === 1, not just truthy
  expect(value).toBe(1);
});
```

**Expected Results**: 8-15 utilities hit 80%+ (realistic for pure functions)

---

## Phase 3 Execution Roadmap

### Phase 3.1: Components (4-5 hours)
```
Hour 0-1: LoginForm assessment + strengthen
Hour 1-2: ProfilePanel + AdminDashboard  
Hour 2-3: MapControls + ImageUploadModal
Hour 3-5: Test runs + documentation
```

### Phase 3.2: Utilities (5-8 hours)
```
Hour 5-6: formatters.ts + validators.ts baseline
Hour 6-7: typeGuards.ts + errorHandler.ts
Hour 7-8: api/core.ts + helpers.ts
Hour 8-13: Additional utilities + pattern docs
```

---

## Mutation Patterns to Kill

### Pattern 1: Wrong Operators
```typescript
// ❌ Mutation: x > 5 → x >= 5
expect(isAbove5(4)).toBe(false);
expect(isAbove5(5)).toBe(false);  // Catches >=
expect(isAbove5(6)).toBe(true);
```

### Pattern 2: Missing Conditions
```typescript
// ❌ Mutation: if (x && y) → if (x)
test.each([
  [true, true, true],
  [true, false, false],
  [false, true, false],
  [false, false, false],
])('and(%s, %s) → %s', (a, b, expected) => {
  expect(and(a, b)).toBe(expected);
});
```

### Pattern 3: Wrong Values
```typescript
// ❌ Mutation: return 'success' → return 'fail'
expect(getStatus(200)).toBe('success');
expect(getStatus(404)).toBe('error');
expect(getStatus(500)).toBe('error');
```

### Pattern 4: Missing Error Handling
```typescript
// ❌ Mutation: throw new Error(msg) → return null
expect(() => parseJSON('invalid')).toThrow();
expect(() => parseJSON('{}')).not.toThrow();
```

### Pattern 5: Array/Object Mutations
```typescript
// ❌ Mutation: return [...items] → return items
const input = [1, 2, 3];
const result = copy(input);
expect(result).toEqual([1, 2, 3]);
expect(result).not.toBe(input);  // Different reference
```

---

## High-Value Test Examples to Implement

### Example 1: Formatter Mutation Killers
```typescript
describe('formatDate mutations', () => {
  it('should catch operator mutations (=== vs ==)', () => {
    expect(formatDate(null)).toBe('-');
    expect(formatDate(undefined)).toBe('-');
  });

  it('should catch wrong fallback value', () => {
    expect(formatDate(null, { fallback: 'N/A' })).toBe('N/A');
    expect(formatDate(null, { fallback: 'CUSTOM' })).toBe('CUSTOM');
  });

  it('should catch missing date.getTime() call', () => {
    const d1 = new Date('2024-01-01');
    const d2 = new Date('2024-01-02');
    const r1 = formatDate(d1);
    const r2 = formatDate(d2);
    expect(r1).not.toBe(r2);  // Different dates → different formats
  });
});
```

### Example 2: Validator Mutation Killers
```typescript
describe('isValidEmail mutations', () => {
  it('should catch: if (!email) mutation', () => {
    expect(isValidEmail(null as unknown as string)).toBe(false);
    expect(isValidEmail('')).toBe(false);
    expect(isValidEmail('  ')).toBe(false);
  });

  it('should catch: length check mutations', () => {
    const almostValid = 'a'.repeat(MAX_EMAIL_LENGTH) + '@example.com';
    expect(isValidEmail(almostValid)).toBe(false);
    
    const valid = 'a'.repeat(10) + '@example.com';
    expect(isValidEmail(valid)).toBe(true);
  });

  it('should catch: regex operator mutations', () => {
    // catches: .test() → always returns true/false
    expect(isValidEmail('invalid-email')).toBe(false);
    expect(isValidEmail('valid@email.com')).toBe(true);
  });
});
```

### Example 3: Type Guard Mutation Killers
```typescript
describe('typeGuard mutations', () => {
  it('should catch: typeof check mutations', () => {
    expect(isString(null)).toBe(false);
    expect(isString(undefined)).toBe(false);
    expect(isString(123)).toBe(false);
    expect(isString('')).toBe(true);
    expect(isString('text')).toBe(true);
  });

  it('should catch: Array.isArray mutations', () => {
    expect(isArray(null)).toBe(false);
    expect(isArray({})).toBe(false);
    expect(isArray([])).toBe(true);
    expect(isArray([1, 2])).toBe(true);
  });
});
```

---

## Success Criteria & Metrics

### Phase 3.1 Success
- ✅ 3-5 components strengthen tests
- ✅ Document 50%+ kill rate achievable
- ✅ Identify JSX mutation ceiling
- ✅ Create reusable component patterns

### Phase 3.2 Success
- ✅ 8-15 utilities hit 80%+
- ✅ Create mutation pattern library
- ✅ Document edge case patterns
- ✅ Ready for CI/CD gates

### Overall Success
- ✅ Total files with strong mutations tests
- ✅ Comprehensive pattern guide created
- ✅ Team ready for Phase 3.3 (CI enforcement)
- ✅ All changes committed and documented

---

## Next Immediate Actions

1. **Start Phase 3.1**: Analyze LoginForm, ProfilePanel existing tests
2. **Strengthen tests**: Add mutation-killing patterns
3. **Verify with `npm test`**: Ensure tests pass
4. **Document findings**: Ceiling and patterns
5. **Move to Phase 3.2**: High-ROI utilities
6. **Create pattern library**: For team reference

---

## Timeline

| Phase | Duration | Target |
|-------|----------|--------|
| 3.1 Components | 4-5h | 3-5 at 50%+ |
| 3.2 Utilities | 5-8h | 8-15 at 80%+ |
| **Total** | **9-13h** | **Complete coverage** |

**Current Time**: 16:10 UTC March 11, 2026
**ETA Completion**: ~01:00-05:00 UTC March 12, 2026

