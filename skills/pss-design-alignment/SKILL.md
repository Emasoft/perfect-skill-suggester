---
name: pss-design-alignment
description: "Use when augmenting an .agent.toml with project requirements. Trigger with /pss-change-agent-profile --requirements. Scores design docs, cherry-picks elements matching the agent's specialization."
argument-hint: "<agent.toml> --requirements <design-doc.md>"
user-invocable: false
---

# PSS Design Requirement Alignment

## Overview

Takes an existing `.agent.toml` (or baseline candidate pool) and a project requirements/design document, scores the design doc through the Rust binary, then cherry-picks only the elements that match the agent's specialization. Prevents project-level elements from leaking into agents that don't need them.

## Instructions

1. Receive an existing `.agent.toml` profile (baseline from `pss-agent-toml`)
2. Score the requirements document through the Rust binary (separate pass)
3. Cherry-pick elements matching the agent's specialization
4. Merge into the profile, verify, validate

## Critical Rules

- **Separate scoring**: Requirements MUST be scored in a separate binary invocation from the agent definition. Never mix them into one descriptor.
- **Specialization filter**: Every requirements-derived candidate must be individually evaluated against the agent's role, domain, and duties before adding.
- **Tier placement**: Cherry-picked elements go to secondary or specialized tier only. Primary tier is reserved for agent-intrinsic skills.
- **No leaking**: A database agent working on a shopping site does NOT get frontend/payments/UI skills. Only database-related elements from the requirements pass through.

## Prerequisites

- Existing `.agent.toml` profile (from `pss-agent-toml` / `/pss-setup-agent`)
- Requirements/design document (`.md` file describing the project)
- Skill index at `~/.claude/cache/skill-index.json`
- Rust binary at `$CLAUDE_PLUGIN_ROOT/src/skill-suggester/bin/<platform>`

### Checklist

Copy this checklist and track your progress:

- [ ] Requirements scored separately (Pass 2)
- [ ] Each candidate filtered by agent specialization
- [ ] Cherry-picked elements merged, verified, validated

## References

- [Scoring Protocol](references/scoring-protocol.md)
  - Requirements Descriptor Format
  - Binary Invocation
  - Output Format
  - Scoring Checklist
- [Specialization Filter](references/specialization-filter.md)
  - Domain Overlap Check
  - Duty Matching
  - Practical Usage Test
  - Filter Decision Table
  - Examples by Agent Type
  - Cherry-Pick Checklist
- [Merge Protocol](references/merge-protocol.md)
  - Deduplication
  - Tier Placement Rules
  - Exclusion Documentation
  - Verification and Validation
  - Merge Checklist

## Examples

```
# Used internally by pss-agent-profiler when --requirements is provided
# Pass 1 (pss-agent-toml): baseline profile from agent.md
# Pass 2 (pss-design-alignment): augment with project-specific elements

# Also used by pss-change-agent-profile to re-align with new requirements
/pss-change-agent-profile my-agent.agent.toml --requirements docs/prd.md
```

## Error Handling

- No requirements provided: skip (this skill is only needed when requirements exist)
- Requirements file not found: `[FAILED] Requirements file not found: <path>`
- Binary fails on requirements: `[FAILED] Binary error on requirements scoring: <stderr>`
- Zero cherry-picked elements: normal (agent's specialization may not overlap with requirements)

## Output

Updated `.agent.toml` with cherry-picked elements merged into secondary/specialized tiers and rejected candidates documented in `[skills.excluded]`.

## Resources

- `scripts/pss_verify_profile.py` — element verification (anti-hallucination)
- `scripts/pss_validate_agent_toml.py` — structural validation
- `schemas/pss-agent-toml-schema.json` — TOML schema
