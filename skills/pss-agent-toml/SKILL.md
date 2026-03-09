---
name: pss-agent-toml
description: "Use when creating .agent.toml profiles for Claude Code agents. Trigger with /pss-setup-agent. AI selects elements across 6 types, validates coherence, produces conflict-free profiles."
argument-hint: "<agent-path> [--requirements PATH...]"
user-invocable: false
---

# PSS Agent TOML Profile Builder

## Overview

Builds `.agent.toml` profiles for Claude Code agents. AI evaluates scored candidates from the Rust binary, resolves conflicts, prunes redundancy, and assembles a validated profile.

## Instructions

1. Prepare the agent definition `.md` file
2. Ensure skill index exists (run `/pss-reindex-skills` if missing)
3. Run `/pss-setup-agent <agent-path>` for the full 6-phase pipeline
4. Review the generated `.agent.toml`

## Critical Rules

**Name Preservation**: NEVER rename skills, agents, or commands referenced in the agent definition. Preserve prefixes and names exactly as written (e.g., `amia-code-reviewer` stays `amia-code-reviewer`, never changed to match local index entries).

**Auto-Skills Pinning**: Skills listed in the agent's `auto_skills:` frontmatter MUST always appear in `[skills].primary`. They may NEVER be demoted to secondary or specialized.

**Non-Coding Agent Detection**: Orchestrators, coordinators, and managers that delegate all code work to sub-agents should NOT receive LSP servers, linting skills, code-fixing agents, or test-writing agents. Code REVIEW skills are fine (reviewing ≠ writing).

## Prerequisites

- Skill index: `~/.claude/cache/skill-index.json` (run `/pss-reindex-skills` if missing)
- Rust binary: `$CLAUDE_PLUGIN_ROOT/src/skill-suggester/bin/<platform>`
- Agent definition `.md` file

### Checklist

- [ ] Gather context, get candidates, evaluate each
- [ ] Add external elements, cross-type coherence check
- [ ] Write and validate `.agent.toml`

## References

- [AI Agent Principle](references/ai-agent-principle.md) -- Why AI reasoning is required
- [TOML Format](references/toml-format.md) -- Template, schema, validator
- [Workflow Phases 1-3](references/workflow-phases.md) -- Gather context, get candidates, evaluate
- [External Sources (Phase 4)](references/external-sources.md) -- Add elements from outside the index
- [Cross-Type Coherence (Phase 5)](references/cross-type-coherence.md) -- Overlap detection, resolution
- [Validation (Phase 6)](references/validation-protocol.md) -- Write, validate, clean up
- [Setup Command](references/pss-setup-command.md) -- Usage examples
- [Example and Scoring](references/example-and-scoring.md) -- Scoring reference, full example
- [Error Handling](references/error-handling.md) -- Binary not found, missing index, validation failure

## Examples

```
/pss-setup-agent agents/my-reviewer.md
/pss-setup-agent agents/my-reviewer.md --requirements docs/prd.md
```

## Error Handling

- Missing skill index: run `/pss-reindex-skills` first
- Binary not found: rebuild with `uv run scripts/pss_build.py`
- Validation fails: fix errors and re-run phase 6

## Output

Validated `.agent.toml` at `~/.claude/agents/<agent-name>.agent.toml`.
