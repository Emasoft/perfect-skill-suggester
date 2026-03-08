---
name: pss-benchmark-agent
description: "PSS scoring engine benchmark protocol. Use when running benchmark competitions or improving scoring accuracy. Trigger with /pss-benchmark."
user-invocable: false
---

# PSS Benchmark Agent Documentation Protocol

## Overview

Mandatory documentation protocol for Opus agents competing to improve the PSS scoring engine. Defines report structure, benchmark tracking format, sacred parameters, and anti-patterns. Ensures each agent's work becomes high-quality training data for the next competition cycle.

## Prerequisites

- Access to the PSS scoring engine source: `rust/skill-suggester/src/main.rs`
- Benchmark files: `docs_dev/benchmark-v2-prompts-100.jsonl` and `docs_dev/benchmark-v2-gold-100.json`
- History file: `docs_dev/methodology-improvement-history.md`
- Built binary: `cargo build --release` in `rust/skill-suggester/`

## Instructions

Mandatory documentation protocol for Opus agents competing to improve the PSS scoring engine. Reports are training data for future cycles.

1. Read `docs_dev/methodology-improvement-history.md` and current `main.rs`
2. Run baseline benchmark BEFORE changes and record score
3. Make one change at a time, benchmark after each
4. Revert regressions -- document rejected approaches
5. Write report to `docs_dev/worktree-{YOUR_ID}-report.md`
6. Write benchmark log to `docs_dev/worktree-{YOUR_ID}-benchmark-log.md`
7. Run `cargo test` and `cargo build --release`
8. Complete the Work Tracking Checklist

## References

- [Report Format](references/report-format.md) -- mandatory sections 1-6
  - Score Progression Table
  - Change Details
  - Structural Analysis
  - Synonym Expansions Inventory
  - Near-Miss Analysis
  - Generalizability Self-Assessment
- [Anti-Patterns](references/anti-patterns.md) -- mistakes to avoid
  - Vague descriptions
  - Skipping rejected approaches
  - Prose-only algorithms
  - Forgetting the baseline
- [Sacred Parameters](references/sacred-parameters.md) -- do not change
- [Benchmark Tracking](references/benchmark-tracking.md) -- log format and rules
  - Benchmark Log Format
  - Rules
  - How to Run the Benchmark
- [Work Tracking Checklist](references/work-tracking-checklist.md) -- 5-phase checklist
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

If the benchmark script fails or produces unexpected output, check `docs_dev/methodology-improvement-history.md` for known issues. See [Examples and Resources](references/examples-and-resources.md) for error handling and sample commands.

## Resources

- **Scoring engine**: `rust/skill-suggester/src/main.rs`
- **Benchmark prompts**: `docs_dev/benchmark-v2-prompts-100.jsonl`
- **Gold standard**: `docs_dev/benchmark-v2-gold-100.json`
- **History**: `docs_dev/methodology-improvement-history.md`
