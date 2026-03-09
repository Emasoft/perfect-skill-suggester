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

## References

- [AI Agent Principle](references/ai-agent-principle.md)
  - Why AI Reasoning is Required
  - What This Skill Teaches
  - Default Mode
- [TOML Format](references/toml-format.md)
  - Template
  - Schema and Validator
- [Workflow Phases 1-3](references/workflow-phases.md)
  - Phase 1: Gather Context
    - Read the agent definition file
    - Read requirements documents
    - Detect project languages from cwd
  - Phase 2: Get Candidates from the Index
    - Invoke the Rust binary
    - Search for additional candidates
  - Phase 3: Evaluate Each Candidate
    - Read the candidate's source file
    - Evaluate relevance
    - Detect mutual exclusivity
    - Check for obsolescence
    - Verify stack compatibility
    - Identify gaps
    - Prune redundancy
- [External Sources (Phase 4)](references/external-sources.md)
  - From a local file or folder
  - From an installed plugin
  - From a marketplace plugin (not installed)
  - From a GitHub/git repository URL
  - From a network shared folder
  - From a URL to a raw file
  - Phase 4 Completion Checklist
- [Cross-Type Coherence (Phase 5)](references/cross-type-coherence.md)
  - 5.1 Cross-type overlap detection
  - 5.2 Coherence checklist
  - 5.3 Resolution strategy
  - 5.4 Autonomous vs Interactive mode
- [Validation (Phase 6)](references/validation-protocol.md)
  - Write the .agent.toml file
  - Validate
  - Clean up
  - Completion Checklist
- [Setup Command](references/pss-setup-command.md)
  - Usage Examples
  - How It Works
- [Example and Scoring](references/example-and-scoring.md)
  - Scoring Reference
  - Troubleshooting
  - Complete Example
- [Error Handling](references/error-handling.md)
  - Binary Not Found
  - Missing Skill Index
  - Validation Failure
  - Missing Environment Variable

## Examples

```
/pss-setup-agent agents/my-reviewer.md
/pss-setup-agent agents/my-reviewer.md --requirements docs/prd.md
```

## Output

Validated `.agent.toml` at `~/.claude/agents/<agent-name>.agent.toml`.

## Resources

- **Schema**: `${CLAUDE_PLUGIN_ROOT}/schemas/pss-agent-toml-schema.json`
- **Validator**: `${CLAUDE_PLUGIN_ROOT}/scripts/pss_validate_agent_toml.py`
- **Skill Index**: `~/.claude/cache/skill-index.json`
