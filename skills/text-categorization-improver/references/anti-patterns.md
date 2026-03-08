# Anti-Patterns to Avoid

## Table of Contents

- Common experimental anti-patterns to avoid

## Anti-Patterns

1. **Non-additive optimization:** When W2/W3 optimize against the original baseline instead of W1's improved version, their gains may not stack. Always inform later worktrees of earlier discoveries.

2. **Score overfitting:** Optimizing solely for the benchmark score. Use qualitative eval to catch cases where score improves but actual quality doesn't.

3. **Contamination loops:** When algorithm output is used as input to the next iteration without validation, errors compound.

4. **Ignoring structural limits:** No amount of parameter tuning can overcome missing data, wrong architecture, or fundamental algorithm limitations.

5. **Non-reproducible experiments:** Always use git commits, fixed random seeds, and recorded configurations so any experiment can be reproduced.
