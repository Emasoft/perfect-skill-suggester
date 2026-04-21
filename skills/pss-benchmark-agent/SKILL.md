---
name: pss-benchmark-agent
description: "Use when running benchmark competitions or improving scoring accuracy. Used by pss-agent-profiler. Trigger with /pss-benchmark."
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

## Output location (MANDATORY)

Write every file to `$MAIN_ROOT/reports/pss-benchmark-agent/` — the **main
repo root's** reports folder, never the worktree's own. Both `./reports/`
and `./reports_dev/` are gitignored project-wide. Resolve the path with
this shell prologue at the start of your Bash section:

```bash
MAIN_ROOT="$(git worktree list | head -n1 | awk '{print $1}')"
REPORT_DIR="$MAIN_ROOT/reports/pss-benchmark-agent"
mkdir -p "$REPORT_DIR"
TIMESTAMP="$(date +%Y%m%d_%H%M%S%z)"   # local time + GMT offset, e.g. 20260421_183012+0200
REPORT_FILE="$REPORT_DIR/$TIMESTAMP-worktree-${AGENT_ID}-report.md"
LOG_FILE="$REPORT_DIR/$TIMESTAMP-worktree-${AGENT_ID}-benchmark-log.md"
```

## Instructions

1. Read `docs_dev/methodology-improvement-history.md` and current `main.rs`
2. Run baseline benchmark BEFORE changes and record score
3. Make one change at a time, benchmark after each
4. Revert regressions -- document rejected approaches
5. Write report to `$REPORT_FILE` (resolved via the prologue above)
6. Write benchmark log to `$LOG_FILE` (same prologue)
7. Run `cargo test` and `cargo build --release`
8. Complete the Work Tracking Checklist

**Token savings**: Use `mcp__plugin_llm-externalizer_llm-externalizer__code_task` (when available) to analyze benchmark logs and scoring engine source. Use `chat` to compare log snapshots in parallel. Reserve Opus reasoning for scoring algorithm changes.

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
cargo build --release && uv run scripts/pss_agent_benchmark.py --binary target/release/pss
```

## Output

- `$MAIN_ROOT/reports/pss-benchmark-agent/<TS±TZ>-worktree-{AGENT_ID}-report.md` -- structured report with all mandatory sections
- `$MAIN_ROOT/reports/pss-benchmark-agent/<TS±TZ>-worktree-{AGENT_ID}-benchmark-log.md` -- per-prompt benchmark results (append-only)
- Timestamp is local time with GMT offset (e.g. `20260421_183012+0200`). Both dirs are gitignored project-wide.
- Modified `rust/skill-suggester/src/main.rs` -- with improvements to the scoring engine

## Error Handling

If the benchmark script fails or produces unexpected output, check `docs_dev/methodology-improvement-history.md` for known issues.

## Resources

- `rust/skill-suggester/src/main.rs` — scoring engine
- `docs_dev/benchmark-v2-prompts-100.jsonl` — prompts
- `docs_dev/benchmark-v2-gold-100.json` — gold standard
- `docs_dev/methodology-improvement-history.md` — history

