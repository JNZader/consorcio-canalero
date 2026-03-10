#!/bin/bash
# Automatic mutation testing rollback script
# Triggered when mutation score drops >10% from baseline
# Usage: .github/mutation-rollback-script.sh <baseline-score> <current-score>

set -e

BASELINE_SCORE="${1:100}"
CURRENT_SCORE="${2}"

if [ -z "$CURRENT_SCORE" ]; then
    echo "Usage: $0 <baseline-score> <current-score>"
    echo "Example: $0 100 85"
    exit 1
fi

# Calculate the drop percentage
DROP=$(echo "$BASELINE_SCORE - $CURRENT_SCORE" | bc -l)
THRESHOLD=10

echo "=========================================="
echo "Mutation Testing Rollback Check"
echo "=========================================="
echo "Baseline score: ${BASELINE_SCORE}%"
echo "Current score:  ${CURRENT_SCORE}%"
echo "Drop:           ${DROP}%"
echo "Threshold:      ${THRESHOLD}%"
echo ""

# Check if drop exceeds threshold
if (( $(echo "$DROP > $THRESHOLD" | bc -l) )); then
    echo "🔴 CRITICAL: Score dropped ${DROP}% (threshold: ${THRESHOLD}%)"
    echo ""
    echo "Initiating automatic rollback..."
    echo ""
    
    # Get the last commit hash
    LAST_COMMIT=$(git rev-parse HEAD)
    LAST_AUTHOR=$(git log -1 --pretty=format:'%an')
    LAST_MESSAGE=$(git log -1 --pretty=format:'%s')
    
    echo "[ROLLBACK] Last commit: $LAST_COMMIT"
    echo "[ROLLBACK] Author:      $LAST_AUTHOR"
    echo "[ROLLBACK] Message:     $LAST_MESSAGE"
    echo ""
    
    # Verify we're on main or develop
    CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    if [ "$CURRENT_BRANCH" != "main" ] && [ "$CURRENT_BRANCH" != "develop" ]; then
        echo "❌ ERROR: Cannot rollback on branch '$CURRENT_BRANCH' (only main/develop)"
        exit 1
    fi
    
    # Perform rollback
    echo "[ROLLBACK] Reverting commit: $LAST_COMMIT"
    git revert --no-edit "$LAST_COMMIT" || {
        echo "❌ ERROR: Revert failed"
        exit 1
    }
    
    echo "[ROLLBACK] ✅ Revert successful"
    echo ""
    
    # Get the revert commit hash
    REVERT_COMMIT=$(git rev-parse HEAD)
    echo "[ROLLBACK] New revert commit: $REVERT_COMMIT"
    echo ""
    
    # Try to push if in CI/CD
    if [ -n "$GITHUB_TOKEN" ]; then
        echo "[ROLLBACK] Pushing revert to origin..."
        git push origin "$CURRENT_BRANCH" || {
            echo "⚠️  WARNING: Failed to push revert (you may need to push manually)"
            exit 1
        }
        echo "[ROLLBACK] ✅ Revert pushed to origin"
    else
        echo "[ROLLBACK] ℹ️  Not in CI environment; revert commit prepared but not pushed"
        echo "[ROLLBACK] To push manually, run: git push origin $CURRENT_BRANCH"
    fi
    
    # Create post-mortem issue (if GitHub CLI available)
    if command -v gh &> /dev/null; then
        echo ""
        echo "[ROLLBACK] Creating post-mortem issue..."
        
        ISSUE_TITLE="[post-mortem] Mutation regression - ${CURRENT_SCORE}% (rollback)"
        ISSUE_BODY="## Automatic Rollback Triggered

**Date**: $(date -u +'%Y-%m-%d %H:%M:%S UTC')
**Reason**: Mutation score dropped ${DROP}% (from ${BASELINE_SCORE}% to ${CURRENT_SCORE}%)
**Severity**: 🔴 Critical (>10% drop)

### Rolled Back Commit
- **Hash**: $LAST_COMMIT
- **Author**: $LAST_AUTHOR
- **Message**: $LAST_MESSAGE

### Revert Commit
- **Hash**: $REVERT_COMMIT

### Next Steps
1. Investigate why the mutation score dropped
2. See [MUTATION_ROLLBACK.md](../../docs/MUTATION_ROLLBACK.md) for post-mortem template
3. Fix tests to improve mutation score
4. Re-submit changes after testing

### Related Documentation
- [Mutation Testing Guide](../../docs/MUTATION_TESTING.md)
- [Rollback Procedures](../../docs/MUTATION_ROLLBACK.md)
"
        
        # Create issue (requires gh CLI and token)
        gh issue create --title "$ISSUE_TITLE" --body "$ISSUE_BODY" || {
            echo "⚠️  WARNING: Failed to create post-mortem issue"
        }
    fi
    
    echo ""
    echo "=========================================="
    echo "🔄 ROLLBACK COMPLETE"
    echo "=========================================="
    echo ""
    echo "✅ Automatic rollback finished successfully"
    echo ""
    echo "Next steps for developer:"
    echo "  1. Review the rollback: git log --oneline -5"
    echo "  2. Read: docs/MUTATION_ROLLBACK.md"
    echo "  3. Complete post-mortem in the created issue"
    echo "  4. Fix tests and re-submit changes"
    echo ""
    
    exit 0
    
elif (( $(echo "$DROP > 5" | bc -l) )); then
    echo "🟠 WARNING: Score dropped ${DROP}% (5-10% range)"
    echo "Manual review recommended before merge"
    exit 0
    
else
    echo "🟢 OK: Score drop is within acceptable range (<5%)"
    exit 0
fi
