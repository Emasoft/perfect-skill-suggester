---
name: text-categorization-improver
description: "Iterative algorithm improvement via parallel experimentation and LLM-as-judge evaluation. Used by pss-agent-profiler. Trigger with /text-categorization-improver."
user-invocable: false
---

# Text Categorization Algorithm Improvement Protocol

## Overview

Systematic methodology for iteratively improving text categorization, scoring, or matching algorithms. Uses a 5-phase cycle: baseline measurement, qualitative LLM-as-judge evaluation, parallel experimentation across 3 git worktrees, benchmark-driven merge testing, and iteration until the target score is reached.

## Prerequisites

- A text categorization/scoring algorithm with measurable output
- A benchmark dataset (gold standard or ground truth)
- A quantitative scoring script
- Git repository with worktree support

## Instructions

1. **Phase 1**: Run quantitative benchmark to establish baseline score
2. **Phase 2**: Run qualitative LLM-as-judge evaluation on failure cases
3. **Phase 3**: Spawn 3 parallel researcher agents in separate git worktrees
4. **Phase 4**: Benchmark each worktree, merge the winner, verify no regressions
5. **Phase 5**: Repeat from Phase 1 until target score is reached

### Checklist

Copy this checklist and track your progress through the protocol:

- [ ] Phase 1: Baseline Measurement
- [ ] Phase 2: Qualitative Evaluation (LLM-as-Judge)
- [ ] Phase 3: Parallel Experimentation (3 Worktrees)
- [ ] Phase 4: Benchmark & Merge Testing
- [ ] Phase 5: Next Iteration or Completion

## Output
See [Output, Error Handling, Examples & Resources](references/output-errors-examples.md) for expected output formats.

## Error Handling
See [Output, Error Handling, Examples & Resources](references/output-errors-examples.md) for error handling details.

## Examples

Input: Scoring algorithm achieving 65% accuracy on benchmark dataset
Output: After 3 improvement cycles, accuracy reaches 82%+ with documented changes per iteration

See [Output, Error Handling, Examples & Resources](references/output-errors-examples.md) for detailed usage examples.

## Resources
See [Output, Error Handling, Examples & Resources](references/output-errors-examples.md) for additional resources.

## Reference Documentation

- [Model Requirements](references/model-requirements.md)
  - Model tier table for cost-efficient agent roles
- [Phase 1: Baseline Measurement](references/phase1-baseline.md)
  - Step 1.1: Run Quantitative Benchmark
  - Step 1.2: Initialize Progress Ledger
- [Phase 2: Qualitative Evaluation](references/phase2-qualitative-evaluation.md)
  - Step 2.1: Generate Evaluation Samples
  - Step 2.2: Spawn Evaluator Agents (Opus)
  - Step 2.3: Aggregate Findings (Opus)
  - Step 2.4: Update Progress Ledger
- [Phase 3: Parallel Experimentation](references/phase3-parallel-experimentation.md)
  - Step 3.1: Create 3 Git Worktrees
  - Step 3.2: Assign Experiment Focus
  - Step 3.3: Launch Researcher Agents (Opus)
  - Step 3.4: Collect Results
- [Phase 4: Benchmark & Merge](references/phase4-benchmark-merge.md)
  - Step 4.1: Identify Best Performers
  - Step 4.2: Test Additivity
  - Step 4.3: Verify No Regressions
  - Step 4.4: Update Progress Ledger
- [Phase 5: Iteration or Completion](references/phase5-iteration-completion.md)
  - Decision Gate
  - Iteration History
  - Final Merge
- [Anti-Patterns](references/anti-patterns.md)
  - Common experimental anti-patterns to avoid
- [Output, Errors, Examples & Resources](references/output-errors-examples.md)
  - Output
  - Error Handling
  - Examples
  - Resources
