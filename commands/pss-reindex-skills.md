---
name: pss-reindex-skills
description: "Rebuild the PSS skill index from scratch using the Rust enrichment pipeline"
argument-hint: "[--all-projects]"
allowed-tools: ["Bash", "Read"]
---

# PSS Reindex Skills Command

Rebuild the skill index using the deterministic Rust pipeline. Completes in under 10 seconds for 10K+ elements. No AI agents needed.

## Instructions

1. Resolve the plugin root and binary paths
2. Run the 3-step pipeline: discover, enrich, merge
3. Build the CozoDB index for fast scoring
4. Aggregate the domain registry
5. Report results

## Execution

Run this exact script. Replace `PLUGIN_ROOT` with the value of `$CLAUDE_PLUGIN_ROOT` if available, otherwise use the resolved plugin cache path.

```bash
#!/bin/bash
set -euo pipefail

# Resolve paths
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(find ~/.claude/plugins/cache/emasoft-plugins/perfect-skill-suggester -maxdepth 1 -type d | sort -V | tail -1)}"
SCRIPTS="$PLUGIN_ROOT/scripts"
ARCH=$(uname -m)
OS=$(uname -s)
if [ "$OS" = "Darwin" ] && [ "$ARCH" = "arm64" ]; then
    BINARY="$PLUGIN_ROOT/src/skill-suggester/bin/pss-darwin-arm64"
elif [ "$OS" = "Darwin" ] && [ "$ARCH" = "x86_64" ]; then
    BINARY="$PLUGIN_ROOT/src/skill-suggester/bin/pss-darwin-x86_64"
elif [ "$OS" = "Linux" ] && [ "$ARCH" = "x86_64" ]; then
    BINARY="$PLUGIN_ROOT/src/skill-suggester/bin/pss-linux-x86_64"
elif [ "$OS" = "Linux" ] && [ "$ARCH" = "aarch64" ]; then
    BINARY="$PLUGIN_ROOT/src/skill-suggester/bin/pss-linux-arm64"
else
    echo "ERROR: Unsupported platform: $OS/$ARCH"; exit 1
fi

# Verify binary
if [ ! -x "$BINARY" ]; then
    echo "ERROR: Binary not found or not executable: $BINARY"; exit 1
fi

# Step 1: Back up old index
BACKUP_DIR="$(python3 -c 'import tempfile; print(tempfile.gettempdir())')/pss-backup-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
[ -f ~/.claude/cache/skill-index.json ] && cp ~/.claude/cache/skill-index.json "$BACKUP_DIR/"
[ -f ~/.claude/cache/skill-index.db ] && cp ~/.claude/cache/skill-index.db "$BACKUP_DIR/"
rm -f ~/.claude/cache/skill-index.json ~/.claude/cache/skill-index.db ~/.claude/cache/skill-checklist.md

# Step 2: Discover + Enrich + Merge (the core pipeline)
DISCOVER_FLAGS="--jsonl --all-projects"
python3 "$SCRIPTS/pss_discover.py" $DISCOVER_FLAGS 2>/tmp/pss-discover-warnings.txt \
  | "$BINARY" --pass1-batch 2>/tmp/pss-pass1-stats.txt \
  | python3 "$SCRIPTS/pss_merge_queue.py" --batch-stdin 2>&1

# Step 3: Build CozoDB index for fast scoring
"$BINARY" --build-db 2>&1

# Step 4: Aggregate domain registry
python3 "$SCRIPTS/pss_aggregate_domains.py" 2>&1

# Step 5: Clean stale .pss files
python3 "$SCRIPTS/pss_cleanup.py" --all-projects 2>/dev/null || true

# Report
PASS1_STATS=$(cat /tmp/pss-pass1-stats.txt 2>/dev/null || echo "unknown")
INDEX_SIZE=$(ls -lh ~/.claude/cache/skill-index.json 2>/dev/null | awk '{print $5}')
ELEMENT_COUNT=$(python3 -c "import json; d=json.load(open('$HOME/.claude/cache/skill-index.json')); print(d.get('skill_count', len(d.get('skills', {}))))" 2>/dev/null || echo "?")
echo ""
echo "PSS Reindex Complete"
echo "===================="
echo "Elements: $ELEMENT_COUNT"
echo "Index: ~/.claude/cache/skill-index.json ($INDEX_SIZE)"
echo "Pass 1: $PASS1_STATS"
echo "Backup: $BACKUP_DIR"
```

## Error Handling

- **Binary not found**: Run `cargo build --release` in `$PLUGIN_ROOT/src/skill-suggester/` or check platform detection
- **Discovery warnings**: Check `/tmp/pss-discover-warnings.txt` for non-existent project paths
- **Merge errors**: Check that `~/.claude/cache/` directory exists and is writable
- **Restore from backup**: `cp $BACKUP_DIR/skill-index.json ~/.claude/cache/`

## Output

- `~/.claude/cache/skill-index.json` — enriched index with keywords, categories, intents, languages, frameworks
- `~/.claude/cache/pss-skill-index.db` — CozoDB index for fast pre-filtered scoring
- `~/.claude/cache/domain-registry.json` — aggregated domain gates

## Examples

```
/pss-reindex-skills
```

Output: `PSS Reindex Complete — Elements: 9275, Index: 12M, 7 seconds`

## Resources

- **Rust binary**: `$PLUGIN_ROOT/src/skill-suggester/bin/pss-<platform>`
- **Discovery script**: `$PLUGIN_ROOT/scripts/pss_discover.py`
- **Merge script**: `$PLUGIN_ROOT/scripts/pss_merge_queue.py`
- **Architecture**: `docs/PSS-ARCHITECTURE.md`
