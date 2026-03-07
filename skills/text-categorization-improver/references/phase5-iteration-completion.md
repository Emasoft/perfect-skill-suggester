# Phase 5: Next Iteration or Completion

## Decision Gate

Compare current score to target:
- **Score >= target:** Protocol complete. Merge winning changes to main.
- **Score < target but improving:** Return to Phase 2 with the improved algorithm. The qualitative eval will find new issues to fix.
- **Score < target and plateau:** The remaining gap may be structural. Document limitations and escalate to the user.

## Iteration History

Each iteration through Phase 2-4 should show measurable progress. If 3 consecutive iterations show <5% improvement, the algorithm has likely hit a structural ceiling.

## Final Merge

When target is reached:
1. Cherry-pick winning worktree commits to main
2. Rebuild and verify all benchmarks pass
3. Clean up worktrees
4. Update the progress ledger with final results
