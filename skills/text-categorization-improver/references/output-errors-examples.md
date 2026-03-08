# Output, Error Handling, Examples & Resources

## Table of Contents

- [Output](#output)
- [Error Handling](#error-handling)
- [Examples](#examples)
- [Resources](#resources)

## Output

- **Progress Ledger** (`progress-ledger.md`): Markdown file tracking every iteration's score, breakdown, qualitative findings, merge results, and failed approaches.
- **Evaluator Reports**: Per-sample quality grades (A-F), identified issues, and root cause hypotheses from LLM-as-judge evaluation.
- **Researcher Reports**: Per-worktree reports with final score, iterations tried, what worked and what failed.
- **Final merged algorithm**: The improved algorithm committed to main with all benchmarks passing.

## Error Handling

- **Benchmark script fails**: Verify the scoring script runs against the current algorithm before starting. Do not proceed to Phase 2 without a valid baseline score.
- **Worktree creation fails**: Ensure the git repository supports worktrees and no naming conflicts exist. Clean up stale worktrees with `git worktree prune`.
- **Merge conflicts**: If cherry-picking between worktrees produces conflicts, resolve manually and re-run the benchmark. Do not auto-resolve conflicts in algorithm logic.
- **Score regression after merge**: Revert to the best individual worktree result and investigate conflicting changes before retrying.
- **3 consecutive iterations with <5% improvement**: Stop iterating. The algorithm has likely hit a structural ceiling. Document limitations and escalate to the user.

## Examples

**Example 1: Improving a keyword-based skill matcher**
1. Baseline score: 62% accuracy on 200-entry benchmark
2. Qualitative eval reveals: keyword overlap scoring ignores synonyms, category penalties too aggressive
3. W1 fixes scoring bugs (+4%), W2 adds synonym expansion (+8%), W3 restructures normalization (+3%)
4. Merged result: 74% accuracy (changes are additive)
5. Second iteration targets remaining false positives, reaches 81%

**Example 2: Improving a document classifier**
1. Baseline F1 score: 0.71
2. LLM-as-judge finds: short documents misclassified, ambiguous categories conflated
3. W1 adds length normalization (+0.03), W2 refines category boundaries (+0.05), W3 tests ensemble approach (+0.02)
4. Merged W1+W2: F1 = 0.79 (W3 conflicts with W2, excluded)

## Resources

- Git worktree documentation: `git worktree --help`
- LLM-as-judge pattern: Use Opus-tier models for nuanced quality grading
- Benchmark design: Ensure gold-standard datasets cover edge cases and category boundaries
