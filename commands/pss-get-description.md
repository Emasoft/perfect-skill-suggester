---
name: pss-get-description
description: "Get element metadata (description, type, plugin) for skills, agents, commands, MCPs, rules"
argument-hint: "<name> [--batch] [--format json|table]"
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
  "plugin": "owner/plugin-name",
  "trigger": ["api", "rest", "endpoint"],
  "source_path": "/path/to/SKILL.md"
}
```

Fields:
- **name**: Element name as indexed
- **type**: skill | agent | command | hook | rule | mcp | lsp
- **description**: One-line description from frontmatter
- **plugin**: Plugin identifier (`null` for user-owned elements)
- **trigger**: Top keywords/activation terms (max 20)
- **source_path**: Absolute path to the element definition file

## Related Commands

- `/pss-status` - Show PSS index health and statistics
- `/pss-reindex-skills` - Rebuild the skill index
