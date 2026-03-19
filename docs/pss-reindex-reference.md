# PSS Reindex Reference Documentation

This file contains reference information for the `/pss-reindex-skills` command.
Moved here to reduce token consumption when the command is loaded.

## Keyword Best Practices (Updated for PSS v3.0)

All keywords go into a single flat array. **PRIORITIZE multi-word phrases over single words.**

### Technology Names (ALWAYS use full names)
Tool and framework identifiers - use compound names:
- **GOOD**: `docker compose`, `kubernetes deployment`, `typescript strict mode`
- **GOOD**: `github actions workflow`, `gitlab ci/cd`, `jenkins pipeline`
- **AVOID**: `docker`, `k8s`, `ts` (too short/ambiguous)

### Action Phrases (NOT single verbs)
What the user wants to do - combine verb + context:
- **GOOD**: `deploy to production`, `run unit tests`, `review pull request`
- **GOOD**: `refactor legacy code`, `debug memory leak`, `migrate database`
- **AVOID**: `deploy`, `test`, `build` (too generic)

### Command Phrases (Natural language, 3+ words)
Full phrases users would type:
- **GOOD**: `fix failing build`, `set up ci/cd pipeline`, `configure test coverage`
- **GOOD**: `review this pull request`, `deploy to staging environment`
- **AVOID**: `fix build`, `run tests` (still too generic)

### Error Patterns (Specific messages)
Messages that indicate the element is needed:
- **GOOD**: `workflow run failed`, `typescript type error`, `connection refused error`
- **GOOD**: `permission denied ssh`, `module not found node`
- **AVOID**: `failed`, `error`, `denied` (match everything)

## PSS Enhanced Scoring Algorithm

PSS extends rio's matchCount with weighted scoring:

```rust
// Weighted scoring (from reliable skill-activator)
const WEIGHTS = {
    directory: 5,    // +5 - element in matching directory
    path: 4,         // +4 - prompt mentions file path
    intent: 4,       // +4 - action verb matches
    pattern: 3,      // +3 - regex pattern matches
    keyword: 2,      // +2 - simple keyword match
    first_match: 10, // +10 - first keyword bonus (from LimorAI)
    original_bonus: 3 // +3 - keyword in original prompt (not expanded)
};

// Confidence classification
const THRESHOLDS = {
    high: 12,    // AUTO-suggest with commitment reminder
    medium: 6,   // Show with evidence
    low: 0       // Include alternatives
};
```

## Synonym Expansion (from LimorAI)

Before matching, user prompts are expanded with 70+ synonym patterns:

```
"pr" → "github pull request"
"403" → "oauth2 authentication"
"db" → "database"
"ci" → "cicd deployment automation"
"test" → "testing"
```

This improves matching accuracy significantly.

## Pipeline Architecture

The reindex pipeline is a 3-stage Unix pipeline:

```
pss_discover.py → pss (Rust binary --pass1-batch) → pss_merge_queue.py
```

1. **Discover**: Scans all sources (user, project, plugin cache, marketplaces, MCP, LSP)
2. **Enrich**: Rust binary extracts keywords, intents, categories, languages, frameworks
3. **Merge**: Writes unified `skill-index.json` with atomic swap for crash safety

No AI agents are used. The pipeline completes in under 10 seconds for 10K+ elements.

## Cache Management

**PSS ALWAYS performs a FULL REINDEX from scratch. There are NO incremental updates.**

| Condition | Action |
|-----------|--------|
| **ANY invocation** | **Full reindex (discover + enrich + merge + atomic swap)** |

**WHY FULL REINDEX ONLY:**
1. Plugin versions change - old paths become invalid
2. Elements get renamed/moved - creates orphaned entries
3. Elements get deleted - phantom entries persist
4. Co-usage references stale elements - causes broken relationships
5. Partial updates create inconsistent state - impossible to debug

**CRASH SAFETY:** The old index is preserved during rebuild. The merge stage writes to a staging file first, then uses `os.replace()` for an atomic swap. If the pipeline crashes mid-rebuild, the previous index remains intact.

## Example Output

```
PSS Reindex Complete
====================
Elements: 9275
Index: ~/.claude/cache/skill-index.json (12M)
Pass 1: 9275 enriched
Backup: /tmp/pss-backup-20260310_143000
```

## Rust Skill Suggester

For maximum performance, a native Rust binary is bundled at `bin/`.

**No installation required** - Pre-built binaries for all major platforms are included with the plugin.

### Supported Platforms

| Platform | Binary |
|----------|--------|
| macOS Apple Silicon | `bin/pss-darwin-arm64` |
| macOS Intel | `bin/pss-darwin-x86_64` |
| Linux x86_64 | `bin/pss-linux-x86_64` |
| Linux ARM64 | `bin/pss-linux-arm64` |
| Windows x86_64 | `bin/pss-windows-x86_64.exe` |

### Performance

| Metric | Value |
|--------|-------|
| **Binary Size** | ~1MB |
| **Startup Time** | ~5-10ms |
| **Memory Usage** | ~2-3MB |

### How It Works

1. **Reads stdin** - JSON payload from Claude Code hook
2. **Loads index** - From `~/.claude/cache/skill-index.json`
3. **Expands synonyms** - 70+ patterns for better matching
4. **Applies weighted scoring** - directory, path, intent, pattern, keyword weights
5. **Classifies confidence** - HIGH (>=12), MEDIUM (6-11), LOW (<6)
6. **Returns JSON** - Skills-first ordering with commitment mechanism

### Testing

```bash
# Test with sample prompt (use your platform's binary)
echo '{"prompt":"help me set up github actions"}' | ./bin/pss-darwin-arm64
```

### Debugging

```bash
RUST_LOG=debug ./bin/pss-darwin-arm64 < payload.json
```

## Why AI-Analyzed Keywords Matter

| Aspect | Heuristic (old) | AI-Analyzed (PSS) |
|--------|-----------------|-------------------|
| Accuracy | ~70% | ~88%+ |
| Multi-word phrases | No | Yes |
| Error pattern detection | Limited | Full |
| Context understanding | None | Yes |
| Processing time | ~5 seconds | ~2-3 minutes |
| Requires API calls | No | Yes (Sonnet) |
| **Commitment mechanism** | No | **Yes** |
| **Confidence routing** | No | **Yes (3-tier)** |
