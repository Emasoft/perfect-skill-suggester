# Model Requirements

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
