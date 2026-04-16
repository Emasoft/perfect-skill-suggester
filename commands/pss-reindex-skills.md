---
name: pss-reindex-skills
description: "Full reindex of all 6 element types (skills, agents, commands, rules, MCP servers, LSP servers) using the deterministic Rust enrichment pipeline"
argument-hint: "[--exclude-inactive-plugins]"
effort: medium
allowed-tools: ["Bash", "Read"]
---

# PSS Reindex Skills Command

Rebuild the skill index using the deterministic Rust pipeline. Completes in under 10 seconds for 10K+ elements. No AI agents needed.

Indexes all **6 element types**: skills, agents, commands, rules, MCP servers, and LSP servers. By default, indexes **all registered projects and all plugins** (every marketplace, every plugin). Use `--exclude-inactive-plugins` to skip plugins that the user has disabled in Claude Code settings.

As of v3.0.0 CozoDB (`pss-skill-index.db`) is the single canonical store. Python writes the DB directly via `pycozo[embedded]` under an `fcntl` lock; the Rust `--build-db` flag has been removed. If you want a diffable JSON snapshot for code review, run `pss export --json` after reindexing.

## Instructions

1. Resolve the plugin root and binary paths
2. Run the 3-step pipeline via `pss_reindex.py` (orchestrates discover, enrich, merge)
3. `pss_merge_queue.py` writes enriched rows directly into CozoDB
4. Aggregate the domain registry
5. Report results

The Python script `pss_reindex.py` is the single entry point — it orchestrates the discovery (`pss_discover.py`), Rust enrichment (`pss --pass1-batch`), and merge-to-CozoDB (`pss_merge_queue.py`) steps internally.

## Execution

Run the Python reindex script. It resolves paths, runs the pipeline, builds the DB, and reports results.

```bash
if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ]; then echo "ERROR: CLAUDE_PLUGIN_ROOT is not set." >&2; exit 1; fi
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
uv run "$PLUGIN_ROOT/scripts/pss_reindex.py"
```

To exclude plugins the user has deactivated in Claude Code:

```bash
uv run "$PLUGIN_ROOT/scripts/pss_reindex.py" --exclude-inactive-plugins
```

This reads `enabledPlugins` from `~/.claude/settings.json` and skips any plugin where the value is `false`. Plugins not listed in `enabledPlugins` are included by default.

## Error Handling

- **Binary not found**: Run `cargo build --release` in `$PLUGIN_ROOT/rust/skill-suggester/` or check platform detection
- **Discovery warnings**: Check `/tmp/pss-discover-warnings.txt` for non-existent project paths
- **Merge errors**: Check that the data directory (`$CLAUDE_PLUGIN_DATA` or `~/.claude/cache/`) exists and is writable
- **Restore from backup**: The script creates backups in `/tmp/pss-backup-<timestamp>/` (CozoDB snapshot and, if present, legacy `skill-index.json`). Check the script output for the exact backup path.

## Output

Output is written to `$CLAUDE_PLUGIN_DATA` (CC v2.1.78+) or `~/.claude/cache/` as fallback:

- `pss-skill-index.db` — canonical CozoDB index (written by Python, read by the Rust hot path)
- `domain-registry.json` — aggregated domain gates
- `skill-index.json` — **not written automatically** in v3.0.0+. Run `$PLUGIN_ROOT/bin/pss-<platform> export --json` after reindex if you want a diffable snapshot.

## Examples

```
/pss-reindex-skills                           # All projects, all plugins (default)
/pss-reindex-skills --exclude-inactive-plugins  # Skip disabled plugins
```

Output: `PSS Reindex Complete — Elements: 9275, Index: 12M, 7 seconds`

## Resources

- **Orchestrator script**: `$PLUGIN_ROOT/scripts/pss_reindex.py`
- **Rust binary**: `$PLUGIN_ROOT/bin/pss-<platform>`
- **Discovery script**: `$PLUGIN_ROOT/scripts/pss_discover.py`
- **Merge script**: `$PLUGIN_ROOT/scripts/pss_merge_queue.py`
- **Architecture**: `$PLUGIN_ROOT/docs/PSS-ARCHITECTURE.md`
