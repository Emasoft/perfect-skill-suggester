# Execution Protocol

As of v3.0.0, the authoritative PSS index is the CozoDB store
(`pss-skill-index.db`). All statistics are read from it via the Rust binary's
`stats` / `health` / `count` subcommands.

## Step 1: Check Index Status

Use the Rust binary's `health` subcommand (exit 0 = populated, 1 = empty, 2 =
missing) and `stats` subcommand for headline numbers:

```bash
DATA_DIR="${CLAUDE_PLUGIN_DATA:-$HOME/.claude/cache}"
DB_FILE="${DATA_DIR}/pss-skill-index.db"
BINARY="${CLAUDE_PLUGIN_ROOT}/bin/pss-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"

if [ -f "$DB_FILE" ]; then
    echo "CozoDB index found: $DB_FILE"
    echo "Modified: $(stat -f '%Sm' -t '%Y-%m-%d %H:%M:%S' "$DB_FILE" 2>/dev/null || stat -c '%y' "$DB_FILE" 2>/dev/null | cut -d. -f1)"
    echo "Size: $(du -h "$DB_FILE" | cut -f1)"
    "$BINARY" health --verbose
else
    echo "No CozoDB index found. Run /pss-reindex-skills to create one."
fi
```

## Step 2: Parse Index Statistics

Call `pss stats --format table` (or `--format json` for structured output) to
extract:
- Total element count by type (skill, agent, command, rule, mcp, lsp)
- Counts per domain and category
- Oldest / newest installation timestamps (from `first_indexed_at`)
- Last reindex timestamp (from `last_updated_at`)

Internally the Rust binary reads the CozoDB relations; no JSON parsing required.

## Step 3: Display Status

Output in a clear, tabular format:

```
╔══════════════════════════════════════════════════════════════╗
║           PERFECT SKILL SUGGESTER STATUS                     ║
╠══════════════════════════════════════════════════════════════╣
║ Index Version:        3.0                                    ║
║ Generation Method:    rust-pipeline                          ║
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
uv run "${CLAUDE_PLUGIN_ROOT}/scripts/pss_test_e2e.py" --verbose
```

Report the test results to the user. The script tests the full PSS pipeline:
- Environment setup and binary detection
- Test skill creation
- Discovery pipeline (pss_discover.py)
- Rust enrichment (pss --pass1-batch)
- Merge queue (pss_merge_queue.py)
- Hook simulation with multiple prompts

If all phases pass, PSS is working correctly. If any phase fails, report the specific failure details.
