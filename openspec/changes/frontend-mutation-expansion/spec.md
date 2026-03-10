# Delta Specification: Frontend Mutation Testing Expansion

## Purpose

Systematically expand mutation testing coverage across the frontend codebase to achieve ≥80% mutation score per file, organized by complexity batch (utilities → hooks → store/components).

## Target Files by Complexity

### Category: Low Complexity (Utilities & Helpers)

**Count**: 5 files | **Est. Escape Scenarios**: 8-12 per file | **Target Tests**: 15 total

1. `src/lib/utils/formatters.ts` — String formatting (toUpperCase, toLowerCase, date formatting)
2. `src/lib/utils/validators.ts` — Input validation (email, phone, URL regex patterns)
3. `src/lib/utils/calculations.ts` — Math operations (sum, average, percentage, rounding)
4. `src/lib/utils/constants.ts` — Constant definitions and enums
5. `src/lib/utils/object-helpers.ts` — Object manipulation (merge, clone, pick, omit)

### Category: Medium Complexity (Hooks & State Logic)

**Count**: 8 files | **Est. Escape Scenarios**: 15-20 per file | **Target Tests**: 25 total

1. `src/hooks/useForm.ts` — Form state, validation logic, error handling
2. `src/hooks/useAuth.ts` — Authentication state, login/logout flows
3. `src/hooks/useAsync.ts` — Async operations, loading/error states
4. `src/hooks/useLocalStorage.ts` — Storage persistence, sync/async branches
5. `src/hooks/useDebounce.ts` — Debounce timer logic, cleanup
6. `src/hooks/useTheme.ts` — Theme switching, persisted state
7. `src/hooks/useModal.ts` — Modal open/close state, keyboard handling
8. `src/hooks/usePagination.ts` — Offset/limit calculations, boundary conditions

### Category: High Complexity (Store, Components, Integration)

**Count**: 7+ files | **Est. Escape Scenarios**: 25-35+ per file | **Target Tests**: 30+ total

1. `src/store/authStore.ts` — State management, reducers, side effects
2. `src/store/appStore.ts` — Global app state, middleware
3. `src/components/Form/index.tsx` — Form rendering, field arrays, conditional sections
4. `src/components/DataTable/index.tsx` — Sorting, filtering, pagination integration
5. `src/components/Modal/index.tsx` — Portal rendering, event handling, animations
6. `src/components/Layout/index.tsx` — Conditional rendering, responsive behavior
7. `src/pages/Dashboard/index.tsx` — Data fetching, error states, empty states

## Mutation Escape Scenarios by Category

### Low Complexity Escapes

**Formatters**:
- Boundary mutations (trim vs. no trim, case handling)
- Conditional operator flips (&&, ||, !, ===)
- Increment/decrement mutations (+1 → -1)
- Return value mutations (empty string vs. null)

**Validators**:
- Regex boundary conditions (include/exclude edge cases)
- Conditional negation (!match → match)
- Length checks off-by-one
- Type coercion mutations

**Calculations**:
- Arithmetic operator mutations (+/-, */÷, %/)
- Rounding direction (Math.floor → Math.ceil)
- Zero handling and division by zero
- Initialization value mutations

### Medium Complexity Escapes

**Hooks (useForm, useAuth, useAsync)**:
- Conditional branches not fully executed
- Effect cleanup missing or incomplete
- Dependency array mutations (missing/extra deps)
- Error handler invocation mutations
- State setter call skipping
- Async callback ordering

**State Persistence (useLocalStorage, useTheme)**:
- JSON.parse/stringify edge cases
- Storage key mutations
- Fallback value mutations
- Sync vs. async timing

**Timers (useDebounce)**:
- Timeout duration mutations
- clearTimeout call skipping
- Pending state tracking

### High Complexity Escapes

**Store (Reducers, Selectors)**:
- Action type mutations
- State immutability violations
- Selector computation mutations
- Middleware dispatch call skipping

**Components (Conditional Rendering)**:
- Boundary condition mutations in lists (.length, .length > 0)
- Boolean operator flips in render conditions
- Default prop mutations
- Event handler invocation mutations
- CSS class name mutations affecting behavior

**Data Table**:
- Sort direction mutations (asc/desc)
- Pagination offset calculations
- Filter predicate mutations
- Empty state condition mutations

## Testing Patterns & Best Practices

### Parametrization Strategy

```typescript
// Pattern 1: Boundary value parametrization
describe.each([
  { input: 0, expected: "zero" },
  { input: 1, expected: "one" },
  { input: -1, expected: "minus one" },
  { input: 999999, expected: "999999" },
])('formatNumber($input)', ({ input, expected }) => {
  expect(formatNumber(input)).toBe(expected);
});
```

### Mocking Strategy

**Utilities**: Minimal mocking, focus on pure function inputs/outputs

**Hooks**: Mock external APIs, timers, and browser APIs
- `vi.useFakeTimers()` for timeout/interval logic
- `localStorage` mocks for persistence hooks
- `fetch` mocks for async hooks

