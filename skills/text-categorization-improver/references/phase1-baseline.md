# Phase 1: Baseline Measurement

## Step 1.1: Run Quantitative Benchmark

Run your scoring benchmark against the current algorithm version to establish a baseline score.

```
Record: baseline_score, per-category breakdown, timestamp
```

## Step 1.2: Initialize Progress Ledger

Create a markdown file to track the history of all iterations:

```markdown
# Algorithm Improvement Progress Ledger

## Iteration 0 (Baseline)
- **Score:** [baseline_score]
- **Breakdown:** [per-category scores]
- **Known issues:** [from prior analysis or initial observation]
```

The orchestrator (Opus) maintains this ledger across all iterations, documenting:
- Every score change (improvements AND regressions)
- Every failed approach (with root cause analysis)
- Every wrong turn (so researchers don't repeat mistakes)
- Structural limitations discovered
