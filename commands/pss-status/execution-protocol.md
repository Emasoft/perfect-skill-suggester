# Execution Protocol

## Step 1: Check Index Status

Read the skill index and display statistics:

```bash
INDEX_FILE="$HOME/.claude/cache/skill-index.json"
if [ -f "$INDEX_FILE" ]; then
    echo "Index found: $INDEX_FILE"
    echo "Modified: $(stat -f '%Sm' -t '%Y-%m-%d %H:%M:%S' "$INDEX_FILE" 2>/dev/null || stat -c '%y' "$INDEX_FILE" 2>/dev/null | cut -d. -f1)"
    echo "Size: $(du -h "$INDEX_FILE" | cut -f1)"
else
    echo "No skill index found. Run /pss-reindex-skills to create one."
fi
```

## Step 2: Parse Index Statistics

Read the index file and extract:
- Total skills count
- Skills by source (user, project, plugin)
- Skills by type (skill, agent, command)
- Total keywords count
- Index version and generation method

## Step 3: Display Status

Output in a clear, tabular format:

```
╔══════════════════════════════════════════════════════════════╗
║           PERFECT SKILL SUGGESTER STATUS                     ║
╠══════════════════════════════════════════════════════════════╣
║ Index Version:        3.0                                    ║
║ Generation Method:    ai-analyzed                            ║
║ Last Updated:         2026-01-18 06:00:00 UTC               ║
║ Cache Age:            2 hours (VALID)                        ║
╠══════════════════════════════════════════════════════════════╣
║                     SKILL STATISTICS                         ║
╠══════════════════════════════════════════════════════════════╣
║ Total Skills:         216                                    ║
║ Total Keywords:       2,592 (avg 12 per skill)              ║
╠══════════════════════════════════════════════════════════════╣
║ By Source:                                                   ║
║   • user              45                                     ║
║   • project           12                                     ║
║   • plugin            159                                    ║
╠══════════════════════════════════════════════════════════════╣
║ By Type:                                                     ║
║   • skill             180                                    ║
║   • agent             24                                     ║
║   • command           12                                     ║
╠══════════════════════════════════════════════════════════════╣
║                   SCORING CONFIGURATION                      ║
╠══════════════════════════════════════════════════════════════╣
║ Weights:                                                     ║
║   • directory         +5                                     ║
║   • path              +4                                     ║
║   • intent            +4                                     ║
║   • pattern           +3                                     ║
║   • keyword           +2                                     ║
║   • first_match       +10                                    ║
║   • original_bonus    +3                                     ║
╠══════════════════════════════════════════════════════════════╣
║ Confidence Thresholds:                                       ║
║   • HIGH              ≥12 (auto-suggest with commitment)     ║
║   • MEDIUM            6-11 (show with evidence)              ║
║   • LOW               <6 (include alternatives)              ║
╚══════════════════════════════════════════════════════════════╝
```

## Step 4: Run Tests (if --run-tests)

If the user passes `--run-tests`, execute the end-to-end pipeline test script:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pss_test_e2e.py" --verbose
```

Report the test results to the user. The script tests the full PSS pipeline:
- Environment setup and binary detection
- Test skill creation
- Pass 1 merge queue (keywords/metadata)
- Pass 2 merge queue (co-usage relationships)
- Rust binary direct scoring
- Hook simulation with multiple prompts

If all 6 phases pass, PSS is working correctly. If any phase fails, report the specific failure details.
