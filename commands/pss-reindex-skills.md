---
name: pss-reindex-skills
description: "Rebuild the PSS skill index from scratch using the Rust enrichment pipeline"
argument-hint: "[--exclude-inactive-plugins]"
allowed-tools: ["Bash", "Read"]
---

# PSS Reindex Skills Command

Rebuild the skill index using the deterministic Rust pipeline. Completes in under 10 seconds for 10K+ elements. No AI agents needed.

By default, indexes **all registered projects and all plugins** (every marketplace, every plugin). Use `--exclude-inactive-plugins` to skip plugins that the user has disabled in Claude Code settings.

## Instructions

1. Resolve the plugin root and binary paths
2. Run the 3-step pipeline: discover, enrich, merge
3. Build the CozoDB index for fast scoring
4. Aggregate the domain registry
5. Report results

## Execution

Run the Python reindex script. It resolves paths, runs the pipeline, builds the DB, and reports results.

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(uv run python3 -c "from pathlib import Path; dirs=[d for d in (Path.home()/'.claude/plugins/cache/emasoft-plugins/perfect-skill-suggester').iterdir() if d.is_dir()]; print(sorted(dirs,key=lambda p:tuple(int(x) for x in p.name.split('.')))[-1])")}"
uv run "$PLUGIN_ROOT/scripts/pss_reindex.py"
```

To exclude plugins the user has deactivated in Claude Code:

```bash
uv run "$PLUGIN_ROOT/scripts/pss_reindex.py" --exclude-inactive-plugins
```

This reads `enabledPlugins` from `~/.claude/settings.json` and skips any plugin where the value is `false`. Plugins not listed in `enabledPlugins` are included by default.

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
/pss-reindex-skills                           # All projects, all plugins (default)
/pss-reindex-skills --exclude-inactive-plugins  # Skip disabled plugins
```

Output: `PSS Reindex Complete — Elements: 9275, Index: 12M, 7 seconds`

## Resources

- **Rust binary**: `$PLUGIN_ROOT/src/skill-suggester/bin/pss-<platform>`
- **Discovery script**: `$PLUGIN_ROOT/scripts/pss_discover.py`
- **Merge script**: `$PLUGIN_ROOT/scripts/pss_merge_queue.py`
- **Architecture**: `docs/PSS-ARCHITECTURE.md`
