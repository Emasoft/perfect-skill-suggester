# Benchmark Results Tracking

## Table of Contents

- [Benchmark Log Format](#benchmark-log-format)
- [Rules](#rules)
- [How to Run the Benchmark](#how-to-run-the-benchmark)

**CRITICAL: Use a SEPARATE file for per-prompt benchmark results.** The per-prompt tracking can grow to thousands of lines. Your report file must stay concise. Write benchmark results to:

`reports/worktree-{AGENT_ID}-benchmark-log.md`

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

```bash
# Run the benchmark and save per-prompt results
uv run python3 -c "
import subprocess, json, sys
BINARY = './target/release/skill-suggester'
PROMPTS = 'docs_dev/benchmark-v2-prompts-100.jsonl'
GOLD = 'docs_dev/benchmark-v2-gold-100.json'
with open(GOLD) as f: gold = json.load(f)
with open(PROMPTS) as f: prompts = [l.strip() for l in f if l.strip()]
total_hits = 0
for i, line in enumerate(prompts, 1):
    proc = subprocess.run([BINARY, '--format', 'json', '--top', '10'],
        input=line, capture_output=True, text=True, timeout=30)
    try:
        results = json.loads(proc.stdout)
        suggested = [r.get('name','') for r in results] if isinstance(results, list) else []
    except: suggested = []
    hits = sum(1 for s in gold.get(str(i), []) if s in suggested)
    total_hits += hits
    print(f'P{i}: {hits}/5 | suggested: {suggested[:5]}...')
print(f'\\nTotal: {total_hits}/500')
"
```

Save the full output to the benchmark log, then update your work tracker.
