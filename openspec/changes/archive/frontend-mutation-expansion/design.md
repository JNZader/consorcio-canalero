# Design: Frontend Mutation Testing Expansion

## Technical Approach

Implement mutation testing incrementally across the frontend codebase in three complexity-based batches:
1. **Batch 1 (Utilities)**: Low-complexity pure functions with straightforward escape scenarios
2. **Batch 2 (Hooks)**: Medium-complexity React hooks with async logic, mocking, and state management
3. **Batch 3 (Store/Components)**: High-complexity store reducers and React components with integration points

Each batch achieves ≥80% mutation score before advancing to the next, validated by Stryker in CI/CD.

## Architecture Decisions

### Decision: Batch-Based Implementation Over File-By-File

**Choice**: Organize implementation in three batches by complexity level
**Alternatives Considered**:
- File-by-file implementation (difficult to manage batch transitions)
- All files simultaneously (overwhelming, hard to isolate issues)

**Rationale**: Batches allow clear phase boundaries, gradual confidence building, and easier rollback. Early batches serve as template patterns for later batches.

### Decision: Stryker as Mutation Testing Framework

**Choice**: Use Stryker for mutation score reporting and threshold enforcement
**Alternatives Considered**:
- PIT (Java-only, not applicable)
- Manual mutation review (not scalable)

**Rationale**: Stryker is JavaScript-native, integrates with Jest/Vitest, provides detailed HTML reports, and supports CI/CD thresholds.

### Decision: Test Library Patterns Per Complexity

**Choice**:
- **Utilities**: Vitest with `describe.each()` parametrization
- **Hooks**: `@testing-library/react` with `renderHook()` + `act()`
- **Store/Components**: `@testing-library/react` + mocked providers

**Alternatives Considered**:
- Unified testing approach (would require compromises on hook-specific patterns)

**Rationale**: Each layer has unique testing needs. Utilities benefit from parametrization, hooks need renderHook, components need component rendering.

### Decision: Mock Strategy Progression

**Choice**:
- **Batch 1**: No mocking (pure functions)
- **Batch 2**: Mock `localStorage`, `timers`, `fetch` selectively
- **Batch 3**: Mock all external dependencies (child components, API, providers)

**Rationale**: Mocking increases complexity; start simple, introduce selectively as needed.

### Decision: CI/CD Batch-Based Execution

**Choice**: Run Stryker separately per batch in CI, reporting batch-specific thresholds
**Alternatives Considered**:
- Run all mutations once (long feedback loop, batch rollback unclear)

**Rationale**: Faster feedback per batch, easier to debug failures, clear batch completion gates.

## File Organization & Implementation Sequence

### Directory Structure

```
src/
├── lib/
│   ├── utils/
│   │   ├── __tests__/
│   │   │   ├── formatters.test.ts         (Batch 1)
│   │   │   ├── validators.test.ts         (Batch 1)
│   │   │   ├── calculations.test.ts       (Batch 1)
│   │   │   ├── constants.test.ts          (Batch 1)
│   │   │   └── object-helpers.test.ts     (Batch 1)
│   │   ├── formatters.ts
│   │   ├── validators.ts
│   │   ├── calculations.ts
│   │   ├── constants.ts
│   │   └── object-helpers.ts
│   └── api/
│       └── __tests__/
│           └── [existing tests]
├── hooks/
│   ├── __tests__/
│   │   ├── useForm.test.ts            (Batch 2)
│   │   ├── useAuth.test.ts            (Batch 2)
│   │   ├── useAsync.test.ts           (Batch 2)
│   │   ├── useLocalStorage.test.ts    (Batch 2)
│   │   ├── useDebounce.test.ts        (Batch 2)
│   │   ├── useTheme.test.ts           (Batch 2)
│   │   ├── useModal.test.ts           (Batch 2)
│   │   └── usePagination.test.ts      (Batch 2)
│   ├── useForm.ts
│   ├── useAuth.ts
│   ├── useAsync.ts
│   ├── useLocalStorage.ts
│   ├── useDebounce.ts
│   ├── useTheme.ts
│   ├── useModal.ts
│   └── usePagination.ts
├── store/
│   ├── __tests__/
│   │   ├── authStore.test.ts         (Batch 3)
│   │   └── appStore.test.ts          (Batch 3)
│   ├── authStore.ts
│   └── appStore.ts
└── components/
    ├── Form/
    │   ├── __tests__/
    │   │   └── index.test.tsx          (Batch 3)
    │   └── index.tsx
    ├── DataTable/
    │   ├── __tests__/
    │   │   └── index.test.tsx          (Batch 3)
    │   └── index.tsx
    ├── Modal/
    │   ├── __tests__/
    │   │   └── index.test.tsx          (Batch 3)
    │   └── index.tsx
    ├── Layout/
    │   ├── __tests__/
    │   │   └── index.test.tsx          (Batch 3)
    │   └── index.tsx
    └── pages/
        └── Dashboard/
            ├── __tests__/
            │   └── index.test.tsx      (Batch 3)
            └── index.tsx
```

