# Benchmark Results Tracking

## Table of Contents

- [Benchmark Log Format](#benchmark-log-format)
- [Rules](#rules)
- [How to Run the Benchmark](#how-to-run-the-benchmark)

**CRITICAL: Use a SEPARATE file for per-prompt benchmark results.** The per-prompt tracking can grow to thousands of lines. Your report file must stay concise. Write benchmark results to:

`$MAIN_ROOT/reports/pss-benchmark-agent/<TS±TZ>-worktree-{AGENT_ID}-benchmark-log.md` (main-repo root; timestamp is `YYYYMMDD_HHMMSS±HHMM` local+offset)

## Benchmark Log Format

After EVERY benchmark run, append a section to the benchmark log:

```markdown
## Run #{N}: {description of change}
Timestamp: {ISO 8601}
Score: {score}/500 (delta: {+/-N} from previous)

### Per-Prompt Results (only changed prompts)
| Prompt | Before | After | Delta | Gold Skills Affected | Explanation |
|--------|--------|-------|-------|---------------------|-------------|
| P14 | 2/5 | 3/5 | +1 | axiom-swiftdata moved #14→#8 | whole-name match added 4000pts |
| P53 | 3/5 | 2/5 | -1 | ios-test-runner displaced gold test-simulator | gate penalty too lenient |

### Full Top-10 Dump (for prompts that changed)
#### P14 (before):
1. skill-a (0.85) 2. skill-b (0.77) ... 10. skill-j (0.52)
#### P14 (after):
1. skill-a (0.85) 2. skill-b (0.77) ... 8. axiom-swiftdata (0.64) ... 10. skill-k (0.50)
```

## Rules

- EVERY benchmark run gets logged, even if score didn't change (document "no change" with explanation)
- Only log prompts that CHANGED score -- don't dump all 100 every time
- For regressions: ALWAYS dump the full before/after top-10 so the next agent can diagnose
- The benchmark log is append-only -- never delete previous runs
- Your final REPORT references the benchmark log but doesn't duplicate it

## How to Run the Benchmark

Drive the benchmark from a short Python harness (illustration only — write it
to a `.py` file and run it with `uv run`, rather than copy-pasting it into a
shell). The procedure is:

1. Load the gold set `docs_dev/benchmark-v2-gold-100.json` and the prompt set
   `docs_dev/benchmark-v2-prompts-100.jsonl`.
2. For each prompt line, invoke the release binary
   `./target/release/skill-suggester` with the argv list
   `["--format", "json", "--top", "10"]`, feeding the prompt on stdin (an argv
   list, never a shell string — no shell interpolation occurs).
3. Parse the JSON result, collect the suggested element names, and count how
   many of that prompt's gold answers appear.
4. Accumulate hits across all prompts and print the running `P{i}: hits/5`
   line plus a final `Total: total_hits/500`.

The harness is a thin loop over the prompt file: read the gold/prompt files,
call the binary once per prompt with the fixed argv above, tally hits against
the gold answers, and report per-prompt and total scores.

Save the full output to the benchmark log, then update your work tracker.
