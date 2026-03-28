---
name: pss-benchmark-agent
description: "PSS scoring engine benchmark protocol. Use when running benchmark competitions or improving scoring accuracy. Trigger with /pss-benchmark."
user-invocable: false
---

# PSS Benchmark Agent Documentation Protocol

## Overview

Benchmark protocol for Opus agents competing to improve the PSS scoring engine. Defines report structure, tracking format, sacred parameters, and anti-patterns.

## Prerequisites

- Access to the PSS scoring engine source: `rust/skill-suggester/src/main.rs`
- Benchmark files: `docs_dev/benchmark-v2-prompts-100.jsonl` and `docs_dev/benchmark-v2-gold-100.json`
- History file: `docs_dev/methodology-improvement-history.md`
- Built binary: `cargo build --release` in `rust/skill-suggester/`

## Instructions

1. Read `docs_dev/methodology-improvement-history.md` and current `main.rs`
2. Run baseline benchmark BEFORE changes and record score
3. Make one change at a time, benchmark after each
4. Revert regressions -- document rejected approaches
5. Write report to `docs_dev/worktree-{YOUR_ID}-report.md`
6. Write benchmark log to `docs_dev/worktree-{YOUR_ID}-benchmark-log.md`
7. Run `cargo test` and `cargo build --release`
8. Complete the Work Tracking Checklist

**Token savings**: When `mcp__plugin_llm-externalizer_llm-externalizer__code_task` is available, use it to analyze benchmark logs and scoring engine source instead of reading them into your context. Use `chat` with `answer_mode=0, max_retries=3` to compare multiple benchmark log snapshots in parallel. Keep Opus reasoning for the actual scoring algorithm changes — delegate log analysis to the externalizer.

## References

- [Report Format](references/report-format.md) -- mandatory sections 1-6
  - Section 1: Score Progression Table
  - Section 2: Change Details
    - Exact Code Diff
    - Formula / Algorithm Description
    - Why This Change (Hypothesis)
    - Per-Prompt Impact
    - Rejected Approach Details
  - Section 3: Structural Analysis
  - Section 4: Synonym Expansions Inventory
  - Section 5: Near-Miss Analysis
  - Section 6: Generalizability Self-Assessment
- [Anti-Patterns](references/anti-patterns.md) -- mistakes to avoid
  - DO NOT write vague descriptions
  - DO NOT skip rejected approaches
  - DO NOT describe algorithms in prose only
  - DO NOT forget the baseline
- [Sacred Parameters](references/sacred-parameters.md) -- do not change
  - Validated scoring parameters and regression history
- [Benchmark Tracking](references/benchmark-tracking.md) -- log format and rules
  - Benchmark Log Format
  - Rules
  - How to Run the Benchmark
- [Work Tracking Checklist](references/work-tracking-checklist.md) -- 5-phase checklist
  - Work tracker template for benchmark agents
- [Examples and Resources](references/examples-and-resources.md) -- commands and error handling
  - Output Files
  - Error Handling
  - Examples
  - Resources

### Checklist

Copy this checklist and track your progress:

- [ ] Read history and current main.rs
- [ ] Run baseline benchmark and record score
- [ ] Make changes one at a time, benchmark each
- [ ] Revert regressions and document rejected approaches
- [ ] Write report and benchmark log
- [ ] Run cargo test and cargo build --release

## Examples

```
cargo build --release && uv run scripts/pss_benchmark.py --binary target/release/pss
```

## Output

- `docs_dev/worktree-{AGENT_ID}-report.md` -- structured report with all mandatory sections
- `docs_dev/worktree-{AGENT_ID}-benchmark-log.md` -- per-prompt benchmark results (append-only)
- Modified `rust/skill-suggester/src/main.rs` -- with improvements to the scoring engine

## Error Handling

If the benchmark script fails or produces unexpected output, check `docs_dev/methodology-improvement-history.md` for known issues.

## Resources

- `rust/skill-suggester/src/main.rs` — scoring engine
- `docs_dev/benchmark-v2-prompts-100.jsonl` — prompts
- `docs_dev/benchmark-v2-gold-100.json` — gold standard
- `docs_dev/methodology-improvement-history.md` — history

