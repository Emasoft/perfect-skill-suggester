---
name: pss-status
description: "View Perfect Skill Suggester status, index statistics, and recent activations."
argument-hint: "[--verbose] [--test PROMPT] [--run-tests]"
allowed-tools: ["Bash", "Read"]
---

# PSS Status Command

View the current status of Perfect Skill Suggester including:
- Skill index statistics
- Cache age and validity
- Recent skill activations
- Matching performance metrics

## Usage

```
/pss-status [--verbose] [--test "PROMPT"] [--run-tests]
```

## Options

| Option | Description |
|--------|-------------|
| `--verbose` | Show detailed breakdown by source and type |
| `--test "PROMPT"` | Test matching against a sample prompt |
| `--run-tests` | Run end-to-end pipeline tests to verify PSS works correctly |

## Execution Protocol

### Step 1: Check Index Status

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

### Step 2: Parse Index Statistics

Read the index file and extract:
- Total skills count
- Skills by source (user, project, plugin)
- Skills by type (skill, agent, command)
- Total keywords count
- Index version and generation method

### Step 3: Display Status

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

### Step 4: Run Tests (if --run-tests)

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

## Test Mode

With `--test "PROMPT"`, simulate matching against the provided prompt:

```
/pss-status --test "help me set up github actions for ci"
```

Output:

```
╔══════════════════════════════════════════════════════════════╗
║                     TEST RESULTS                             ║
╠══════════════════════════════════════════════════════════════╣
║ Input Prompt:                                                ║
║   "help me set up github actions for ci"                    ║
║                                                              ║
║ Expanded Prompt (after synonym expansion):                   ║
║   "help me set up github actions for ci cicd deployment     ║
║    automation"                                               ║
╠══════════════════════════════════════════════════════════════╣
║                   MATCHED SKILLS                             ║
╠══════════════════════════════════════════════════════════════╣
║ Rank │ Skill             │ Score │ Conf.  │ Matches         ║
╠══════════════════════════════════════════════════════════════╣
║  1   │ devops-expert     │  18   │ HIGH   │ github, actions,║
║      │                   │       │        │ ci, set up ci   ║
║  2   │ github-workflow   │  14   │ HIGH   │ github, actions ║
║  3   │ ci-pipeline       │   9   │ MEDIUM │ ci, deployment  ║
║  4   │ automation-expert │   6   │ MEDIUM │ automation      ║
╚══════════════════════════════════════════════════════════════╝

Recommendation: devops-expert (HIGH confidence)
Commitment: "Before implementing: Evaluate YES/NO - Will this skill solve the user's actual problem?"
```

## Verbose Mode

With `--verbose`, show additional details:

- Full list of skills by source
- Keyword distribution histogram
- Top 10 most-activated skills (if activation logs exist)
- Synonym expansion patterns count

## Cache Validity

The index is considered:
- **VALID**: Less than 24 hours old
- **STALE**: More than 24 hours old (recommend reindex)
- **MISSING**: No index file found (must reindex)

## Related Commands

- `/pss-reindex-skills` - Regenerate the skill index with AI analysis

## Binary Status

The command also checks if the Rust binary is available for the detected platform:

### Supported Platforms

| Platform | Binary | Notes |
|----------|--------|-------|
| macOS Apple Silicon | `bin/pss-darwin-arm64` | Native build |
| macOS Intel | `bin/pss-darwin-x86_64` | Native build |
| Linux x86_64 | `bin/pss-linux-x86_64` | Static (musl) |
| Linux ARM64 | `bin/pss-linux-arm64` | Static (musl) |
| Windows x86_64 | `bin/pss-windows-x86_64.exe` | Cross-compiled |
| WASM | `bin/pss-wasm32.wasm` | For web sandboxes/containers |

### Example Output

```
╔══════════════════════════════════════════════════════════════╗
║                     BINARY STATUS                            ║
╠══════════════════════════════════════════════════════════════╣
║ Platform:             darwin-arm64                           ║
║ Binary:               bin/pss-darwin-arm64                   ║
║ Status:               ✓ AVAILABLE                            ║
║ Size:                 2.2 MB                                 ║
║ Expected Latency:     ~10ms                                  ║
╚══════════════════════════════════════════════════════════════╝
```
