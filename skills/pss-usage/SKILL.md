---
name: pss-usage
description: "Use when interpreting element suggestions, understanding confidence levels, or troubleshooting PSS. Trigger with /pss-status."
argument-hint: "skill-name or keyword to search"
user-invocable: false
---

# PSS Usage Skill

## Overview

Perfect Skill Suggester (PSS) automatically suggests relevant Claude Code elements (skills, agents, commands, rules, MCP servers, LSP servers) based on your prompts and agent profiles. PSS indexes 6 element types: skills, agents, commands, rules, MCP servers, and LSP servers.

**Hook mode** (normal prompting): Suggests skills and agents only.
**Agent-profile mode** (`/pss-setup-agent`): Recommends all 6 types in `.agent.toml` files.

## Prerequisites

- PSS plugin installed and enabled (verify with `/plugin list`)
- Skills available in `~/.claude/skills/` or project `.claude/skills/`
- Index built at least once via `/pss-reindex-skills`
- Write permissions to `~/.claude/cache/` directory

## Instructions

1. Check PSS health with `/pss-status`
2. Build or rebuild the skill index with `/pss-reindex-skills`
3. Use prompts naturally -- PSS suggests relevant skills with confidence levels (HIGH/MEDIUM/LOW)
4. Activate suggested skills with `/skill activate <skill-name>`
5. Reindex after installing or modifying skills by running `/pss-reindex-skills`

## When to Use

**Activate when:** user asks about skill suggestions, PSS functionality, reindexing, PSS status, or when suggestions appear empty/incorrect.

**Do NOT activate for:** general skill activation, writing skill content, or plugin development.

### Checklist

Copy this checklist and track your progress:

- [ ] Plugin installed and enabled (`/plugin list`)
- [ ] Index built (`/pss-reindex-skills`)
- [ ] Status verified (`/pss-status`)
- [ ] Test prompt produces suggestions

## Quick Reference

| Task | Command |
|------|---------|
| Check PSS health | `/pss-status` |
| Rebuild skill index | `/pss-reindex-skills` |
| Profile an agent | `/pss-setup-agent <agent-name>.md` |

## Error Handling

- **Commands not found**: Check plugin enabled with `/plugin list`
- **Empty suggestions**: Run `/pss-reindex-skills`
- **Index errors**: Delete `~/.claude/cache/skill-index.json` and reindex
- **Reindex failures**: Verify skills directories exist, check error message

## Output

PSS outputs a suggestion table with columns: Element Name, Type, Confidence (HIGH/MEDIUM/LOW), Evidence. Suggestions appear as a `systemMessage` notification: `⚡« Pss!... use: skill-name (type) »`.

## Examples

Input: User prompt "I need to set up Docker containers for my app"
Output: `⚡« Pss!... use: docker (skill), devops (skill) »`

- `/pss-status` -- displays index health, element count, last reindex time
- `/pss-reindex-skills` -- full regeneration of skill index from all sources
- See [Examples Reference](references/examples.md) for testing workflow and debugging scenarios

## References

- [Commands Reference](references/pss-commands.md) -- command structure, /pss-status usage, /pss-reindex-skills workflow, interpreting output, troubleshooting
- [Suggestion Output and Decision Framework](references/suggestion-output.md) -- reading suggestion tables, confidence levels, evidence types, activation decisions
- [Common Workflows](references/common-workflows.md) -- first-time setup, adding new skills, debugging missing suggestions
- [Examples](references/examples.md) -- testing workflow, first-time setup, debugging missing suggestions
- [Best Practices](references/pss-best-practices.md) -- when to reindex, interpreting suggestions, maintaining index health
- [Skill Authoring Tips](references/pss-skill-authoring-tips.md) -- making skills discoverable, improving suggestion quality, standard categories
- [Setup Checklist](references/setup-checklist.md) -- verify your PSS workflow is complete

## Resources

- **PSS Architecture**: See `docs/PSS-ARCHITECTURE.md` in PSS plugin directory
- **Plugin Validation**: See `docs/PLUGIN-VALIDATION.md` for validation procedures
- **Agent Skills Open Standard**: https://github.com/agentskills/agentskills
- **Claude Code Documentation**: https://platform.claude.com/llms.txt
