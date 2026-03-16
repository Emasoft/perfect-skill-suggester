---
name: pss-usage
description: "Use when interpreting element suggestions, understanding confidence levels, or troubleshooting PSS. Trigger with /pss-status."
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

## Error Handling

- **Commands not found**: Check plugin enabled (`/plugin list`)
- **Empty suggestions**: Run `/pss-reindex-skills`
- **Index errors**: Delete `~/.claude/cache/skill-index.json`, reindex
- **Reindex failures**: Verify skills directories exist

## Output

Suggestion table with: Element Name, Type, Confidence (HIGH/MEDIUM/LOW), Evidence. Notification: `⚡« Pss!... use: skill-name (type) »`.

## Examples

Input: User prompt "I need to set up Docker containers for my app"
Output: `⚡« Pss!... use: docker (skill), devops (skill) »`

- `/pss-status` -- displays index health, element count, last reindex time
- `/pss-reindex-skills` -- full regeneration of skill index from all sources
- `/pss-get-description react` -- lightweight metadata lookup for any indexed element
- `/pss-setup-agent path/to/agent.md` -- generate `.agent.toml` profile for an agent
- `/pss-change-agent-profile path/to/file.agent.toml` -- modify a profile with natural language
- `/pss-add-to-index path/to/SKILL.md` -- add a new element to the index

## References

- [Commands Reference](references/pss-commands.md) -- command structure, /pss-status, /pss-reindex-skills, suggestion output interpretation, troubleshooting
- [Suggestion Output](references/suggestion-output.md) -- reading the table, decision framework
- [Common Workflows](references/common-workflows.md) -- first-time setup, adding skills, debugging missing suggestions
- [Examples](references/examples.md) -- testing, setup, debugging examples
- [Setup Checklist](references/setup-checklist.md) -- setup and verification checklist

## Resources

- **Architecture**: `docs/PSS-ARCHITECTURE.md`
- **Companion skill**: pss-authoring (best practices and skill authoring tips)