### Implementation Sequence

**Batch 1 (Utilities)**: Implement in order
1. `formatters.test.ts` — Simplest test patterns
2. `validators.test.ts` — Regex boundary testing
3. `calculations.test.ts` — Arithmetic operator coverage
4. `constants.test.ts` — Enum/constant validation
5. `object-helpers.test.ts` — Object mutation testing

**Batch 2 (Hooks)**: Implement in order
1. `useDebounce.test.ts` — Timer logic (simplest hook pattern)
2. `useLocalStorage.test.ts` — Storage persistence
3. `useTheme.test.ts` — State + storage combo
4. `useModal.test.ts` — Simple state management
5. `usePagination.test.ts` — Calculation-based hook
6. `useForm.test.ts` — Complex state + validation
7. `useAuth.test.ts` — Async + error handling
8. `useAsync.test.ts` — Advanced async patterns

**Batch 3 (Store/Components)**: Implement in order
1. `authStore.test.ts` — Store reducer testing
2. `appStore.test.ts` — Complex store logic
3. `Modal/index.test.tsx` — Simple component (event handling)
4. `Form/index.test.tsx` — Complex component (field arrays, conditional rendering)
5. `DataTable/index.test.tsx` — Data-driven component (sorting, filtering, pagination)
6. `Layout/index.test.tsx` — Layout conditionals
7. `Dashboard/index.test.tsx` — Page-level integration

## Test Pattern Library (Shared Fixtures & Mocks)

### Pattern 1: Parametrized Unit Tests (Batch 1)

```typescript
// src/lib/utils/__tests__/setup.ts
export const boundaryValues = [
  { input: 0, name: 'zero' },
  { input: 1, name: 'one' },
  { input: -1, name: 'negative one' },
  { input: Number.MAX_SAFE_INTEGER, name: 'max safe int' },
  { input: Number.MIN_SAFE_INTEGER, name: 'min safe int' },
];

export const commonStrings = [
  { input: '', name: 'empty string' },
  { input: ' ', name: 'whitespace only' },
  { input: 'normal text', name: 'normal' },
  { input: 'UPPERCASE', name: 'uppercase' },
  { input: '  trimmed  ', name: 'with padding' },
];
```

### Pattern 2: Hook Testing Setup (Batch 2)

```typescript
// src/hooks/__tests__/setup.ts
import { renderHook, act, waitFor } from '@testing-library/react';
import { ReactNode } from 'react';

export function renderHookWithProviders<T>(
  hook: () => T,
  { wrapper }: { wrapper?: ({ children }: { children: ReactNode }) => ReactNode } = {}
) {
  return renderHook(hook, { wrapper });
}

export const mockLocalStorage = () => {
  const store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      Object.keys(store).forEach(key => delete store[key]);
    }),
  };
};

export const setupFakeTimers = () => {
  vi.useFakeTimers();
  return () => vi.runOnlyPendingTimers();
};
```

### Pattern 3: Component Testing Setup (Batch 3)

```typescript
// src/components/__tests__/setup.tsx
import { render, screen, within } from '@testing-library/react';
import { ReactElement, ReactNode } from 'react';

export function renderComponent(
  component: ReactElement,
  { mocks = {}, ...options } = {}
) {
  const AllProviders = ({ children }: { children: ReactNode }) => (
    <MockProvider {...mocks}>{children}</MockProvider>
  );
  return render(component, { wrapper: AllProviders, ...options });
}

export const mockChildComponent = (displayName: string, defaultProps = {}) => {
  const MockComponent = vi.fn((props) => (
    <div data-testid={`mock-${displayName}`} {...defaultProps} {...props} />
  ));
  MockComponent.displayName = `Mock${displayName}`;
  return MockComponent;
};
```

## Stryker Configuration Extension

### File: `stryker.config.json`

```json
{
  "mutate": [
    "src/lib/utils/**/*.ts",
    "src/hooks/**/*.ts",
    "src/store/**/*.ts",
    "src/components/**/*.tsx",
    "src/pages/**/*.tsx",
    "!src/**/*.d.ts",
    "!src/**/*.test.ts",
    "!src/**/*.test.tsx"
  ],
  "testRunner": "vitest",
  "reporters": [
    "clear-text",
    "html",
    "progress"
  ],
  "htmlReporter": {
    "baseDir": "coverage/mutation-report"
  },
  "mutationThreshold": 80,
  "thresholdBreaker": {
    "highBreaker": 85,
    "breaking": 80
  },
  "timeoutMS": 10000,
  "timeoutFactor": 1.5,
  "concurrency": 4,
  "ignoreStatic": false,
  "ignorePatterns": [
    "**/node_modules/**",
    "**/*.d.ts",
    "**/dist/**"
  ]
}
```

