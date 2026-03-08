# Phase 4: Benchmark & Merge Testing

## Table of Contents

- [Step 4.1: Identify Best Performers](#step-41-identify-best-performers)
- [Step 4.2: Test Additivity](#step-42-test-additivity)
- [Step 4.3: Verify No Regressions](#step-43-verify-no-regressions)
- [Step 4.4: Update Progress Ledger](#step-44-update-progress-ledger)

## Step 4.1: Identify Best Performers

Rank worktrees by score improvement over baseline.

## Step 4.2: Test Additivity

Create a merge worktree and cherry-pick changes from the best-performing worktrees:

```bash
git worktree add .claude/worktrees/exp-merge -b improve/exp-merge
cd .claude/worktrees/exp-merge
git cherry-pick <w1-commit>
git cherry-pick <w2-commit>  # if compatible
```

Run the benchmark on the merged version. Compare:
- If merged > best individual: changes are additive, merge all
- If merged = best individual: other changes are non-additive, keep only the best
- If merged < best individual: changes conflict, investigate

## Step 4.3: Verify No Regressions

Run ALL existing benchmarks (not just the one being optimized) to ensure no regressions in other algorithm modes.

## Step 4.4: Update Progress Ledger

Record merge results, additivity analysis, and final iteration score.
