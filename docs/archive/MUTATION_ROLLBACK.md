# Mutation Testing Rollback Runbook

**Created**: 2026-03-09  
**For**: Consorcio Canalero Frontend  
**Audience**: On-call engineers, CI/CD maintainers  

---

## Quick Reference

| Scenario | Command | Time |
|----------|---------|------|
| **Rollback last batch** | `git revert -m 1 <merge-commit-hash>` | 5 min |
| **Pause CI (emergency)** | Branch protection rule → disable check | 2 min |
| **Debug failing test** | `npm run test:run -- <path> --reporter=verbose` | 10 min |
| **Re-run mutation batch** | `npm run mutation:run -- stryker-batch-N.config.json` | 45s-2min |

---

## Pre-Batch Checklist

### Before Merging Any Mutation Testing Batch

- [ ] **Main branch is clean**: `git status` shows no uncommitted changes
- [ ] **Latest from upstream**: `git pull origin main`
- [ ] **All existing tests pass**: `npm run test:run`
- [ ] **Baseline recorded**: Store current mutation scores (see below)
- [ ] **Feature branch created**: `git checkout -b mutation-test/batch-N`
- [ ] **Slack notification sent**: "@team-dev: Deploying mutation test batch N"

### Recording Baseline

```bash
# Before batch merge, store current mutation scores
npm run mutation:run -- stryker.config.json > /tmp/baseline-before-batch-N.txt 2>&1

# Extract and document
grep "Mutation score" /tmp/baseline-before-batch-N.txt
# Example: "Mutation score: 68% (killed: 238, survived: 110, timeout: 12)"
```

---

## During-Batch Troubleshooting

### Scenario 1: Mutation Tests Fail (Score < 75%)

**Problem**: Stryker reports mutation score below threshold on a file

**Steps**:
1. **Identify the file**: Check Stryker HTML report
   ```bash
   open coverage/mutation-report/batch-N/index.html
   ```

2. **Find survived mutations**: Click file → view escaped mutants
   ```
   Example:
   - Line 42: Expected "test" not to be called (but it is)
   - Line 55: Arithmetic operator swap: + to - survives
   ```

3. **Add test cases**: Edit test file to catch escaped mutation
   ```typescript
   // Example: If operator + to - escapes
   it('detects addition vs subtraction', () => {
     expect(sum([5, 5])).toBe(10);  // Catches 5-5=0
     expect(sum([10, 3])).toBe(13); // Catches 10-3=7
   });
   ```

4. **Re-run tests**:
   ```bash
   npm run test:run -- tests/unit/lib/utils/
   ```

5. **Re-run mutation**:
   ```bash
   npm run mutation:run -- stryker-batch-N.config.json
   ```

6. **Check score**: Target ≥80%
   ```bash
   grep "Mutation score" coverage/mutation-report/batch-N/*.json
   ```

7. **If still failing** (after 2 attempts):
   - Escalate to team lead
   - Consider documenting as acceptable escape
   - See "Acceptable Escapes" section below

### Scenario 2: Tests Become Flaky (Intermittent Failures)

**Problem**: `npm run test:run` passes sometimes, fails others

**Diagnosis**:
```bash
# Run tests multiple times
for i in {1..5}; do npm run test:run 2>&1 | grep -E "(FAIL|PASS)"; done

# Check for timing issues
npm run test:run -- --reporter=verbose 2>&1 | grep -i "timeout\|retry"

# Check for setTimeout/fake timers
grep -r "setTimeout\|vi.useFakeTimers" tests/unit/
```

**Fixes**:
- **Timing**: Add `--testTimeout 10000` to vitest config
- **Async**: Use `await vi.runAllTimersAsync()` before assertions
- **Race conditions**: Add explicit `await` before checking state
- **Global state**: Clear mocks between tests: `vi.clearAllMocks()`

```typescript
// BAD: Flaky
it('should load data', () => {
  fetchUser();
  expect(user).toBeDefined();
});

// GOOD: Deterministic
it('should load data', async () => {
  await fetchUser();
  expect(user).toBeDefined();
});
```

### Scenario 3: Stryker Process Hangs (>120 seconds)

**Problem**: `npm run mutation:run` stuck, eating CPU

**Emergency Stop**:
```bash
# Kill Stryker
pkill -f stryker
pkill -f vitest

# Check if processes still running
ps aux | grep -i stryker
ps aux | grep -i vitest
```

**Restart**:
```bash
# Clear npm cache
npm cache clean --force

# Re-run with smaller scope
npm run mutation:run -- stryker-batch-1.config.json --concurrency=1
```

**Prevention**:
- Set `concurrency: 2` (not 4+) in stryker config
- Set `timeoutMS: 60000` (60 seconds per test)
- Test on smaller subset first

---

## Post-Batch Issues

### Issue: CI Job Passes Locally but Fails in GitHub Actions