**Store/Components**: Mock child components, external services, API calls
- `vi.mock('../child-component')`
- Mock provider contexts
- MSW (Mock Service Worker) for API endpoints

### Edge Case Coverage

**For each file, test**:
1. **Happy path**: Normal, expected input/output
2. **Boundary conditions**: Minimum, maximum, zero, empty values
3. **Error states**: Invalid input, failed API calls, network errors
4. **Async timing**: Race conditions, cancellation, cleanup
5. **State transitions**: Before/after state mutations
6. **User interactions**: Click, type, submit, keyboard events

## Success Metrics

### Per-File Metrics

| Metric | Target | Validation |
|--------|--------|-----------|
| Mutation Score | ≥80% | Stryker report per file |
| Test Coverage | ≥85% | Istanbul/c8 report |
| Test Count | See batch targets | Task checklist |

### Batch Completion Criteria

- **Phase 1 (Utilities)**: All 5 files ≥80% mutation score before Phase 2 starts
- **Phase 2 (Hooks)**: All 8 files ≥80% mutation score before Phase 3 starts
- **Phase 3 (Store/Components)**: All 7+ files ≥80% mutation score before Phase 4

### CI/CD Thresholds

| Type | Threshold | Action |
|------|-----------|--------|
| Mutation Score Drop | >5% regression | Fail build |
| Coverage Drop | >3% regression | Fail build |
| Test Execution | >2 min per batch | Warn in PR |
| New Files | Must have ≥80% before merge | Enforce check |

## CI/CD Specification

### When to Run

**Trigger**: On every PR and merge to `main`
**Branches**: Feature branches, `develop`, `main`

### Execution Plan

**Phase 1 Batch** (Utilities): Run in <45s
- Command: `stryker run --testNamePattern="(formatters|validators|calculations|constants|object-helpers)"`

**Phase 2 Batch** (Hooks): Run in <1m 15s
- Command: `stryker run --testNamePattern="(useForm|useAuth|useAsync|useLocalStorage|useDebounce|useTheme|useModal|usePagination)"`

**Phase 3 Batch** (Store/Components): Run in <2m
- Command: `stryker run --testNamePattern="(auth-store|app-store|Form|DataTable|Modal|Layout|Dashboard)"`

**Full Suite**: Run post-merge, nightly
- Command: `stryker run` (all files)

### Reporting

**Metrics Collected**:
- Mutation score per file
- Test count per module
- Execution time per batch
- Survived vs. killed mutations (with escape scenarios)

**Dashboard**: Generate summary HTML report in `coverage/mutation-report/` for PR review

**Rollback Condition**: If mutation score drops >5% from baseline, revert PR or fail merge

## Requirements & Scenarios

### Requirement: Systematic Mutation Score Improvement

The test suite MUST achieve ≥80% mutation score for all 20+ target files, organized in three implementation batches (low → medium → high complexity).

#### Scenario: Batch 1 Utilities Completion

- GIVEN 5 utility files with initial mutation scores <40%
- WHEN Phase 1 tests are implemented following parametrization patterns
- THEN each file achieves ≥80% mutation score
- AND test count reaches ≥15 across the batch
- AND Phase 2 can proceed

#### Scenario: Batch 2 Hooks Completion

- GIVEN 8 hook files with initial mutation scores <50%
- WHEN Phase 2 tests use hook testing library and mock external dependencies
- THEN each file achieves ≥80% mutation score
- AND test count reaches ≥25 across the batch
- AND Phase 3 can proceed

#### Scenario: Batch 3 Store/Components Completion

- GIVEN 7+ complex files with initial mutation scores <60%
- WHEN Phase 3 tests mock child components and use provider contexts
- THEN each file achieves ≥80% mutation score
- AND test count reaches ≥30+ across the batch
- AND CI/CD thresholds are met

### Requirement: Escape Scenario Coverage

The test suite MUST cover all documented mutation escape scenarios per category.

#### Scenario: Arithmetic Operator Mutations Caught

- GIVEN `calculations.ts` with +, -, *, / operators
- WHEN Stryker mutates `a + b` to `a - b`
- THEN at least one test fails
- AND no mutation survives uncaught

#### Scenario: Conditional Negation Mutations Caught

- GIVEN `validators.ts` with regex .test() calls
- WHEN Stryker mutates `if (pattern.test(value))` to `if (!pattern.test(value))`
- THEN at least one test fails

### Requirement: CI/CD Integration

The testing pipeline MUST enforce mutation score thresholds and prevent regressions.

#### Scenario: PR Fails on Mutation Score Drop

- GIVEN PR adds tests to `useForm.ts`
- WHEN mutation score drops from 85% to 79%
- THEN PR fails with clear message showing regression
- AND author must fix before merge

#### Scenario: CI Reports Batch Completion

- GIVEN Phase 1 tests pass locally
- WHEN pushed to feature branch
- THEN CI runs Phase 1 stryker suite
- AND generates HTML report in `coverage/mutation-report/batch-1.html`
