# Frontend Mutation Testing - Phase 3 Roadmap

## Overview
Phase 2 scaled mutation test coverage from 3 to 9 hooks with 276 passing tests. Phase 3 will focus on **depth and quality** — improving mutation score from baseline to ≥80% per hook.

## Phase 2 → Phase 3 Handoff

### What Phase 2 Delivered
✅ **All 9 hooks have unit tests**:
- useJobStatus (43 tests)
- useMapReady (43 tests)
- useSelectedImage (47 tests)
- useAuth (33 tests)
- useInfrastructure (20 tests)
- useCaminosColoreados (15 tests)
- useImageComparison (31 tests)
- useContactVerification (21 tests)
- useGEELayers (23 tests)

✅ **All tests passing**: `npm test tests/hooks/` = 276/276 ✅

✅ **Mutation test infrastructure**: Ready to measure kill rates

### Key Metric: Mutation Kill Rate

**Definition**: % of mutations caught by tests
- 0-30% = Very weak tests (need major work)
- 30-60% = Weak tests (missing assertions, edge cases)
- 60-80% = Good tests (Phase 3 target)
- 80-95% = Excellent tests (Phase 4 consideration)
- 95-100% = Perfect coverage (rarely needed)

**Phase 3 Goal**: ≥70% kill rate per hook (pragmatic, achievable)

## Phase 3 Work Plan

### Phase 3A: Measure Baseline Kill Rates

**Step 1**: Run mutation tests on each hook individually
```bash
cd ~/consorcio-canalero/consorcio-web

# Run mutation tests (full suite)
npm run mutation:run

# Or target specific hooks by modifying stryker.config.json
# and running: npm run mutation:run
```

**Step 2**: Extract mutation report data
- Open `reports/mutation/mutation.html` in browser
- Document kill rate for each hook
- Note which mutation types are surviving

**Expected baseline** (estimated, may vary):
| Hook | Est. Kill Rate | Status |
|------|----------------|--------|
| useJobStatus | 75% | Good baseline |
| useMapReady | 70% | Needs work |
| useSelectedImage | 72% | Needs work |
| useAuth | 55% | Needs improvement |
| useInfrastructure | 50% | Needs improvement |
| useCaminosColoreados | 45% | Needs significant work |
| useImageComparison | 68% | Needs work |
| useContactVerification | 50% | Needs improvement |
| useGEELayers | 48% | Needs improvement |

### Phase 3B: Identify Survival Patterns

**Common mutation types that survive**:
1. **Boolean mutations**: `true` → `false` (test uses truthy, not exact)
2. **Boundary mutations**: `>` → `>=` (no edge case tests)
3. **Return value mutations**: `return x` → `return null` (weak assertion)
4. **Condition mutations**: `&&` → `||` (logic not fully tested)
5. **State update mutations**: Missing setter calls (state change not verified)

**For each hook**:
1. Read mutation report HTML
2. Identify top 5 mutation patterns that survive
3. Document specific code lines affected
4. Plan test additions

### Phase 3C: Improve Tests Progressively

**Per hook process** (takes ~30-45 min per hook):

1. **Analyze survived mutations**
   ```bash
   # Open mutation.html, find specific line numbers with red/yellow mutations
   ```

2. **Add targeted tests**
   - Add `describe("Specific mutation: <mutation type>")` blocks
   - Create parametrized tests for boundary conditions
   - Add explicit assertion tests

3. **Test locally**
   ```bash
   npm test tests/hooks/useHookName.test.ts
   ```

4. **Verify improvement**
   ```bash
   # Re-run mutation tests (optional, time-consuming)
   npm run mutation:run
   ```

**Example improvement pattern**:

Before (weak):
```javascript
test("should update state", () => {
  const { result } = renderHook(() => useMyHook());
  expect(result.current.value).toBeDefined();
});
```

After (strong):
```javascript
describe("catches mutation: should handle null/false/0 values", () => {
  test("should initialize with correct default value", () => {
    const { result } = renderHook(() => useMyHook());
    expect(result.current.value).toBe(expectedDefault);
  });

  test("should NOT set value to undefined", () => {
    const { result } = renderHook(() => useMyHook());
    expect(result.current.value).not.toBeUndefined();
  });

  test("should differentiate between false and null", () => {
    const { result } = renderHook(() => useMyHook(false));
    expect(result.current.value).toBe(false);
    expect(result.current.value).not.toBe(null);
  });
});
```