**Diagnosis**:
```bash
# Reproduce CI environment
npm ci  # (not npm install, which is what CI uses)
npm run test:run -- tests/unit/lib/utils/
npm run mutation:run -- stryker-batch-1.config.json
```

**Common Causes**:
- Node version mismatch: Check `.nvmrc` or `engines` in package.json
- Cache stale: `npm ci` not using lock file correctly
- Environment variables: Check `.env.example` against GitHub Secrets

**Fix**:
```bash
# Update lock file
rm package-lock.json
npm install
npm ci

# Re-commit and push
git add package-lock.json
git commit -m "fix: update npm dependencies"
git push
```

### Issue: Mutation Score Regression (Drop >5%)

**Example**: Batch 1 was 82%, new batch 2 is 76%

**Steps**:
1. **Identify regression**:
   ```bash
   # Compare reports
   diff coverage/mutation-report/batch-1/summary.json \
        coverage/mutation-report/batch-2/summary.json
   ```

2. **Find new escaped mutations**:
   - Check files modified since last batch
   - Focus on files with score drop >10%

3. **Determine root cause**:
   - Missing test coverage?
   - Library changed behavior?
   - Test became flaky?

4. **Fix**:
   ```bash
   # Add missing tests to catch escaped mutations
   # Then re-run
   npm run test:run && npm run mutation:run -- stryker-batch-N.config.json
   ```

5. **If can't reach 80%**:
   - Document escape scenario
   - Update MUTATION_TESTING.md escape table
   - Add comment in test file explaining mutation skip
   - Get code review approval

---

## Emergency Rollback Procedures

### Complete Rollback: Revert Entire Batch

**When to use**: Mutation test batch introduces widespread failures, can't fix quickly

**Steps**:
```bash
# 1. Find the batch merge commit
git log --oneline main | grep -i "mutation.*batch"
# Output: a1b2c3d "test: phase 1 utilities mutation testing (all files ≥80%)"

# 2. Revert the batch
git revert -m 1 a1b2c3d

# 3. Force push (if not merged to main yet)
git push origin mutation-test/batch-N --force

# OR

# 4. Create new rollback commit (if already on main)
git push origin main

# 5. Notify team
# @slack: "Rolled back batch N due to X. See GitHub #123"
```

### Selective Rollback: Revert Single File Test

**When to use**: One file failing, others passing

**Steps**:
```bash
# 1. Identify problematic file
git log --oneline tests/unit/ | head -5

# 2. Revert just that file
git checkout HEAD~1 -- tests/unit/lib/utils/problematic.test.ts

# 3. Commit
git add tests/unit/lib/utils/problematic.test.ts
git commit -m "Revert: problematic test cases for X"

# 4. Re-run other tests
npm run test:run -- tests/unit/lib/utils/ --exclude problematic.test.ts
```

### Pause CI Checks (Emergency Only)

**ONLY in emergency**, without approval:

```bash
# Temporarily disable branch protection
# In GitHub: Settings → Branch Protection → Dismiss stale PRs

# This allows merging without passing checks
# ⚠️  MUST re-enable immediately after fix!
```

**Re-enable**:
```bash
# In GitHub: Settings → Branch Protection → Require status checks
# Then run full test suite
npm run test:run
npm run mutation:run
```

---

## Post-Mortem Checklist

**After a failed batch or rollback**:

- [ ] **Root cause identified**: Document in issue
- [ ] **Fix merged**: Tests now passing
- [ ] **All 3 batches passing**: Run full suite
- [ ] **Baseline updated**: New baseline scores recorded
- [ ] **Team notified**: Slack message with resolution
- [ ] **Runbook updated**: Add new scenario if novel
- [ ] **Follow-up created**: Jira ticket to prevent recurrence

### Post-Mortem Template

```markdown
## Mutation Testing Rollback Post-Mortem

**Date**: 2026-03-10
**Batch**: 1 (Utilities)
**Duration of Incident**: 15 minutes

### What Happened
- Batch 1 tests had 2 escaped mutations in calculations.test.ts
- Could not reach 80% threshold

### Root Cause
- Missing test for operator mutation: + to -
- Only tested positive cases, not subtraction differentiation

### Resolution
- Added parametrized test: `expect(sum([1,2])).toBe(3)`
- Re-ran Stryker: Score improved from 72% to 84%

### Prevention
- Add checklist item: Test BOTH success and failure paths
- Code review: Require mutation score review before approval

### Action Items
- [ ] Update test writing guidelines (PR #123)
- [ ] Add mutation testing pre-commit hook (PR #124)
- [ ] Schedule team training on escapes (March 15)
```

---

## Acceptable Mutation Escapes

Documented escapes that are OK to ignore:

### 1. **Floating Point Rounding**
```typescript
// Escape: 0.1 + 0.2 === 0.30000000000000004
// Solution: Use toBeCloseTo()
expect(0.1 + 0.2).toBeCloseTo(0.3);
```

