# Mutation Testing Guide

A comprehensive guide to understanding, maintaining, and improving mutation testing across the Consorcio Canalero project.

## Table of Contents
1. [Overview & Purpose](#overview--purpose)
2. [Terminology](#terminology)
3. [Baseline Scores](#baseline-scores)
4. [Reading Stryker Reports](#reading-stryker-reports)
5. [Debugging Low Scores](#debugging-low-scores)
6. [Team Process](#team-process)

---

## Overview & Purpose

### What is Mutation Testing?

Mutation testing is a quality assurance technique that verifies the effectiveness of your test suite. It works by:

1. **Creating mutations** - Intentionally introducing small, deliberate "bugs" (mutations) into the source code
2. **Running tests** - Executing the test suite against each mutation
3. **Checking results** - Measuring whether tests catch the mutations (kill them)

### Why Mutation Testing Matters

Mutation testing uncovers **test quality gaps** that traditional code coverage misses:

- **Coverage ≠ Quality**: You can have 95% code coverage but still miss critical logic errors
- **Catches logic bugs**: Detects missing assertions, incomplete edge case handling, and weak test conditions
- **Prevents regressions**: Ensures new code changes are properly tested before merge
- **Builds confidence**: High mutation scores indicate robust, effective tests

### How It Integrates with CI/CD

In this project:
- **Backend (Python)**: Cosmic-Ray mutation testing runs on every PR and merge to main
  - Target: **100% kill rate** on critical modules
  - Failure threshold: <100% OR >5% regression from baseline
- **Frontend (TypeScript)**: Stryker mutation testing (rollout in Phase 2)
  - Target: **≥80% kill rate** on critical components
  - Failure threshold: <80% OR >5% regression from baseline

Gates are enforced in `.github/workflows/mutation-testing.yml` - **PRs cannot merge if mutation tests fail**.

---

## Terminology

### Core Concepts

| Term | Definition | Example |
|------|-----------|---------|
| **Mutation** | A small, intentional code change introduced for testing | Changing `==` to `!=` in a condition |
| **Killed** | A mutation that was caught by at least one test | Test failed when mutation was applied ✓ |
| **Survived/Escaped** | A mutation that passed all tests uncaught | Test suite didn't catch the mutation ✗ |
| **Kill Rate** | Percentage of mutations killed by your tests | 454 killed / 454 total = 100% kill rate |
| **Threshold** | Minimum acceptable kill rate to pass CI gates | Backend: 100%, Frontend: 80% |
| **Regression** | Drop in kill rate from previous baseline | Was 100%, now 95% = 5% regression |

### Mutation Types

- **Logical mutations**: Change operators (`==` → `!=`, `>` → `<`, `+` → `-`)
- **Conditional mutations**: Remove conditions or modify boolean logic
- **Return value mutations**: Change or negate return values
- **Literal mutations**: Modify numbers, strings, or constants
- **Assignment mutations**: Remove or modify assignments

### Batch Status

| Batch | Tool | Status | Target Score |
|-------|------|--------|--------------|
| **Backend Core** | cosmic-ray | ✅ Complete | 100% |
| **Frontend Phase 1** | stryker | 📋 Spec Ready | ≥80% |
| **Frontend Phase 2** | stryker | 🔜 Planned | ≥80% |

---

## Baseline Scores

### Backend (Python) - Production Ready ✅

Mutation testing is fully integrated in the backend with a **100% kill rate** across all monitored modules.

#### Current Baselines

| Module | File Path | Mutations | Killed | Score | Status |
|--------|-----------|-----------|--------|-------|--------|
| **Reports** | `app/api/v1/endpoints/reports.py` | 200+ | 200+ | 100% | ✅ Production Ready |
| **Sugerencias** | `app/api/v1/endpoints/sugerencias.py` | 100+ | 100+ | 100% | ✅ Production Ready |
| **Schemas** | `app/api/v1/schemas.py` | 50+ | 50+ | 100% | ✅ Production Ready |
| **Total** | - | **454** | **454** | **100%** | ✅ **Baseline Set** |

#### How These Baselines Were Achieved

1. **Comprehensive test coverage**: Unit and integration tests cover all major code paths
2. **Edge case handling**: Tests explicitly validate boundary conditions and error cases
3. **Assertion quality**: Tests use specific, targeted assertions rather than general checks
4. **Parametrized tests**: Many scenarios tested with different inputs to catch logical variations

#### Test Files Supporting These Baselines

- `tests/test_tramites_schema.py` - Schema validation tests
- `tests/test_mutation_targets.py` - Focused tests for mutation targets
- `tests/test_reports_contract.py` - Contract tests for reports endpoint
- `tests/test_sugerencias_contract.py` - Contract tests for sugerencias endpoint

### Frontend (TypeScript) - Implementation Pending 📋

Frontend mutation testing configuration is ready but implementation is pending. See [Phase 2 Real Hooks](../openspec/changes/frontend-mutation-expansion/PHASE_2_REAL_HOOKS.md) for the expansion plan.

#### Target Baselines (Post-Phase 2)

| Category | Target Files | Status | Target Score |
|----------|-------------|--------|----------------|
| **Utilities** | 5 utility files | 📋 Spec Ready | ≥80% |
| **Hooks** | 8 custom React hooks | 📋 Spec Ready | ≥80% |
| **Components** | Store + UI components | 📋 Spec Ready | ≥80% |

---

## Reading Stryker Reports

### Backend: Cosmic-Ray Reports

#### Location
After a mutation test run, check:
```
gee-backend/coverage/mutation-report/
```

#### Command to Generate Reports
```bash
cd gee-backend
python3 scripts/cosmic_gate.py --min-kill-rate 1.0
```

#### Interpreting the Output

```
Mutation summary: total=454 killed=450 survived=4 timeout=0 incompetent=0 other=0 pending=0
Kill rate: 99.12% (required >= 100.00%)
```

- **total**: Total mutations applied during testing
- **killed**: Mutations caught by your tests (good!)
- **survived**: Mutations that passed undetected (bad - test gaps)
- **timeout**: Mutations that caused test execution to hang (usually safe to ignore)
- **incompetent**: Invalid mutations the tool couldn't apply (usually safe to ignore)
- **pending**: Unfinished mutations (should be 0 at end of run)

### Frontend: Stryker Reports

#### Location
After a mutation test run, check:
```
consorcio-web/reports/mutation/index.html
```

#### Key Metrics in Dashboard

- **Mutation Score**: Percentage of killed mutations (target: ≥80%)
- **Killed**: Count of mutations caught by tests
- **Survived**: Count of escaped mutations (investigate these!)
- **Compile Errors**: Mutations that broke code (usually safe)
- **No Coverage**: Code lines not covered by tests (priority for testing)

#### Identifying Escaped Mutations in Reports

1. Click on source file in report
2. Look for lines highlighted in **red** or **yellow**
3. **Red** = mutation survived (tests didn't catch it)
4. Hover over the red line to see the exact mutation applied
5. Example mutations to look for:
   - Boundary conditions (`<` changed to `<=`)
   - Logical negation (truthy/falsy checks flipped)
   - Return value modifications

### Common Report Patterns

| Pattern | Meaning | Action |
|---------|---------|--------|
| Many red lines in one function | Insufficient test coverage for that function | Add tests for that function |
| Red lines in branches (if/else) | Edge cases not tested | Add parametrized tests for all branches |
| Red lines after recent commit | New code not properly tested | Review and enhance tests |

---

## Debugging Low Scores

### Step-by-Step Investigation Process

#### Step 1: Identify the Problem
```bash
# For backend
cd gee-backend
python3 scripts/cosmic_gate.py --min-kill-rate 1.0 2>&1 | tee mutation_output.log

# For frontend (when Phase 2 is ready)
cd consorcio-web
npm run mutation:test
```

#### Step 2: Find the Escaped Mutations

**Backend example**:
```
Mutation: reports.py:45 - Changed == to !=
  Status: SURVIVED (not caught by tests!)
```

**Frontend example**:
- Open `consorcio-web/reports/mutation/index.html`
- Click on the file with escaped mutations
- Red highlights = survived mutations

#### Step 3: Understand the Root Cause

Common reasons for escaped mutations:

| Root Cause | Example | How to Fix |
|-----------|---------|-----------|
| **Insufficient assertions** | Test checks that code runs without error, but doesn't verify the result | Add specific assertions: `expect(result).toEqual(expectedValue)` |
| **Missing edge cases** | Test only covers the happy path, not boundary conditions | Add parametrized tests with edge cases (null, empty, max value) |
| **Incomplete mocking** | Test mocks dependencies but doesn't validate all interactions | Mock and assert all important calls |
| **Weak boolean checks** | Test just checks `if (result)` without validating the actual value | Use specific assertions like `toBe(true)` not `toBeTruthy()` |
| **Ignored error cases** | Test doesn't check error handling paths | Add try/catch tests and error assertions |

#### Step 4: Locate and Fix the Tests

**Example: Function with low mutation score**

Original function:
```python
def calculate_fee(amount: float, is_member: bool) -> float:
    if is_member:
        return amount * 0.9  # 10% discount
    return amount
```

Weak test (mutation survives):
```python
def test_calculate_fee_member():
    result = calculate_fee(100, True)
    assert result is not None  # Weak! Doesn't verify the value
```

Strong test (kills mutations):
```python
def test_calculate_fee_member():
    result = calculate_fee(100, True)
    assert result == 90  # Strong! Verifies exact value

def test_calculate_fee_non_member():
    result = calculate_fee(100, False)
    assert result == 100  # Also test the non-member case

def test_calculate_fee_edge_case():
    result = calculate_fee(0, True)
    assert result == 0  # Test boundary
```

### Common Low-Score Patterns and Fixes

#### Pattern 1: Low Scores in Validation Code
```python
# Low score
def validate_email(email: str) -> bool:
    return "@" in email  # Weak - only checks for @

# Test that survives mutations
assert validate_email("test@example.com") is True
```

**Fix**: Test invalid cases and boundaries
```python
# Higher score
assert validate_email("test@example.com") is True
assert validate_email("test") is False  # Kill mutations
assert validate_email("@") is False
assert validate_email("test@") is False
```

#### Pattern 2: Low Scores in Calculation Code
```python
# Low score
def calculate_total(items: list) -> float:
    total = 0
    for item in items:
        total += item["price"]
    return total

# Test that survives mutations
assert calculate_total([{"price": 10}]) >= 0
```

**Fix**: Use exact assertions
```python
assert calculate_total([{"price": 10}, {"price": 20}]) == 30
assert calculate_total([]) == 0
assert calculate_total([{"price": 5.5}, {"price": 4.5}]) == 10
```

#### Pattern 3: Low Scores in Conditional Logic
```python
# Low score
def get_status(age: int) -> str:
    if age < 18:
        return "minor"
    elif age >= 18 and age < 65:
        return "adult"
    else:
        return "senior"

# Weak test - doesn't kill boundary mutations
assert get_status(20) == "adult"
```

**Fix**: Test all boundaries
```python
assert get_status(17) == "minor"    # Boundary
assert get_status(18) == "adult"    # Boundary
assert get_status(64) == "adult"    # Boundary
assert get_status(65) == "senior"   # Boundary
assert get_status(100) == "senior"
```

### Using Parametrized Tests for Better Scores

Parametrized tests make it easy to test many cases and kill more mutations:

**Python (pytest)**:
```python
import pytest

@pytest.mark.parametrize("amount,is_member,expected", [
    (100, True, 90),      # 10% member discount
    (100, False, 100),    # No discount
    (0, True, 0),         # Zero amount
    (0, False, 0),        # Zero amount (non-member)
    (999.99, True, 899.991),  # Large amount
])
def test_calculate_fee(amount, is_member, expected):
    result = calculate_fee(amount, is_member)
    assert result == pytest.approx(expected)
```

**TypeScript (Vitest)**:
```typescript
describe("calculateFee", () => {
  test.each([
    [100, true, 90],      // 10% member discount
    [100, false, 100],    // No discount
    [0, true, 0],         // Zero amount
    [0, false, 0],        // Zero amount (non-member)
    [999.99, true, 899.991], // Large amount
  ])("calculates fee correctly for %i with member=%s", (amount, isMember, expected) => {
    expect(calculateFee(amount, isMember)).toBeCloseTo(expected);
  });
});
```

### Mutation Testing vs Code Coverage

| Aspect | Code Coverage | Mutation Testing |
|--------|--------------|-----------------|
| **Measures** | Lines executed during tests | Test effectiveness at catching bugs |
| **Can miss** | Logic errors, boundary issues | Hidden gaps in assertions |
| **Better for** | Identifying untested code | Improving test quality |
| **Typical target** | 70-80% | 80-100% |

**Key insight**: 100% code coverage with 50% mutation kill rate means you're exercising code but not verifying results properly.

---

## Team Process

### When Mutation Tests Run

#### Backend (Production)
- **On every PR**: Must pass before merge approval
- **On push to main**: Blocks deployment if failed
- **On push to develop**: Informational only (no block)
- **Schedule**: Manual workflow dispatch available anytime

#### Frontend (When Phase 2 Ready)
- **On every PR**: Must pass before merge approval
- **On push to main**: Blocks deployment if failed
- **Nightly**: Full suite runs at 2 AM UTC

### Approval and Exceptions

#### Normal Case: Mutation Tests Pass ✅
- Automatic pass in CI
- PR can be merged normally
- No team lead approval needed

#### Regression Case: <5% Drop
- Tests fail in CI with regression warning
- **Team review required** before merging
- Process:
  1. Developer analyzes failed mutations
  2. Adds or enhances tests to fix regressions
  3. Pushes update; CI re-runs
  4. Merge when tests pass

#### Exception Case: >5% Drop or Critical Regression
- Tests fail in CI with BLOCK message
- **Team lead approval required**
- Process:
  1. Developer creates issue explaining:
     - What changed
     - Why mutation score dropped
     - Recovery plan
  2. Team lead reviews and comments: `@consorcio-bot approve-mutation-exception`
  3. Exception granted for **single PR only**
  4. Developer must improve score in follow-up PR

### Team Training Checklist

Before working on code in this project, ensure you've completed:

- [ ] Read [MUTATION_TESTING.md](MUTATION_TESTING.md) (this document)
- [ ] Read [MUTATION_ROLLBACK.md](MUTATION_ROLLBACK.md) - emergency procedures
- [ ] Review backend baseline scores in [MUTATION_TESTING_BASELINE.md](MUTATION_TESTING_BASELINE.md)
- [ ] Understand CI/CD gates:
  - Backend: 100% kill rate (≥0.12 = 12% minimum acceptance)
  - Frontend: 80% kill rate (when Phase 2 ready)
- [ ] Know how to access mutation reports:
  - Backend: `gee-backend/coverage/mutation-report/`
  - Frontend: `consorcio-web/reports/mutation/index.html`
- [ ] Can explain the difference between code coverage and mutation score
- [ ] Know what "escaped mutation" means and why it matters
- [ ] Familiar with the rollback procedure for emergencies

### Common Questions

**Q: Does a high code coverage guarantee high mutation score?**
A: No. Code coverage shows lines executed; mutation testing shows whether tests actually verify behavior. 95% coverage with 60% mutation score = weak assertions.

**Q: What's a "good" mutation score?**
A: 
- **80-90%**: Good. Most mutations caught; minor edge cases may remain.
- **90-100%**: Excellent. Test suite is comprehensive and robust.
- **<80%**: Needs improvement. Investigate and enhance tests.

**Q: Can I ignore low mutation scores on legacy code?**
A: No. If it's monitored by the gate, it must pass. If you can't improve it, request a team exception with justification.

**Q: How long do mutation tests take to run?**
A: 
- Backend: ~30-35 minutes (454 mutations × test suite per mutation)
- Frontend: ~15-20 minutes (estimated, depends on file count)

Runs are optimized but are slower than unit tests because each mutation requires a full test run.

**Q: What happens if a mutation test run times out?**
A: 
- Check the timeout setting in config (120s per mutation for backend)
- If many timeouts, may indicate performance issues in code or tests
- Contact team lead to investigate

### Requesting a Threshold Exception

If you need to temporarily adjust the mutation score threshold:

1. Create an issue with title: `[mutation] Exception: {module} - Temporary threshold adjustment`
2. Include in the issue:
   - Current score and required score
   - Reason for exception
   - Target score for next sprint
   - Recovery plan
3. Request review from team lead: `@team/leads`
4. Once approved, add to `.github/workflows/mutation-testing.yml` (temporary comment)
5. Create follow-up issue to remove the exception

Example:
```yaml
# TEMPORARY EXCEPTION - Remove by 2026-03-31
# Reason: Legacy refactoring phase
# Author: @developer, Approved: @lead
# Tracking issue: #1234
```

---

## Related Documentation

- **[MUTATION_ROLLBACK.md](MUTATION_ROLLBACK.md)** - Emergency procedures for regressions
- **[MUTATION_TESTING_BASELINE.md](MUTATION_TESTING_BASELINE.md)** - Tracking baselines and scores
- **[Frontend Mutation Expansion](../openspec/changes/frontend-mutation-expansion/)** - Phase 2 plan
- **CI/CD Workflow**: `.github/workflows/mutation-testing.yml`
- **Backend Config**: `gee-backend/.cosmic-ray.toml`
- **Frontend Config**: `consorcio-web/stryker.config.json`

---

## Support & Questions

For questions about mutation testing:
1. Check this guide first (you might find the answer!)
2. Review [MUTATION_ROLLBACK.md](MUTATION_ROLLBACK.md) for emergency scenarios
3. Ask in #engineering-practices Slack channel
4. Contact team lead if you need a threshold exception

Happy testing! 🧪
