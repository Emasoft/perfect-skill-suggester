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

## References

- [Commands Reference](references/pss-commands.md)
  - Understanding PSS command structure and invocation
    - Command naming conventions
    - Command invocation from Claude Code chat
  - Using /pss-status to check PSS configuration and index health
    - Basic /pss-status usage without arguments
    - Understanding /pss-status output: index statistics
    - Understanding /pss-status output: skill counts and categories
    - Interpreting /pss-status warnings and errors
  - Using /pss-reindex-skills to rebuild the skill index
    - When to reindex: detecting stale skill data
    - Running /pss-reindex-skills workflow step-by-step
    - Understanding reindex progress and completion messages
    - Verifying successful reindexing with /pss-status
  - Interpreting PSS skill suggestion output
    - Understanding confidence levels: HIGH, MEDIUM, LOW
    - Understanding evidence types: intent, keyword, co_usage
    - Reading the skill suggestion table format
    - Deciding when to activate suggested skills
  - Troubleshooting common PSS issues
    - PSS commands not found or not responding
    - Empty or missing skill suggestions
    - Index file errors or corruption
    - Reindexing failures and recovery
- [Suggestion Output](references/suggestion-output.md)
  - Reading This Table
  - Decision Framework
- [Common Workflows](references/common-workflows.md)
  - Workflow 1: First-Time PSS Setup
  - Workflow 2: Adding New Skills
  - Workflow 3: Debugging Missing Suggestions
- [Examples](references/examples.md)
  - Example 1: Testing Workflow
  - Example 2: First-Time Setup
  - Example 3: Debugging Missing Suggestions
- [Setup Checklist](references/setup-checklist.md)
  - PSS setup and verification checklist items

## Resources

- **Architecture**: `docs/PSS-ARCHITECTURE.md`
- **Companion skill**: pss-authoring (best practices and skill authoring tips)
