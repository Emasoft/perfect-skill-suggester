---
name: pss-agent-toml
description: "Use when creating .agent.toml profiles. Trigger with /pss-setup-agent. AI selects elements, validates coherence."
argument-hint: "<agent-path> [--requirements PATH...]"
user-invocable: false
---

# PSS Agent TOML Profile Builder

## Overview

7-phase pipeline: gather context, score candidates (Rust binary), resolve conflicts, validate, review.

## Instructions

1. Run `/pss-setup-agent <agent-path>` (creates new profile)
2. Run `/pss-change-agent-profile <profile-path> <instructions>` (modify existing)
3. Review the generated `.agent.toml`

## Critical Rules

- NEVER rename skills/agents/commands from the agent definition
- `auto_skills:` frontmatter entries MUST stay in `[skills].primary`
- Non-coding agents: no LSP/linting/code-fix elements (code REVIEW is fine)

## Prerequisites

- Skill index at `~/.claude/cache/skill-index.json` (run `/pss-reindex-skills`)
- Rust binary at `$CLAUDE_PLUGIN_ROOT/src/skill-suggester/bin/<platform>`
- Agent `.md` file to profile

### Checklist

- [ ] Gather context, get candidates, evaluate each
- [ ] External elements, cross-type coherence
- [ ] Write, validate, verify, review `.agent.toml`

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
- [Review Protocol (Phase 7)](references/review-protocol.md)
  - Self-Review Checklist (Name Integrity, Auto-Skills Pinning, Non-Coding Filter, Coverage, Exclusion Quality, Fix Cycle)
  - Interactive Review Protocol (Activation, Summary Format, User Directives)
  - Search Integration (Find, Compare, Add from Results)
  - Re-validation Loop
  - Completion Checklist
- [Setup Command](references/pss-setup-command.md)
  - Usage Examples, How It Works
- [Example and Scoring](references/example-and-scoring.md)
  - Scoring Reference, Troubleshooting, Complete Example
- [Error Handling](references/error-handling.md)
  - Binary Not Found, Missing Skill Index, Validation Failure, Missing Env Var

## Examples

```
/pss-setup-agent agents/my-agent.md
/pss-setup-agent agents/my-agent.md --requirements docs/prd.md
/pss-change-agent-profile my-agent.agent.toml add websocket-handler
```

## Error Handling

- Missing index: run `/pss-reindex-skills`
- Binary not found: `uv run scripts/pss_build.py`
- Validation fails: fix errors, re-run

## Output

`.agent.toml` in `~/.claude/agents/`.

## Resources

- Schema: `${CLAUDE_PLUGIN_ROOT}/schemas/pss-agent-toml-schema.json`
- Validator: `${CLAUDE_PLUGIN_ROOT}/scripts/pss_validate_agent_toml.py`
- Verifier: `${CLAUDE_PLUGIN_ROOT}/scripts/pss_verify_profile.py`
