---
name: pss-usage
description: "Use when interpreting element suggestions or troubleshooting PSS. Used by pss-agent-profiler. Trigger with /pss-status."
argument-hint: "skill-name or keyword to search"
user-invocable: false
---

# PSS Usage Skill

## Overview

PSS automatically suggests relevant Claude Code elements (skills, agents, commands, rules, MCP servers, LSP servers) based on prompts and agent profiles.

**Hook mode**: Suggests skills and agents on normal prompts.
**Agent-profile mode** (`/pss-setup-agent`): Recommends all 6 types in `.agent.toml` files.

## Prerequisites

- PSS plugin installed and enabled (`/plugin list`)
- Skills in `~/.claude/skills/` or project `.claude/skills/`
- Index built via `/pss-reindex-skills`

## Instructions

1. Check PSS health: `/pss-status`
2. Build/rebuild skill index: `/pss-reindex-skills`
3. Use prompts naturally -- PSS suggests skills with confidence (HIGH/MEDIUM/LOW)
4. Activate suggestions: `/skill activate <skill-name>`
5. Reindex after installing or modifying skills

### Checklist

Copy this checklist and track your progress:

- [ ] Plugin installed and enabled (`/plugin list`)
- [ ] Index built (`/pss-reindex-skills`)
- [ ] Status verified (`/pss-status`)
- [ ] Test prompt produces suggestions

## Querying the Index Directly

The canonical PSS index is a CozoDB store (`pss-skill-index.db`) under `$CLAUDE_PLUGIN_DATA` (fallback `~/.claude/cache/`). Two slash commands wrap the most common queries; the Rust binary and Python helpers expose everything else.

- `/pss-search <query>` — keyword / full-text search
- `/pss-added-since <when>` — list entries installed since `<when>` (`1d`, `2w`, `2026-04-10`, RFC 3339)

See [Querying the Index Directly](references/querying-the-index.md) for the full list of Rust CLI subcommands, Python helpers in `scripts/pss_cozodb.py`, and quick recipes.

## Error Handling

- **Commands not found**: Check plugin enabled (`/plugin list`)
- **Empty suggestions**: Run `/pss-reindex-skills`
- **Index errors**: Delete `$CLAUDE_PLUGIN_DATA/pss-skill-index.db` (or `~/.claude/cache/pss-skill-index.db`), then reindex
- **Reindex failures**: Verify skills directories exist
- **Legacy `skill-index.json`**: Generated on demand via `pss export --json` for `git diff` workflows. The runtime hook no longer reads JSON — CozoDB is canonical.

## Output

Suggestion table with: Element Name, Type, Confidence (HIGH/MEDIUM/LOW), Evidence. Notification: `⚡« Pss!... use: skill-name (type) »`.

## Examples

Input: User prompt "I need to set up Docker containers for my app"
Output: `⚡« Pss!... use: docker (skill), devops (skill) »`

- `/pss-status` -- displays index health, element count, last reindex time
- `/pss-reindex-skills` -- full regeneration of skill index from all sources
- `/pss-get-description react` -- lightweight metadata lookup for any indexed element
- `/pss-search docker` -- keyword / full-text search across the CozoDB index
- `/pss-added-since 1d` -- list entries installed since the given time
- `/pss-setup-agent path/to/agent.md` -- generate `.agent.toml` profile for an agent
- `/pss-change-agent-profile path/to/file.agent.toml` -- modify a profile with natural language
- `/pss-add-to-index path/to/SKILL.md` -- add a new element to the index

## References

- [Commands Reference](references/pss-commands.md) -- command structure, /pss-status, /pss-reindex-skills, suggestion output interpretation, troubleshooting
- [Suggestion Output](references/suggestion-output.md) -- reading the table, decision framework
- [Common Workflows](references/common-workflows.md) -- first-time setup, adding skills, debugging missing suggestions
- [Examples](references/examples.md) -- testing, setup, debugging examples
- [Setup Checklist](references/setup-checklist.md) -- setup and verification checklist
- [Querying the Index Directly](references/querying-the-index.md)
  - Slash command entry points
  - Rust CLI subcommand reference
    - Overview and health
    - Single-entry lookup
    - Search and list
    - Timestamp-windowed queries
    - Export
  - Python helpers in `scripts/pss_cozodb.py`
    - Count and health
    - Timestamp-windowed lookups
    - Search helpers (seven dimensions)
    - Single-entry and full-scan
  - Quick recipes
  - JSON export for `git diff` workflows

## Resources

- **Architecture**: `docs/PSS-ARCHITECTURE.md`
- **Companion skill**: pss-authoring (best practices and skill authoring tips)
