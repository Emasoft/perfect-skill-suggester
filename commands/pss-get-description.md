---
name: pss-get-description
description: "Get element metadata (description, type, plugin) for skills, agents, commands, MCPs, rules"
argument-hint: "<name> [--batch] [--format json|table]"
effort: low
allowed-tools: ["Bash", "Read"]
---

# PSS Get Description Command

Retrieve lightweight metadata for any indexed element. Designed for tooltips, UI panels, and token-efficient lookups without reading entire skill/agent files.

## Usage

```
/pss-get-description <name>
/pss-get-description "name1,name2,name3" --batch
```

## Options

| Option | Description |
|--------|-------------|
| `<name>` | Element name or 13-char ID |
| `--batch` | Comma-separated names; returns JSON array with `null` for not-found |
| `--format json` | JSON output (default) |
| `--format table` | Human-readable table output |

## Reference

- [Execution Protocol](pss-get-description/execution-protocol.md)

## Output Schema (JSON)

```json
{
  "name": "api-development",
  "type": "skill",
  "description": "Guidelines for building clean, scalable APIs...",
  "source": "user",
  "source_path": "/path/to/SKILL.md",
  "scope": "user",
  "plugin": "owner/plugin-name",
  "trigger": ["api", "rest", "endpoint"]
}
```

Fields:
- **name**: Element name as indexed
- **type**: skill | agent | command | hook | rule | mcp | lsp
- **description**: One-line description from frontmatter
- **source**: Raw source field (e.g., `user`, `plugin:owner/name`, `marketplace:name`)
- **source_path**: Absolute path to the element definition file
- **scope**: Derived scope label: `user`, `project`, `installed`, or `marketplace`
- **plugin**: Plugin identifier (`null` for user-owned elements)
- **trigger**: Top keywords/activation terms (max 20)

### Ambiguous Results

When multiple entries share the same name from different sources, single mode returns:
```json
{
  "ambiguous": true,
  "query": "element-name",
  "matches": [...]
}
```
Use namespace-qualified names (`plugin-name:element-name`) or 13-char IDs to disambiguate.

## Related Commands

- `/pss-status` - Show PSS index health and statistics
- `/pss-reindex-skills` - Rebuild the skill index