### Phase 3D: Establish Baseline & CI/CD Gate

Once ≥70% per hook is achieved:

1. **Document baseline**
   ```markdown
   # Mutation Testing Baseline - Frontend Hooks
   
   Generated: [date]
   
   | Hook | Kill Rate | Target | Status |
   |------|-----------|--------|--------|
   | useJobStatus | 78% | ≥70% | ✅ |
   | ...
   ```

2. **Update CLAUDE.md**
   - Set frontend target to ≥70%
   - Document Phase 3 results

3. **Update stryker.config.json**
   - Add threshold enforcement
   - Block CI if kill rate drops below baseline

4. **Create CI/CD gate** (similar to backend)
   ```yaml
   # In .github/workflows/mutation-testing.yml
   - name: Check mutation score
     if: github.event_name == 'pull_request'
     run: |
       kill_rate=$(npm run mutation:run | grep -oP 'Kill rate: \K[\d.]+')
       if (( $(echo "$kill_rate < 70" | bc -l) )); then
         echo "Kill rate ($kill_rate%) below threshold (70%)"
         exit 1
       fi
   ```

## Phase 3 Success Criteria

✅ All hooks at ≥70% kill rate
✅ Baseline documented and committed
✅ CI/CD enforcement in place
✅ Team educated on mutation testing results
✅ Ready for Phase 4 (component testing, if needed)

## Phase 3 Timeline Estimate

| Task | Effort | Duration |
|------|--------|----------|
| Run mutation baseline | 30 min | 1 session |
| Analyze survival patterns | 1 hour | 1 session |
| Improve tests (6 hooks) | 4-5 hours | Multiple sessions |
| Documentation | 30 min | 1 session |
| CI/CD setup | 1 hour | 1 session |
| **Total** | **7-8 hours** | **1-2 weeks** |

## Phase 3 Git Workflow

```bash
# Create feature branch
git checkout -b feature/phase-3-mutation-improvements

# For each hook improvement:
git add tests/hooks/useHookName.test.ts
git commit -m "test(mutation): improve useHookName kill rate to X%

- Fixed Boolean mutations: added explicit toBe(false) checks
- Fixed boundary mutations: added parametrized edge case tests
- Fixed return value mutations: added null/undefined checks
- Mutation baseline: X/Y kills (Z%)"

# After all 9 hooks improved:
git add MUTATION_TESTING_BASELINE.md
git commit -m "docs(mutation): establish Phase 3 baseline at 70%+ per hook"

# Create PR and merge after CI passes
```

## Phase 3 Success Signals

### Immediate (After Testing)
- All hook tests still passing ✅
- Mutation kill rate ≥70% per hook
- No regression in existing tests

### Long-term (After CI/CD)
- PRs blocked if kill rate drops below baseline
- New tests required to maintain score
- Team regularly checks mutation reports

## What NOT to Do in Phase 3

❌ Don't aim for 100% kill rate (overkill, diminishing returns)
❌ Don't modify source code just to improve scores (defeats purpose)
❌ Don't run full mutation tests constantly (it's slow)
❌ Don't skip parametrized tests to save time (they're crucial)
❌ Don't assume high coverage = high mutation score

## Resources

- **Mutation Report**: `consorcio-web/reports/mutation/mutation.html`
- **Test Configuration**: `consorcio-web/stryker.config.json`
- **Test Files**: `consorcio-web/tests/hooks/*.test.ts`
- **Documentation**: `docs/MUTATION_TESTING.md`

## Questions for Team

Before starting Phase 3, clarify:

1. **Timeline**: Is 1-2 weeks acceptable?
2. **Target**: Is 70% kill rate the right goal?
3. **Ownership**: Who will own Phase 3 work?
4. **CI/CD**: Should we block PRs for mutation score?
5. **Review**: Who will review mutation test improvements?

---

**Next**: Schedule Phase 3 kickoff meeting with team
