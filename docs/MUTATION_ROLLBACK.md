# Mutation Testing Rollback Procedures

Emergency procedures for handling mutation testing failures and regressions in CI/CD.

## Table of Contents
1. [When to Rollback](#when-to-rollback)
2. [How to Rollback](#how-to-rollback)
3. [Post-Mortem Template](#post-mortem-template)
4. [Escalation Path](#escalation-path)

---

## When to Rollback

### Automatic Rollback Triggers

Rollback procedures should be initiated when:

#### Backend (Cosmic-Ray)

| Condition | Severity | Action |
|-----------|----------|--------|
| Kill rate drops >10% from baseline (100% → <90%) | 🔴 Critical | Automatic rollback via CI script |
| Kill rate drops 5-10% from baseline (100% → 90-95%) | 🟠 High | Manual review + fix or rollback |
| Kill rate drops <5% from baseline (95-100%) | 🟡 Medium | Developer fixes tests, no rollback needed |
| Multiple modules affected | 🔴 Critical | Escalate immediately |

#### Frontend (Stryker) - When Phase 2 Implemented

| Condition | Severity | Action |
|-----------|----------|--------|
| Kill rate drops >10% from baseline (80% → <70%) | 🔴 Critical | Automatic rollback via CI script |
| Kill rate drops 5-10% from baseline (80% → 70-75%) | 🟠 High | Manual review + fix or rollback |
| Kill rate drops <5% from baseline (75-80%) | 🟡 Medium | Developer fixes tests, no rollback needed |
| Threshold broken (drops below 80%) | 🟠 High | Block merge; require fix |

### Decision Tree

```
Mutation test fails in CI
    ↓
Is score drop >10%?
    ├─ YES → Automatic rollback triggered
    │         See "How to Rollback" section
    │
    └─ NO (5-10% drop)
        ↓
        Is it on main branch (already merged)?
            ├─ YES → Team lead triggered rollback
            │         See "How to Rollback" section
            │
            └─ NO (on feature PR)
                ↓
                Developer fixes tests in same PR
                OR closes PR and tries different approach
```

---

## How to Rollback

### Automatic Rollback via CI (Production)

The rollback happens automatically when `.github/mutation-rollback-script.sh` detects a >10% score drop.

**In the GitHub Actions output, you'll see**:
```
[ROLLBACK] Mutation score dropped >10%: 100% → 85%
[ROLLBACK] Attempting automatic revert...
[ROLLBACK] Reverted commit: abc1234
[ROLLBACK] Re-running mutation tests to confirm...
[ROLLBACK] ✅ Score recovered: 100%
```

No manual action needed—the system handles it.

### Manual Rollback via Command Line

If you need to manually trigger a rollback (e.g., script failed):

#### Step 1: Identify the Problematic Commit

```bash
# Check recent commits
git log --oneline -20

# Example output:
# abc1234 (HEAD -> main) docs: improve error messages
# def5678 feat: add new validation logic  ← This caused the regression
# ghi9012 test: improve coverage
```

#### Step 2: Verify the Regression

```bash
# Locally run mutation tests on problematic commit
cd gee-backend
python3 scripts/cosmic_gate.py --min-kill-rate 1.0

# Output shows:
# Kill rate: 85.00% (required >= 100.00%)
# FAILED ❌
```

#### Step 3: Revert the Commit

```bash
# Revert the specific commit
git revert def5678  # The problematic commit

# This creates a NEW commit that undoes the changes
# The git log now shows:
# new1234 Revert "feat: add new validation logic"
# abc1234 docs: improve error messages
# def5678 feat: add new validation logic
```

#### Step 4: Re-run Tests to Verify Recovery

```bash
cd gee-backend
python3 scripts/cosmic_gate.py --min-kill-rate 1.0

# Should show:
# Kill rate: 100.00% (required >= 100.00%)
# PASSED ✅
```

#### Step 5: Push the Revert Commit

```bash
git push origin main

# Or push the branch if not on main yet
git push origin feature-branch
```

### Manual Rollback via GitHub UI

If you prefer the GitHub interface:

1. **Go to Pull Requests** → Find the PR that caused the regression
2. **Click "Conversation" tab**
3. **Click "Revert" button** (if commit is already merged)
   - GitHub creates a revert PR automatically
   - Review the revert PR
   - Merge the revert PR
4. **Or go to Commits** in the main branch
   - Find the problematic commit
   - Click the "..." menu
   - Select "Revert this commit"

---

## Post-Mortem Template

After a rollback occurs, complete this post-mortem within **24 hours** to prevent recurrence.

### Template

```markdown
# Mutation Testing Regression Post-Mortem

**Date**: [date of incident]
**Affected Branch**: [main/develop]
**Severity**: 🔴 Critical / 🟠 High / 🟡 Medium

## Summary
One sentence describing what happened.

## Timeline
- **[HH:MM UTC]** Developer merged PR without sufficient test coverage
- **[HH:MM UTC]** CI mutation test gate failed with <85% kill rate
- **[HH:MM UTC]** Automatic rollback triggered
- **[HH:MM UTC]** Post-mortem started

## Root Cause Analysis

### What Failed?
- Module: [reports.py / sugerencias.py / etc]
- Function: [function_name]
- Reason: [insufficient assertions / missing edge cases / etc]

### Why Did It Get Through?
- [ ] Tests passed locally but failed in CI (test environment difference)
- [ ] Tests weren't run before commit
- [ ] Tests were run but didn't catch the gap
- [ ] Reviewer missed the mutation score report
- [ ] Other: ________________________

### What Specifically Escaped?
Paste example mutation that survived:

```
File: app/api/v1/endpoints/reports.py:45
Mutation: Changed == to !=
Status: SURVIVED (tests didn't catch it)
```

## Impact Assessment
- **Duration**: [X] minutes from merge to rollback
- **Users Affected**: [None / Limited / Widespread]
- **Systems Affected**: [which services/endpoints]

## Prevention Strategy

### Immediate Actions (This PR)
- [ ] Add parametrized tests for the affected function
- [ ] Add boundary condition tests
- [ ] Add error case tests
- [ ] Use stronger assertions (specific values, not just truthiness)

### Follow-up Actions (Next Sprint)
- [ ] Code review checklist item: "Verify mutation score report before approving"
- [ ] Team training: "Reading Stryker reports and identifying gaps"
- [ ] Automate: [if applicable]

### Example Test Improvement

Before (weak):
```python
def test_calculate_fee():
    result = calculate_fee(100)
    assert result is not None  # Too weak!
```

After (strong):
```python
@pytest.mark.parametrize("input,expected", [
    (100, 90),
    (0, 0),
    (999.99, 899.991),
    (50, 45),
])
def test_calculate_fee(input, expected):
    assert calculate_fee(input) == pytest.approx(expected)  # Specific!
```

## Re-Submission Plan

Once the post-mortem is complete and tests are fixed:

1. Create feature branch: `git checkout -b fix/mutation-gap-reports`
2. Implement test improvements from "Prevention Strategy"
3. Run mutation tests locally: `python3 scripts/cosmic_gate.py --min-kill-rate 1.0`
4. Confirm score is back to 100% or above baseline
5. Create PR with title: `fix: improve mutation score for {module} - post-mortem #{issue}`
6. Link post-mortem issue in PR description
7. Ensure review includes mutation score verification

## Sign-Off

- [ ] Developer completed post-mortem: **[name]** on **[date]**
- [ ] Team lead reviewed: **[name]** on **[date]**
- [ ] Prevention strategy assigned: **[name]**
- [ ] Re-submission PR created: **[PR link]**

---

## Lessons Learned

What can we do better next time?

- [ ] Better pre-commit mutation test running
- [ ] Clearer code review guidelines
- [ ] More frequent mutation test runs (currently on each PR)
- [ ] Improved test templates/examples for team
- [ ] Other: ____________________
```

### How to Use This Template

1. Create a GitHub issue titled: `[post-mortem] Mutation regression - {module}`
2. Copy the template above into the issue
3. Fill in all sections
4. Assign to developer who made the change
5. Tag team lead for review
6. Link the issue in the revert commit message
7. Create follow-up PR with the prevention fixes

---

## Escalation Path

### Level 1: Automatic (>10% Drop)

**Trigger**: Mutation score drops >10%

**Action**:
1. `.github/mutation-rollback-script.sh` executes automatically
2. Problematic commit is reverted
3. Post-mortem issue is created and assigned to developer
4. Team lead is notified via Slack @devops-team

**Timeline**: < 5 minutes

### Level 2: Manual Review (5-10% Drop)

**Trigger**: Mutation score drops 5-10%

**Action**:
1. CI fails with warning message
2. Developer is notified in PR review
3. Options:
   - Developer fixes tests in the same PR
   - Developer closes PR and starts over with better approach
   - Developer requests exception (rare, needs lead approval)
4. No code merge until score recovers

**Timeline**: < 24 hours (before merge)

### Level 3: Team Lead Escalation

**Trigger**: Developer requests exception OR rollback necessary on main branch

**Action**:
1. Developer creates issue with justification
2. Team lead reviews and decides:
   - **Approve exception**: Allow temporary threshold reduction
   - **Reject exception**: Require developer to fix tests
   - **Approve rollback**: Trigger rollback if on main
3. If approved, add comment to issue: `@consorcio-bot approve-mutation-exception`
4. Developer creates follow-up issue to improve score

**Timeline**: < 4 hours (during business hours)

### Level 4: Critical Incident (Multiple Modules or >20% Drop)

**Trigger**: 
- Multiple modules affected simultaneously
- >20% score drop
- Production service impacted

**Action**:
1. **IMMEDIATE**: Team lead initiates incident response
2. Rollback is automatically triggered
3. Incident channel opened in Slack
4. Root cause analysis started
5. Follow-up: Code review and deploy process changes
6. Post-mortem completed within 24 hours

**Timeline**: < 15 minutes (severity: P1)

### Escalation Matrix

| Severity | Drop | Automated? | Lead Approval? | Timeline |
|----------|------|-----------|----------------|----------|
| Low | <5% | No | No | 24h (before merge) |
| Medium | 5-10% | No | No | 24h (before merge) |
| High | 10-20% | Yes ✅ | Yes | 4h |
| Critical | >20% | Yes ✅ | Yes | 15min |

---

## Prevention Checklist

To prevent regressions in the first place:

### Before Pushing Code

- [ ] Run mutation tests locally: `python3 scripts/cosmic_gate.py --min-kill-rate 1.0`
- [ ] Verify score matches or exceeds baseline
- [ ] If adding new code, add parametrized tests (not just happy path)
- [ ] Use specific assertions (`==` not `is not None`)
- [ ] Test edge cases: null/empty/max values

### Before Merging PR

- [ ] Code reviewer checks mutation score in CI
- [ ] If score dropped, ask developer why and get explanation
- [ ] If acceptable, approve with comment
- [ ] If unacceptable, request changes

### After Merging

- [ ] Monitor deployed service for anomalies
- [ ] No special action needed if mutation tests passed

---

## Tools & Commands

### Quick Command Reference

```bash
# Run mutation tests locally (backend)
cd gee-backend
python3 scripts/cosmic_gate.py --min-kill-rate 1.0

# Run mutation tests with strict threshold
python3 scripts/cosmic_gate.py --min-kill-rate 1.0

# View the cosmic-ray config
cat .cosmic-ray.toml

# Revert a specific commit
git revert <commit-hash>

# Check recent commits
git log --oneline -10

# View current branch status
git status
```

### Useful Files

| File | Purpose | Location |
|------|---------|----------|
| Cosmic-Ray Config | Backend mutation settings | `gee-backend/.cosmic-ray.toml` |
| Stryker Config | Frontend mutation settings | `consorcio-web/stryker.config.json` |
| Cosmic Gate Script | Runs mutation tests + enforces gates | `gee-backend/scripts/cosmic_gate.py` |
| Rollback Script | Automatic rollback on >10% drop | `.github/mutation-rollback-script.sh` |
| Mutation Workflow | CI/CD integration | `.github/workflows/mutation-testing.yml` |

---

## FAQ

**Q: I pushed code and got a mutation test failure. What should I do?**
A: 
1. Don't panic—it's caught before merge!
2. Review the failed mutations report
3. Add or improve tests to fix the score
4. Push the updated tests
5. CI will re-run and confirm pass/fail

**Q: Can I merge with a lower mutation score?**
A: Only with team lead exception approval. Create an issue with justification.

**Q: How long does rollback take?**
A: <5 minutes for automatic rollback, <15 minutes for manual.

**Q: What if rollback fails?**
A: Contact team lead immediately. A manual force-push may be required.

**Q: Do I need to create a post-mortem for every regression?**
A: Only if the regression reaches >5% drop. Minor regressions fixed in the same PR don't need post-mortems.

**Q: Can I disable mutation testing temporarily?**
A: No. Disable only with team lead approval + documented justification. Use exceptions instead.

---

## Related Documentation

- **[MUTATION_TESTING.md](MUTATION_TESTING.md)** - Complete mutation testing guide
- **[MUTATION_TESTING_BASELINE.md](MUTATION_TESTING_BASELINE.md)** - Baseline tracking
- **CI/CD Workflow**: `.github/workflows/mutation-testing.yml`
- **Rollback Script**: `.github/mutation-rollback-script.sh`

---

## Support

For escalations or questions about rollback:
1. Check this guide
2. Ask in #engineering-practices Slack
3. Escalate to team lead if decision needed

Last updated: 2026-03-10
