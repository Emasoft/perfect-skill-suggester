---
name: pss-add-to-index
description: "Index a single skill element"
argument-hint: "<element-name-or-path> [--plugin <plugin-path>] [--pass2]"
allowed-tools: ["Bash", "Read", "Write", "Glob", "Grep", "Task"]
---

# PSS Add to Index Command

Incrementally add or update a single element (skill, agent, command, rule, MCP, LSP) in the skill index WITHOUT requiring a full reindex.

## Usage

```
/pss-add-to-index <element-name-or-path>
/pss-add-to-index --plugin <plugin-path>
/pss-add-to-index --plugin <plugin-path> --pass2
```

| Argument | Description |
|----------|-------------|
| `<element-name-or-path>` | Element name (e.g., `senior-ios`) or path to definition file |
| `--plugin <path>` | Scan ALL elements in a plugin directory and add/update each |
| `--pass2` | Also run Pass 2 (co-usage analysis) for added elements |

## How It Works

### Single Element Mode

1. **Resolve element**: Find the element by name (lookup in index or scan known locations) or by direct path
2. **Check for duplicates**: If the element already exists in `~/.claude/cache/skill-index.json`, it will be UPDATED (not duplicated)
3. **Run Pass 1 scan**: Spawn a sonnet agent to read the element file and extract metadata (keywords, intents, category, etc.)
4. **Merge into index**: Add or update the element in the existing index using `pss_merge_queue.py`

### Plugin Mode (`--plugin`)

1. **Discover elements**: Scan the plugin directory for all element types:
   - `skills/*/SKILL.md` — skill definitions
   - `agents/*.md` — agent definitions
   - `commands/*.md` — command definitions
   - `rules/*.md` — rule definitions
   - Check plugin's `plugin.json`, `.mcp.json`, or `mcp.json` for MCP server configurations
2. **For MCP servers found in plugin configs**:
   - The discovery script (`pss_discover.py`) automatically builds descriptor `.md` files in the system temp dir
   - Each descriptor aggregates: MCP config + README content + tool names from source code
   - The sonnet agent reads the descriptor file (pointed to by the element's `path` field) for deep inspection
   - **NEVER activate or run the MCP server** — only read static files (README, source, config)
3. **For each element**: Run the single-element workflow (check duplicate → scan → merge)
4. **Report**: Show count of elements added/updated

## Element Discovery Locations

When given a name (not a path), search in order:
1. `~/.claude/skills/<name>/SKILL.md`
2. `~/.claude/agents/<name>.md`
3. `~/.claude/commands/<name>.md`
4. `~/.claude/rules/<name>.md`
5. `~/.claude/plugins/cache/**/skills/<name>/SKILL.md`
6. `~/.claude/plugins/cache/**/agents/<name>.md`
7. `~/.claude/plugins/cache/**/commands/<name>.md`
8. Current project: `.claude/skills/<name>/SKILL.md`, `.claude/agents/<name>.md`, etc.

## Reference

- [Execution Protocol](pss-add-to-index/execution-protocol.md) — Step-by-step implementation (Steps 1-7: load index, resolve, dedup, scan, merge, verify, pass2)

## Example

```
# Add a single skill by name
/pss-add-to-index senior-ios

# Add a skill by path
/pss-add-to-index ~/.claude/skills/my-new-skill/SKILL.md

# Add all elements from a plugin
/pss-add-to-index --plugin ~/.claude/plugins/cache/my-plugin/my-plugin/1.0.0/

# Add all elements from a plugin with co-usage analysis
/pss-add-to-index --plugin ~/.claude/plugins/cache/my-plugin/my-plugin/1.0.0/ --pass2
```

## Notes

- This command does NOT delete or reindex existing entries — it only adds new or updates existing
- For a full clean reindex, use `/pss-reindex-skills` instead
- The index `skill_count` field is automatically updated after merge
- Plugin elements are identified by their `plugin.json` manifest