### Batch-Specific Configuration Files

**`stryker-batch-1.config.json`** (Utilities, <45s):
```json
{
  "extends": "stryker.config.json",
  "mutate": [
    "src/lib/utils/**/*.ts",
    "!src/**/*.d.ts"
  ],
  "mutationThreshold": 80,
  "concurrency": 6,
  "timeoutMS": 8000
}
```

**`stryker-batch-2.config.json`** (Hooks, <1m 15s):
```json
{
  "extends": "stryker.config.json",
  "mutate": [
    "src/hooks/**/*.ts",
    "!src/**/*.d.ts"
  ],
  "mutationThreshold": 80,
  "concurrency": 4,
  "timeoutMS": 10000
}
```

**`stryker-batch-3.config.json`** (Store/Components, <2m):
```json
{
  "extends": "stryker.config.json",
  "mutate": [
    "src/store/**/*.ts",
    "src/components/**/*.tsx",
    "src/pages/**/*.tsx",
    "!src/**/*.d.ts"
  ],
  "mutationThreshold": 80,
  "concurrency": 4,
  "timeoutMS": 15000
}
```

## Performance Budget

| Batch | Files | Target Time | Mutations/File | CI Schedule |
|-------|-------|-------------|----------------|------------|
| **Batch 1** | 5 utils | 45s | ~50-80 | Every PR |
| **Batch 2** | 8 hooks | 1m 15s | ~100-150 | Every PR |
| **Batch 3** | 7+ complex | 2m | ~150-250 | Post-merge, nightly |
| **Full Suite** | 20+ | 4m total | ~8000+ | Nightly only |

**Rationale**: PR feedback loop must stay <2m for Batch 1+2. Batch 3 + full suite run post-merge or on schedule.

## Rollback Strategy

### Pre-Batch Checkpoints

Before starting each batch:
1. Run mutation tests on baseline (establish baseline score)
2. Tag baseline commits: `batch-1-baseline`, `batch-2-baseline`, `batch-3-baseline`
3. Create feature branch per batch: `feat/mutation-batch-1`, `feat/mutation-batch-2`, etc.

### During-Batch Rollback

**If mutation score stalls or regresses**:
1. Identify problematic test(s) via Stryker report
2. Fix test logic (not the source code)
3. Re-run Stryker; if still blocked, revert last 1-2 commits

**If batch takes >150% of budgeted time**:
1. Pause, assess complexity (may have underestimated)
2. Consider splitting next batch differently
3. Document learnings in `MUTATION_TESTING.md`

### Post-Batch Rollback

**If full batch regression after merge**:
1. Revert entire batch commit(s)
2. Post-mortem: Why did CI catch what local testing didn't?
3. Fix CI/tool config, re-run batch

### Emergency Rollback (CI Blocked)

```bash
# If merged batch breaks main CI
git revert <batch-merge-commit>
# Analyze Stryker report offline
# Re-submit with fixes in new PR
```

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Mutation score plateaus at 75% | Batch incomplete, blocks next | Pause, analyze escape scenarios, adjust mocking strategy |
| Tests become brittle/flaky | Test maintenance overhead | Use `waitFor()`, stable selectors; review flaky test reports weekly |
| Stryker execution slow (>2m batch) | Developer feedback loop suffers | Parallelize mutations, reduce file scope per batch, profile bottlenecks |
| Batch complexity underestimated | Scope creep, missed deadline | Track burn-down per batch, split if >120% budget consumed |
| Hook testing library mocking complexity | Increases test fragility | Start simple (Batch 2 early files like useDebounce); learn patterns before complex hooks |
| Component snapshots vs. behavioral | Snapshot tests harder to maintain | Use behavioral assertions, data-testid selectors; avoid snapshots where possible |

## Open Questions

- [ ] Should Batch 3 component tests use snapshot testing or behavioral assertions?
- [ ] Do we mock child components in DataTable (integration test approach) or render real children (E2E approach)?
- [ ] Should async hooks (useAuth, useAsync) test race conditions and concurrent requests?
- [ ] Which store implementation pattern: Zustand, Redux, Context? (Affects mock strategy)

## Notes on Implementation

1. **Reuse Test Patterns**: After implementing setup.ts for each batch, subsequent test files become much faster
2. **Escape Analysis**: Track "survived mutations" in Stryker reports; if pattern emerges, add specific test case
3. **Performance Profiling**: If any batch exceeds time budget, use `stryker run --profile` to identify slow mutations
4. **Documentation**: Keep running `MUTATION_TESTING.md` updated with findings per batch
5. **Team Communication**: Share mutation reports after each batch; discuss escape patterns for continuous learning
