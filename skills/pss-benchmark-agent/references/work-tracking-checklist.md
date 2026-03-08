# Work Tracking Checklist

## Table of Contents

- Work tracker template for benchmark agents

## Checklist Template

**Copy this checklist and track your progress.** Copy this entire block to the TOP of your report file immediately when you start working. Update it as you go. This is your task tracker -- it ensures you never skip documentation.

```markdown
# {AGENT_ID} Work Tracker

## Phase 1: Setup
- [ ] Read methodology-improvement-history.md (FULL file)
- [ ] Read baseline-per-prompt-results.txt (training set results)
- [ ] Read main.rs (FULL file, note line count)
- [ ] Run baseline benchmark (RECORD THE NUMBER before any changes)
- [ ] Baseline score: ___/500

## Phase 2: Implementation (update after EACH change)
- [ ] Change 1: _____________ | Score: ___/500 (delta: ___) | Kept/Reverted
- [ ] Change 2: _____________ | Score: ___/500 (delta: ___) | Kept/Reverted
- [ ] Change 3: _____________ | Score: ___/500 (delta: ___) | Kept/Reverted
- [ ] Change 4: _____________ | Score: ___/500 (delta: ___) | Kept/Reverted
- [ ] Change 5: _____________ | Score: ___/500 (delta: ___) | Kept/Reverted
- [ ] Change 6: _____________ | Score: ___/500 (delta: ___) | Kept/Reverted
- [ ] Change 7: _____________ | Score: ___/500 (delta: ___) | Kept/Reverted
- [ ] Change 8: _____________ | Score: ___/500 (delta: ___) | Kept/Reverted
(add more rows as needed)

## Phase 3: Testing & Build
- [ ] All cargo tests pass (record count: ___/___)
- [ ] cargo build --release succeeds
- [ ] Final benchmark score confirmed: ___/500

## Phase 4: Report Writing (MANDATORY -- do NOT skip)
- [ ] Section 1: Score progression table (ALL changes, kept AND reverted)
- [ ] Section 2: Change details for EACH change:
  - [ ] 2a. Exact code diff (before/after with line numbers)
  - [ ] 2b. Formula/algorithm with variable names
  - [ ] 2c. Hypothesis (why you expected this to help)
  - [ ] 2d. Per-prompt impact table (every prompt that changed)
  - [ ] 2e. Regression explanations (if any prompt lost points)
- [ ] Section 3: Rejected approaches (SAME detail level as kept changes)
- [ ] Section 4: Final parameter summary table (all values, all line numbers)
- [ ] Section 5: Synonym expansion inventory (if any added)
- [ ] Section 6: Near-miss analysis (gold skills at positions 11-15)
- [ ] Section 7: Generalizability self-assessment per change
- [ ] Section 8: Remaining 0-hit and 1-hit prompts with blocker analysis

## Phase 5: Final Verification
- [ ] Report written to docs_dev/worktree-{AGENT_ID}-report.md
- [ ] Report contains ALL sections above
- [ ] No section says "also tried several things" without details
- [ ] Every rejected approach has: exact values, score, per-prompt delta, explanation
- [ ] Every code change shows actual Rust code (not just prose)
```

**WHY THIS MATTERS:** Your report becomes the training data for the next 3 agents. If you write "changed a weight, didn't work" without saying WHICH weight, WHAT value, and WHAT score, the next agent will waste time trying the exact same thing. Every detail you skip costs the next cycle ~30 minutes of redundant work.
