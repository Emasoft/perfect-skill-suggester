---
name: pss-agent-toml
description: "Use when creating .agent.toml profiles for Claude Code agents. Trigger with /pss-setup-agent. AI selects elements across 6 types, validates coherence, produces conflict-free profiles."
argument-hint: "<agent-path> [--requirements PATH...]"
user-invocable: false
---

# PSS Agent TOML Profile Builder

An `.agent.toml` defines the complete configuration profile for a Claude Code agent: skills, sub-agents, slash commands, rules, MCP servers, and LSP servers. An AI agent evaluates scored candidates from the Rust binary, resolves conflicts, prunes redundancy, and assembles a validated profile.

## Prerequisites

- **Skill index**: `~/.claude/cache/skill-index.json` -- run `/pss-reindex-skills` if missing
- **Rust binary**: `$CLAUDE_PLUGIN_ROOT/rust/skill-suggester/bin/<platform>`
- **Agent definition**: The `.md` file describing the agent to profile

## Quick Start

```
/pss-setup-agent /path/to/agent.md --requirements /path/to/prd.md
```

## Workflow (6 Phases)

1. **Gather Context** -- Read agent `.md`, extract role/duties/tools/domains, read requirements, detect project languages
2. **Get Candidates** -- Invoke Rust binary (`--agent-profile`), search index for additional candidates
3. **Evaluate Candidates** -- AI reads each candidate's source, checks mutual exclusivity, stack compatibility, obsolescence, gaps, redundancy
4. **Add External Elements** -- Search for elements not in the index (local, marketplace, GitHub, network)
5. **Cross-Type Coherence** -- Validate no overlaps between skills, MCP, agents, commands, rules, LSP
6. **Write and Validate** -- Assemble `.agent.toml`, run validator, fix errors until exit code 0

## Reference Documentation

- [AI Agent Principle](references/ai-agent-principle.md) -- Why AI reasoning is mandatory for element selection
- [TOML Format](references/toml-format.md) -- Complete `.agent.toml` template with all sections
- [Workflow Phases 1-3](references/workflow-phases.md) -- Context gathering, candidate retrieval, AI evaluation with checklists
- [External Sources (Phase 4)](references/external-sources.md) -- Adding elements from local paths, plugins, GitHub, network
- [Cross-Type Coherence (Phase 5)](references/cross-type-coherence.md) -- Overlap detection, coherence checklist, resolution strategies
- [Validation Protocol (Phase 6)](references/validation-protocol.md) -- Writing, validating, and finalizing the `.agent.toml`
- [Setup Command](references/pss-setup-command.md) -- Using `/pss-setup-agent` to invoke the full pipeline
- [Example and Scoring](references/example-and-scoring.md) -- Scoring weights, tier thresholds, complete React example, troubleshooting
- [Error Handling](references/error-handling.md) -- Binary not found, missing index, validation failures

## Output

Validated `.agent.toml` written to `~/.claude/agents/<agent-name>.agent.toml`. Conforms to `${CLAUDE_PLUGIN_ROOT}/schemas/pss-agent-toml-schema.json` and passes `pss_validate_agent_toml.py` with exit code 0.

## Resources

- **Schema**: `${CLAUDE_PLUGIN_ROOT}/schemas/pss-agent-toml-schema.json`
- **Validator**: `${CLAUDE_PLUGIN_ROOT}/scripts/pss_validate_agent_toml.py`
- **Categories**: `${CLAUDE_PLUGIN_ROOT}/schemas/pss-categories.json`
- **Skill Index**: `~/.claude/cache/skill-index.json`
- **Rust Binary**: `${CLAUDE_PLUGIN_ROOT}/rust/skill-suggester/bin/pss-<platform>`
