---
name: pss-agent-toml
description: "Use when creating .agent.toml profiles. Trigger with /pss-setup-agent. Loaded by pss-agent-profiler. AI selects elements, validates coherence."
argument-hint: "<agent-path> [--requirements PATH...]"
user-invocable: false
---

# PSS Agent TOML Profile Builder

## Overview

7-phase pipeline: context, scoring (Rust binary), conflict resolution, validation, review.

## Instructions

1. Run `/pss-setup-agent <agent-path>` to create a new profile
2. Run `/pss-change-agent-profile <profile> <instructions>` to modify
3. Review the generated `.agent.toml` output
4. Validate with `uv run scripts/pss_validate_agent_toml.py <file>`

## Critical Rules

- NEVER rename skills/agents/commands from agent definition
- `auto_skills:` MUST stay in `[skills].primary`
- Non-coding agents: no LSP/linting/code-fix elements

## Prerequisites

- CozoDB skill index at `$CLAUDE_PLUGIN_DATA/pss-skill-index.db` (fallback `~/.claude/cache/pss-skill-index.db`)
- Rust binary at `$CLAUDE_PLUGIN_ROOT/bin/<platform>`

### Checklist

Copy this checklist and track your progress:

- [ ] Context, candidates, evaluate
- [ ] External elements, coherence
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
  - Phase 2: Get Candidates from the Index (Two-Pass Scoring)
    - Pass 1: Agent-only scoring (baseline profile)
    - Pass 2: Requirements-only scoring (project-level candidates)
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

### Profiler-agent procedures

Step-by-step procedures for the `pss-agent-profiler` agent, which keeps only the
workflow skeleton in its own definition.

- [Profiler Runtime](references/profiler-runtime.md)
  - Inputs Contract
  - Debug Output Protocol
  - Step 0: Index Rule Files
  - Step 1: Read and Analyze the Agent
  - Step 2: Read Requirements Documents
  - Step 3a: Pass 1 — Agent-Only Descriptor
  - Step 3b: Pass 2 — Requirements-Only Descriptor
  - Step 9: Clean Up and Report
  - Invocation Examples
  - Change Mode
  - Error Handling (Fail-Fast)
- [Profiler Post-Filtering](references/profiler-postfilter.md)
  - Entry IDs and CLI Tools
  - Token-Efficient Candidate Evaluation (LLM Externalizer)
  - 4a. Mutual Exclusivity Detection
  - 4b. Obsolescence and Deprecation Check
  - 4c. Stack Compatibility and Constraint Filtering
  - 4c-bis. Non-Coding Agent Filter
  - 4d. Requirements-Driven Promotion
  - 4e. Redundancy Pruning
  - 4f. Force-Include/Exclude Directives
  - 4g. Specialization-Aware Cherry-Pick
  - Step 5: Classify into Final Tiers
  - Step 6: Identify Complementary Agents
  - Step 6a: Review and Confirm Tier Assignments
  - Step 6b: Recommended Commands
  - Step 6c: Recommended Rules
  - Step 6d: Recommended MCP Servers
  - Step 6e: LSP Servers (Language-Based)
  - Step 6f: Recommended Hooks
- [Profiler TOML and Validation](references/profiler-toml-and-validation.md)
  - Step 7: Write .agent.toml (full annotated template, TOML syntax rules)
  - Step 8: Structural Validation (MANDATORY)
  - Step 8a: Element Name Verification (MANDATORY, anti-hallucination)
  - Step 8b-i: Token-Efficient Self-Review
  - Step 8b-ii: Interactive Review Entry

## Examples

```
/pss-setup-agent agents/my-agent.md
/pss-change-agent-profile my-agent.agent.toml add websocket-handler
```

## Error Handling

- Missing index: run `/pss-reindex-skills`
- Binary not found: run `uv run scripts/pss_build.py`

## Output

`.agent.toml` in `~/.claude/agents/`.

## Resources

- `schemas/pss-agent-toml-schema.json`
- `scripts/pss_validate_agent_toml.py`
