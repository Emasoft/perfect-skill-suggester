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

Copy this checklist and track your progress:

- [ ] Gather context, get candidates, evaluate
- [ ] External elements, coherence check
- [ ] Write, validate, verify, review

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
  - Phase 2: Get Candidates (Two-Pass Scoring)
    - Pass 1: Agent-only scoring (baseline)
    - Pass 2: Requirements-only scoring (uses `pss-design-alignment`)
    - Search for additional candidates
  - Phase 3: Evaluate Each Candidate
    - Read the candidate's source file
    - Evaluate relevance
    - Detect mutual exclusivity
    - Check for obsolescence
    - Verify stack compatibility
    - Identify gaps
    - Prune redundancy
    - Cherry-pick from requirements (uses `pss-design-alignment`)
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
  - Self-Review Checklist
    - Check 1: Name Integrity
    - Check 2: Auto-Skills Pinning
    - Check 3: Non-Coding Agent Filter
    - Check 4: Coverage Analysis
    - Check 5: Exclusion Quality
    - Self-Review Fix Cycle
  - Interactive Review Protocol
    - Activation Conditions
    - Review Summary Format
    - User Directives
  - Search Integration
    - Finding Alternatives
    - Comparing Candidates
    - Adding from Search Results
  - Re-validation Loop
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
/pss-setup-agent agents/my-agent.md
/pss-change-agent-profile my-agent.agent.toml add websocket-handler
```

## Error Handling

- Missing index: `/pss-reindex-skills`
- Binary not found: `uv run scripts/pss_build.py`
- Validation: fix errors, re-run

## Output

`.agent.toml` in `~/.claude/agents/`.

## Resources

- `schemas/pss-agent-toml-schema.json`
- `scripts/pss_validate_agent_toml.py`
- `scripts/pss_verify_profile.py`
