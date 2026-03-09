---
name: pss-agent-toml
description: "Use when creating .agent.toml profiles for agents. Trigger with /pss-setup-agent. AI selects elements, validates coherence, produces profiles."
argument-hint: "<agent-path> [--requirements PATH...]"
user-invocable: false
---

# PSS Agent TOML Profile Builder

## Overview

Builds `.agent.toml` profiles via 7-phase pipeline: gather context, score candidates (Rust binary), resolve conflicts, validate, review.

## Instructions

1. Ensure skill index exists (run `/pss-reindex-skills` if missing)
2. Run `/pss-setup-agent <agent-path>` for the full pipeline
3. Review the generated `.agent.toml`

## Critical Rules

**Name Preservation**: NEVER rename skills/agents/commands from the agent definition.

**Auto-Skills Pinning**: `auto_skills:` frontmatter entries MUST stay in `[skills].primary`, never demoted.

**Non-Coding Agent Detection**: Orchestrators that delegate code work should NOT receive LSP, linting, or code-fixing elements. Code REVIEW skills are fine.

## Prerequisites

- **Skill index**: `~/.claude/cache/skill-index.json` -- run `/pss-reindex-skills` if missing
- **Rust binary**: `$CLAUDE_PLUGIN_ROOT/src/skill-suggester/bin/<platform>`
- **Agent definition**: The `.md` file to profile

### Checklist

Copy this checklist and track your progress:

- [ ] Gather context, get candidates, evaluate each
- [ ] Add external elements, cross-type coherence check
- [ ] Write, validate, and review `.agent.toml`

## References

- [AI Agent Principle](references/ai-agent-principle.md)
  - Why AI Reasoning is Required
  - What This Skill Teaches
  - Default Mode
- [TOML Format](references/toml-format.md)
  - Template
  - Schema and Validator
- [Workflow Phases 1-3](references/workflow-phases.md)
  - Phase 1: Gather Context (read agent def, requirements, detect languages)
  - Phase 2: Get Candidates (invoke Rust binary, search for additional)
  - Phase 3: Evaluate Each Candidate (relevance, mutual exclusivity, obsolescence, stack compatibility, gaps, redundancy)
- [External Sources (Phase 4)](references/external-sources.md)
  - From local file/folder, installed plugin, marketplace plugin, GitHub URL, network folder, raw URL
  - Phase 4 Completion Checklist
- [Cross-Type Coherence (Phase 5)](references/cross-type-coherence.md)
  - Overlap detection, coherence checklist, resolution strategy, autonomous vs interactive mode
- [Validation (Phase 6)](references/validation-protocol.md)
  - Write .agent.toml, validate, clean up, completion checklist
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
/pss-setup-agent agents/my-reviewer.md
/pss-setup-agent agents/my-reviewer.md --requirements docs/prd.md
/pss-setup-agent agents/my-reviewer.md --interactive
```

## Error Handling

- Missing index: run `/pss-reindex-skills`
- Binary not found: `uv run scripts/pss_build.py`
- Validation fails: fix errors, re-run

## Output

`.agent.toml` at `~/.claude/agents/<agent-name>.agent.toml`.

## Resources

- **Schema**: `${CLAUDE_PLUGIN_ROOT}/schemas/pss-agent-toml-schema.json`
- **Validator**: `${CLAUDE_PLUGIN_ROOT}/scripts/pss_validate_agent_toml.py`
