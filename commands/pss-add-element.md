---
name: pss-add-element
description: "Add a standalone element (skill, agent, command, hook, rule, MCP, LSP, output-style) to an existing plugin"
argument-hint: "--type <element-type> --source <path> --plugin <plugin-path> [--validate] [--force] [--dry-run]"
effort: low
allowed-tools: ["Bash", "Read", "Write", "Glob", "Grep"]
---

# PSS Add Element to Plugin

Add standalone elements to existing Claude Code plugins. Supports all element types: skills, agents, commands, hooks, rules, MCP servers, LSP servers, and output styles.

## Usage

```
/pss-add-element --type skill --source /path/to/skill-dir --plugin /path/to/plugin
/pss-add-element --type agent --source /path/to/agent.md --plugin /path/to/plugin
/pss-add-element --type hook --source /path/to/hooks.json --plugin /path/to/plugin --validate
```

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `--type` | Yes | Element type: `skill`, `agent`, `command`, `hook`, `rule`, `mcp-server`, `lsp-server`, `output-style` |
| `--source` | Yes | Path to the element source (directory for skills, .md file for agents/commands/rules/output-styles, .json for hooks/MCP/LSP) |
| `--plugin` | Yes | Path to the target plugin directory (must contain `.claude-plugin/plugin.json`) |
| `--validate` | No | Run CPV validation after adding the element |
| `--force` | No | Skip duplicate/incompatibility checks |
| `--dry-run` | No | Show what would be done without making changes |

## Element Type Details

### skill
- **Source**: Directory containing `SKILL.md` (may also contain `references/`, `scripts/`, `examples/`)
- **Destination**: `<plugin>/skills/<name>/`
- **Checks**: Duplicate skill name in frontmatter or directory name

### agent
- **Source**: `.md` file with agent frontmatter (`name`, `description`, `model`, etc.)
- **Destination**: `<plugin>/agents/<name>.md`
- **Checks**: Duplicate agent name in frontmatter or filename

### command
- **Source**: `.md` file with command frontmatter (`name`, `description`, `argument-hint`, etc.)
- **Destination**: `<plugin>/commands/<name>.md` (+ optional `<name>/` subdirectory with reference files)
- **Checks**: Duplicate command name in frontmatter or filename

### hook
- **Source**: `hooks.json` file with hook event entries
- **Destination**: Merged into `<plugin>/hooks/hooks.json`
- **Checks**: Duplicate hook commands on the same event type

### rule
- **Source**: `.md` file (rule content)
- **Destination**: `<plugin>/rules/<name>.md`
- **Checks**: Duplicate filename in rules directory
- **Note**: Rules are not a native plugin component. Use SessionStart/SessionEnd hooks to symlink them into `.claude/rules/` at runtime (see `/pss-make-plugin-from-profile` for the pattern).

### mcp-server
- **Source**: JSON file with fields: `name` (required), `command`, `args`, `env`, `cwd`, etc. The `name` becomes the key in `mcpServers`.
- **Destination**: Added to `<plugin>/.mcp.json` under `mcpServers.<name>`
- **Checks**: Duplicate server name in `.mcp.json`

### lsp-server
- **Source**: JSON file with fields: `name` (required — becomes the map key), `command` (required), `extensionToLanguage` (required), `args`, `transport`, `env`, `initializationOptions`, `settings`, `startupTimeout`, etc.
- **Destination**: Added to `<plugin>/.lsp.json` as a map entry `{ "<name>": { ...config } }`
- **Checks**: Duplicate server name in `.lsp.json`
- **Note**: The language server binary must be installed separately on each user's machine.

### output-style
- **Source**: Markdown (.md) file defining an output style
- **Destination**: Copied to `<plugin>/output-styles/<name>.md`
- **Checks**: Duplicate filename in `output-styles/` directory

## Execution

Run the Python script:

```bash
if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ]; then echo "ERROR: CLAUDE_PLUGIN_ROOT is not set." >&2; exit 1; fi
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
uv run python "$PLUGIN_ROOT/scripts/pss_add_element.py" \
  --plugin "<plugin-path>" \
  --type "<element-type>" \
  --source "<source-path>" \
  [--validate] [--force] [--dry-run]
```

## Post-Addition Steps

After adding an element:

1. **Verify**: Read the added file to confirm it was copied correctly
2. **Validate**: If `--validate` was not used, run `/cpv-validate-plugin <plugin-path>` manually
3. **Reindex**: Run `/pss-reindex-skills` to update the PSS skill index with the new element (needed for indexed types: skills, agents, commands, rules, MCP, LSP — not needed for hooks or output-styles which are not indexed)
4. **Reload**: Run `/reload-plugins` to activate the changes without restarting Claude Code

## Error Handling

The script exits with code 1 on:
- Invalid plugin path (no `.claude-plugin/plugin.json`)
- Source file/directory not found
- Duplicate element detected (use `--force` to override)
- Incompatible hook configuration
- Validation failure (when `--validate` is used)
