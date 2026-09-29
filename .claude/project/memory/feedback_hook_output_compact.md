---
name: hook-output-must-be-compact-skills-only
description: "PSS hook suggestions must be max 5 lines, skills only, no agents/commands/rules/mcp — saves tokens on every user message"
ocd: 2026-07-16
lmd: 2026-09-29
metadata:
  node_type: memory
  type: feedback
  tier: component
publish-globally: false
---

^57EUANNK [desc:"Hook output must show only skills (not commands, rules, agents, MCP, LSP) in compact 1-line format, max 5 suggestions; the agent profiler (JSON format) still gets all element types.", keywords:"hook output too verbose suggestions skills_only hook_mode_compact max_5_suggestions element_type_filter hook_vs_json_mode", type:feedback, ocd:2026-07-16, lmd:2026-09-29]
Hook output must show only skills (not commands, rules, agents, MCP, LSP) and use compact 1-line format per skill.
Max 5 suggestions. The agent profiler (JSON format) still gets all element types.

**Why:** Other Claude instances complained about ~50 lines of suggestion output wasting tokens on every single user message.

^5S33N0P8 [desc:"When modifying hook output format or the Rust binary's type filter, keep hook mode skills-only and compact; only JSON mode (agent profiler) includes all element types.", keywords:"modifying_hook_output rust_type_filter keep_skills_only json_mode_all_types agent_profiler_format change_hook_output_format", type:feedback, ocd:2026-07-16, lmd:2026-09-29]
**How to apply:** When modifying hook output format or the type filter in the Rust binary, keep hook mode skills-only and compact. Only JSON mode (agent profiler) should include all element types.

## Governed by
- [[pss-knowledge-hub]] — entry point to PSS's PROJECT-scope memory corpus.

## Notes and lessons learned
