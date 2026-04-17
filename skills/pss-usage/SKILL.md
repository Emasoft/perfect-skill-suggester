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

1. Check health (`/pss-status`); reindex (`/pss-reindex-skills`) if empty.
2. Use prompts naturally — PSS suggests skills with HIGH/MEDIUM/LOW confidence.
3. Activate via `/skill activate <name>`.
4. Reindex after installing or modifying skills.

### Checklist

Copy this checklist and track your progress:

- [ ] Plugin enabled (`/plugin list`)
- [ ] Index built (`/pss-reindex-skills`)
- [ ] Status verified (`/pss-status`)
- [ ] Test prompt produces suggestions

## Querying the Index Directly

Store: CozoDB at `$CLAUDE_PLUGIN_DATA/pss-skill-index.db` (fallback `~/.claude/cache/`). Slash commands: `/pss-search <q>`, `/pss-added-since <when>`. See [Querying the Index Directly](references/querying-the-index.md) for CLI + helpers.

## Error Handling

- **Commands not found** → check `/plugin list`
- **Empty suggestions** → `/pss-reindex-skills`
- **Index errors** → delete `$CLAUDE_PLUGIN_DATA/pss-skill-index.db` (fallback `~/.claude/cache/pss-skill-index.db`), then reindex
- **Legacy `skill-index.json`** → now generated on demand via `pss export --json`; CozoDB is canonical.

## Output

Suggestion table with: Element Name, Type, Confidence (HIGH/MEDIUM/LOW), Evidence. Notification: `⚡« Pss!... use: skill-name (type) »`.

## Examples

Prompt "I need Docker containers" → `⚡« Pss!... use: docker (skill) »`. Commands: `/pss-status`, `/pss-reindex-skills`, `/pss-get-description <n>`, `/pss-search <q>`, `/pss-added-since <w>`, `/pss-setup-agent <p>`, `/pss-change-agent-profile <p>`, `/pss-add-to-index <p>`.

## References

- [Commands Reference](references/pss-commands.md) -- command structure, /pss-status, /pss-reindex-skills, suggestion output interpretation, troubleshooting
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
  - Summary
- [Suggestion Output](references/suggestion-output.md) -- reading the table, decision framework
  - Reading This Table
  - Decision Framework
- [Common Workflows](references/common-workflows.md) -- first-time setup, adding skills, debugging missing suggestions
  - Workflow 1: First-Time PSS Setup
  - Workflow 2: Adding New Skills
  - Workflow 3: Debugging Missing Suggestions
- [Examples](references/examples.md) -- testing, setup, debugging examples
  - Example 1: Testing Workflow
  - Example 2: First-Time Setup
  - Example 3: Debugging Missing Suggestions
- [Setup Checklist](references/setup-checklist.md) -- setup and verification checklist
  - Checklist
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
