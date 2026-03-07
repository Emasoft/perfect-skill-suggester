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

You are an Opus agent competing to improve the PSS scoring engine. This skill defines the MANDATORY documentation standards for your work. Your report is the TRAINING DATA for future agents -- its quality directly determines whether the next cycle succeeds or fails.

1. Read `docs_dev/methodology-improvement-history.md` and the current `main.rs` to understand prior work
2. Run the baseline benchmark BEFORE making any changes and record the score
3. Make one change at a time, benchmark after each, and record in the Score Progression Table
4. Revert any change that causes regression -- document rejected approaches with full detail
5. Write your report to `docs_dev/worktree-{YOUR_ID}-report.md` with ALL mandatory sections
6. Write per-prompt benchmark results to `docs_dev/worktree-{YOUR_ID}-benchmark-log.md`
7. Run `cargo test` and `cargo build --release` to verify no regressions
8. Complete the Work Tracking Checklist before reporting done

## Report File

Write your report to: `docs_dev/worktree-{YOUR_ID}-report.md`

## Reference Documentation

All detailed protocol documentation is in the `references/` directory. Read each file before starting work.

- [Mandatory Report Sections (1-6)](references/report-format.md) -- score progression table, change details (diffs, formulas, hypotheses, per-prompt impact), structural analysis, synonym inventory, near-miss analysis, generalizability assessment
- [Anti-Patterns](references/anti-patterns.md) -- common mistakes that waste future agents' time
- [Sacred Parameters](references/sacred-parameters.md) -- parameters proven across 5 cycles that must NOT be changed
- [Benchmark Tracking](references/benchmark-tracking.md) -- separate benchmark log format, per-prompt result rules, how to run the benchmark script
- [Work Tracking Checklist](references/work-tracking-checklist.md) -- 5-phase checklist to copy into your report (setup, implementation, testing, report writing, verification)
- [Examples and Resources](references/examples-and-resources.md) -- example commands, change documentation format, error handling, resource file locations

## Output

- `docs_dev/worktree-{AGENT_ID}-report.md` -- structured report with all mandatory sections
- `docs_dev/worktree-{AGENT_ID}-benchmark-log.md` -- per-prompt benchmark results (append-only)
- Modified `rust/skill-suggester/src/main.rs` -- with improvements to the scoring engine
