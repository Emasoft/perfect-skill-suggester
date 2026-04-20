# Examples and Resources

## Table of Contents

- [Output Files](#output-files)
- [Error Handling](#error-handling)
- [Examples](#examples)
- [Resources](#resources)

## Output Files

- `reports/worktree-{AGENT_ID}-report.md` -- structured report with all mandatory sections (reports/ is gitignored)
- `reports/worktree-{AGENT_ID}-benchmark-log.md` -- per-prompt benchmark results (append-only, gitignored)
- Modified `rust/skill-suggester/src/main.rs` -- with improvements to the scoring engine

## Error Handling

- If baseline benchmark fails to run: verify binary is built (`cargo build --release`)
- If benchmark score is 0: check that the CozoDB exists at `$CLAUDE_PLUGIN_DATA/pss-skill-index.db` (fallback `~/.claude/cache/pss-skill-index.db`); rebuild with `/pss-reindex-skills` if missing
- If cargo tests fail after changes: revert last change, re-run tests, diagnose the issue
- If a change causes catastrophic regression (>50 points): revert immediately, document in report

## Examples

Run baseline benchmark:
```bash
cd rust/skill-suggester && cargo build --release
uv run scripts/pss_agent_benchmark.py --prompts docs_dev/benchmark-v2-prompts-100.jsonl --gold docs_dev/benchmark-v2-gold-100.json
```

Document a change:
```markdown
### Change 1: Type filter fix (+36)
**BEFORE (line 6976):** `if type == "skill" || type == "agent"`
**AFTER (line 6976):** removed type filter, include all types
**Score:** 392 -> 428 (+36)
**Hypothesis:** Gold elements of type command/rule/mcp were being filtered out
```

## Resources

- `docs_dev/methodology-improvement-history.md` -- full history of all cycles and insights
- `docs_dev/baseline-per-prompt-results.txt` -- per-prompt results for current baseline
- `skills/pss-benchmark-agent/SKILL.md` -- main skill file (documentation protocol)
- `schemas/pss-agent-toml-schema.json` -- schema for agent.toml output files