### 2. **Locale-Dependent Behavior**
```typescript
// Escape: Date formatting varies by system locale
// Solution: Test structure, not exact format
expect(formatDate(date)).toContain('2026');
```

### 3. **Library Mutations** (Outside our control)
```typescript
// Escape: dayjs internal behavior changed
// Solution: Document in MUTATION_TESTING.md
// Test what we control, not library internals
```

### 4. **Deterministic Randomness**
```typescript
// Escape: Math.random() mutations unkillable (no seed)
// Solution: Mock Math.random, or test outputs not randomness
vi.spyOn(Math, 'random').mockReturnValue(0.5);
```

**Document in code**:
```typescript
/**
 * NOTE: Mutation 42 escaped (floating point rounding).
 * This is acceptable because toBeCloseTo() prevents regressions.
 * See MUTATION_TESTING.md#acceptable-escapes
 */
it('should handle floating point', () => {
  expect(0.1 + 0.2).toBeCloseTo(0.3);
});
```

---

## Performance Troubleshooting

### Mutation Testing Takes >3 Minutes

**Diagnosis**:
```bash
# Check concurrency setting
grep "concurrency" stryker-batch-*.config.json

# Check test timeout
grep "timeoutMS" stryker-batch-*.config.json

# Profile which file is slow
time npm run test:run -- tests/unit/lib/utils/slow-file.test.ts
```

**Solutions**:
1. **Lower concurrency**: `"concurrency": 1` (slower but more stable)
2. **Increase timeout**: `"timeoutMS": 120000` (2 minutes per test)
3. **Split batch**: Run smaller subsets in parallel
4. **Optimize tests**: Remove sleep() calls, mock expensive operations

### Stryker Memory Leak (Process >2GB RAM)

**Diagnosis**:
```bash
# Monitor during run
watch -n 1 'ps aux | grep stryker | grep -v grep'

# Check for open file handles
lsof -p $(pgrep stryker)
```

**Fix**:
```bash
# Restart Node, clear cache
npm cache clean --force
killall node
npm run mutation:run -- stryker-batch-N.config.json
```

---

## Support & Escalation

### Tier 1: Common Issues (Self-Service)

- [ ] Test fails locally → Run with `--reporter=verbose`
- [ ] Score too low → Check HTML report for escaped mutations
- [ ] Flaky test → Add `await`, increase timeout, mock external calls

### Tier 2: Batch Issues (Team Lead)

- [ ] Mutation score stalled → Pair programming session
- [ ] Multiple files failing → Review test strategy
- [ ] Regression not fixable → Document escape, get approval

### Tier 3: Critical Issues (Platform Team)

- [ ] Stryker hanging/crashing → Upgrade Stryker version
- [ ] CI runner out of memory → Increase CI machine specs
- [ ] Tests break on merge → Investigate git conflicts

**Escalation Path**:
1. Post in #engineering-mutation-testing Slack channel
2. Tag @test-framework-lead
3. Create issue with:
   - Error message (full output)
   - Reproduction steps
   - Batch number and file name

---

## Key Contacts

| Role | Name | Slack | Email |
|------|------|-------|-------|
| **QA Lead** | TBD | @qa-lead | qa@consorcio.local |
| **DevOps** | TBD | @devops | devops@consorcio.local |
| **Frontend Lead** | TBD | @frontend | frontend@consorcio.local |

---

## Checklists for Common Tasks

### ✅ Before Merging Any Batch

```bash
# 1. All tests pass
npm run test:run

# 2. Mutation score ≥80%
npm run mutation:run -- stryker-batch-N.config.json

# 3. No regressions from baseline
# Manual check: Compare current score to /tmp/baseline-*.txt

# 4. Documentation updated
# Edit: MUTATION_TESTING.md with new batch results

# 5. Ready to commit
git add tests/ stryker-batch-N.config.json MUTATION_TESTING.md
git commit -m "test: phase N mutation testing (all files ≥80%)"
git push origin mutation-test/batch-N

# 6. Create PR and request review
# GitHub: New PR, add link to Stryker report
```

### ✅ Emergency Stop (Something On Fire)

```bash
# 1. Kill processes
pkill -9 stryker
pkill -9 vitest
pkill -9 node

# 2. Pause CI (if needed)
# GitHub: Settings → Branch Protection → Dismiss stale PRs

# 3. Rollback batch
git revert -m 1 <commit-hash>
git push origin main

# 4. Notify team
# Slack: @team "Emergency rollback of batch N"

# 5. Restore CI
# GitHub: Settings → Branch Protection → Require checks again
```

---

## References

- **Stryker Troubleshooting**: https://stryker-mutator.io/docs/stryker-js/troubleshooting/
- **Vitest Debugging**: https://vitest.dev/guide/debugging
- **GitHub Branch Protection**: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches
- **npm CI vs Install**: https://docs.npmjs.com/cli/v8/commands/npm-ci

---

**Last Updated**: 2026-03-09  
**Version**: 1.0  
**Maintained By**: Frontend QA Team
