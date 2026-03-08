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

## Prerequisites

- **Skill index**: `~/.claude/cache/skill-index.json` -- run `/pss-reindex-skills` if missing
- **Rust binary**: `$CLAUDE_PLUGIN_ROOT/rust/skill-suggester/bin/<platform>`
- **Agent definition**: The `.md` file describing the agent to profile

## Workflow (6 Phases)

1. **Gather Context** -- Read agent `.md`, extract role/duties/tools/domains
2. **Get Candidates** -- Invoke Rust binary (`--agent-profile`)
3. **Evaluate Candidates** -- AI checks compatibility, redundancy, gaps
4. **Add External Elements** -- Search marketplace, GitHub, network
5. **Cross-Type Coherence** -- Validate no overlaps across 6 types
6. **Write and Validate** -- Assemble `.agent.toml`, validate until clean

### Checklist

Copy this checklist and track your progress:

- [ ] Gather agent context (role, duties, tools, domains)
- [ ] Get scored candidates from Rust binary
- [ ] Evaluate each candidate with AI reasoning
- [ ] Search for external elements
- [ ] Cross-type coherence check
- [ ] Write and validate `.agent.toml`

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
  - Phase 2: Get Candidates from the Index
  - Phase 3: Evaluate Each Candidate
- [External Sources (Phase 4)](references/external-sources.md)
- [Cross-Type Coherence (Phase 5)](references/cross-type-coherence.md)
  - Cross-type overlap detection
  - Coherence checklist
  - Resolution strategy
  - Autonomous vs Interactive mode
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

## Error Handling

- Missing skill index: run `/pss-reindex-skills` first
- Binary not found: rebuild with `uv run scripts/pss_build.py`
- Validation fails: fix reported errors and re-run phase 6

## Output

Validated `.agent.toml` written to `~/.claude/agents/<agent-name>.agent.toml`. Conforms to `${CLAUDE_PLUGIN_ROOT}/schemas/pss-agent-toml-schema.json` and passes `pss_validate_agent_toml.py` with exit code 0.

## Resources

- **Schema**: `${CLAUDE_PLUGIN_ROOT}/schemas/pss-agent-toml-schema.json`
- **Validator**: `${CLAUDE_PLUGIN_ROOT}/scripts/pss_validate_agent_toml.py`
- **Categories**: `${CLAUDE_PLUGIN_ROOT}/schemas/pss-categories.json`
- **Skill Index**: `~/.claude/cache/skill-index.json`
- **Rust Binary**: `${CLAUDE_PLUGIN_ROOT}/rust/skill-suggester/bin/pss-<platform>`
