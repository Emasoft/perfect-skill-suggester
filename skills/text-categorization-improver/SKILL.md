---
name: text-categorization-improver
description: "Systematic methodology for iteratively improving text categorization, scoring, or matching algorithms using parallel experimentation, qualitative LLM-as-judge evaluation, and merge testing."
user-invocable: false
---

# Text Categorization Algorithm Improvement Protocol

> Systematic methodology for iteratively improving text categorization, scoring, or matching algorithms using parallel experimentation, qualitative LLM-as-judge evaluation, and merge testing.

## Checklist

Copy this checklist and track your progress through the protocol:

- [ ] Phase 1: Baseline Measurement
- [ ] Phase 2: Qualitative Evaluation (LLM-as-Judge)
- [ ] Phase 3: Parallel Experimentation (3 Worktrees)
- [ ] Phase 4: Benchmark & Merge Testing
- [ ] Phase 5: Next Iteration or Completion

## Prerequisites

- A text categorization/scoring algorithm with measurable output
- A benchmark dataset (gold standard or ground truth)
- A quantitative scoring script
- Git repository with worktree support

## Model Requirements

This protocol uses a tiered model strategy for cost efficiency:

| Role | Model | Rationale |
|------|-------|-----------|
| Main orchestrator | **Opus** | Understands algorithm complexity, maintains progress history |
| 3 researcher agents (worktrees) | **Opus** | Each needs deep algorithm understanding for non-trivial changes |
| Benchmark entry creator | **Opus** | Needs domain expertise to create realistic test cases |
| Qualitative evaluators (LLM-as-judge) | **Opus** | Needs nuanced judgment to grade suggestions |
| Data collection & indexing | **Sonnet** | Mechanical extraction tasks |
| Verification & comparison | **Sonnet** | Comparing outputs against gold standard |
| Code formatting & linting | **Sonnet** | Automated cleanup |

## Phase 1: Baseline Measurement

### Step 1.1: Run Quantitative Benchmark
Run your scoring benchmark against the current algorithm version to establish a baseline score.

```
Record: baseline_score, per-category breakdown, timestamp
```

### Step 1.2: Initialize Progress Ledger
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

## Phase 2: Qualitative Evaluation (LLM-as-Judge)

### Step 2.1: Generate Evaluation Samples
Sample 15-25 random inputs from your dataset. For each:
1. Run the algorithm to produce its output
2. Write an evaluation task file containing:
   - The input (what was given to the algorithm)
   - The algorithm's output (what it produced)
   - Evaluation instructions (grade quality, identify errors, suggest fixes)

### Step 2.2: Spawn Evaluator Agents (Opus)
Launch 3-5 batch evaluator agents (Opus), each reviewing 5 samples:

Each evaluator grades each output on:
- **Quality grade** (A/B/C/D/F)
- **Irrelevant items** — what doesn't belong
- **Missing items** — what should be there but isn't
- **Ranking issues** — are top items actually best?
- **Root cause hypothesis** — WHY is the algorithm making this mistake?

### Step 2.3: Aggregate Findings (Opus)
Spawn an aggregation agent to synthesize all evaluator reports:
- Grade distribution across all samples
- Top 10 prioritized improvements with specific code changes
- Quick wins (implementable in <2 hours)
- Structural limitations that can't be fixed with parameter tuning
- Data quality issues in the training/index data

### Step 2.4: Update Progress Ledger
Record the qualitative findings, grade distribution, and identified improvements.

## Phase 3: Parallel Experimentation (3 Worktrees)

### Step 3.1: Create 3 Git Worktrees
```bash
git worktree add .claude/worktrees/exp-w1 -b improve/exp-w1
git worktree add .claude/worktrees/exp-w2 -b improve/exp-w2
git worktree add .claude/worktrees/exp-w3 -b improve/exp-w3
```

### Step 3.2: Assign Experiment Focus
Based on the qualitative evaluation findings, assign each worktree a different improvement strategy:

| Worktree | Focus | Example |
|----------|-------|---------|
| W1 | Quick wins / low-hanging fruit | Remove hard-coded biases, fix scoring bugs |
| W2 | Algorithmic improvements | Add name affinity boost, domain penalties |
| W3 | Structural changes | New scoring signals, different normalization |

**Important:** Each worktree targets DIFFERENT aspects of the algorithm. Changes must be non-conflicting so they can be merged later.

### Step 3.3: Launch Researcher Agents (Opus)
Spawn 3 background researcher agents (one per worktree). Each agent:
1. Reads the qualitative evaluation report for context
2. Reads the specific improvement tasks assigned to their worktree
3. Edits the algorithm source code
4. Builds and runs the benchmark
5. Iterates up to 5-7 times to maximize their score
6. Writes a report with: final score, all iterations tried, what worked and what didn't
7. Commits their changes

### Step 3.4: Collect Results
Wait for all 3 agents to complete. Record each worktree's score in the progress ledger.

## Phase 4: Benchmark & Merge Testing

### Step 4.1: Identify Best Performers
Rank worktrees by score improvement over baseline.

### Step 4.2: Test Additivity
Create a merge worktree and cherry-pick changes from the best-performing worktrees:

```bash
git worktree add .claude/worktrees/exp-merge -b improve/exp-merge
cd .claude/worktrees/exp-merge
git cherry-pick <w1-commit>
git cherry-pick <w2-commit>  # if compatible
```

Run the benchmark on the merged version. Compare:
- If merged > best individual → changes are additive, merge all
- If merged ≈ best individual → other changes are non-additive, keep only the best
- If merged < best individual → changes conflict, investigate

### Step 4.3: Verify No Regressions
Run ALL existing benchmarks (not just the one being optimized) to ensure no regressions in other algorithm modes.

### Step 4.4: Update Progress Ledger
Record merge results, additivity analysis, and final iteration score.

## Phase 5: Next Iteration or Completion

### Decision Gate
Compare current score to target:
- **Score >= target:** Protocol complete. Merge winning changes to main.
- **Score < target but improving:** Return to Phase 2 with the improved algorithm. The qualitative eval will find new issues to fix.
- **Score < target and plateau:** The remaining gap may be structural. Document limitations and escalate to the user.

### Iteration History
Each iteration through Phase 2-4 should show measurable progress. If 3 consecutive iterations show <5% improvement, the algorithm has likely hit a structural ceiling.

### Final Merge
When target is reached:
1. Cherry-pick winning worktree commits to main
2. Rebuild and verify all benchmarks pass
3. Clean up worktrees
4. Update the progress ledger with final results

## Anti-Patterns to Avoid

1. **Non-additive optimization:** When W2/W3 optimize against the original baseline instead of W1's improved version, their gains may not stack. Always inform later worktrees of earlier discoveries.

2. **Score overfitting:** Optimizing solely for the benchmark score. Use qualitative eval to catch cases where score improves but actual quality doesn't.

3. **Contamination loops:** When algorithm output is used as input to the next iteration without validation, errors compound.

4. **Ignoring structural limits:** No amount of parameter tuning can overcome missing data, wrong architecture, or fundamental algorithm limitations.

5. **Non-reproducible experiments:** Always use git commits, fixed random seeds, and recorded configurations so any experiment can be reproduced.
