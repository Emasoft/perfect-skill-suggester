---
name: hook-output-must-be-compact-skills-only
description: "PSS hook suggestions must be max 5 lines, skills only, no agents/commands/rules/mcp — saves tokens on every user message"
ocd: 2026-07-16
lmd: 2026-07-23
metadata:
  node_type: memory
  type: feedback
  tier: component
---

Hook output must show only skills (not commands, rules, agents, MCP, LSP) and use compact 1-line format per skill.
Max 5 suggestions. The agent profiler (JSON format) still gets all element types.

**Why:** Other Claude instances complained about ~50 lines of suggestion output wasting tokens on every single user message.

**How to apply:** When modifying hook output format or the type filter in the Rust binary, keep hook mode skills-only and compact. Only JSON mode (agent profiler) should include all element types.

## Governed by
- [[pss-knowledge-hub]] — entry point to PSS's PROJECT-scope memory corpus.

## Notes and lessons learned
