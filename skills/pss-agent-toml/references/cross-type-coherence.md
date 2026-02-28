# Cross-Type Coherence Validation

## Table of Contents

- [5.1 Cross-type overlap detection](#51-cross-type-overlap-detection)
- [5.2 Coherence checklist](#52-coherence-checklist)
- [5.3 Resolution strategy](#53-resolution-strategy)
- [5.4 Autonomous vs Interactive mode](#54-autonomous-vs-interactive-mode)

---

**This is the most critical phase.** The Rust binary scores candidates within each type independently. It does NOT check for overlaps or conflicts BETWEEN types. You MUST validate coherence across ALL sections before finalizing.

**5.1 Cross-type overlap detection**

Compare every element in the profile against every other element across ALL types:

**Skill <-> MCP overlap**: A skill and an MCP server providing the same capability.
- Example: A "database-management" skill AND a "postgres-mcp" server — the MCP gives direct DB access, making parts of the skill redundant. Keep the MCP (it provides actual tools), demote or remove the skill.
- Example: A "chrome-devtools" skill AND a "chrome-devtools" MCP — the MCP provides tools, the skill provides instructions on how to use them. Both are valid (keep both).

**Skill <-> Agent overlap**: A skill that teaches what an agent already does.
- Example: A "python-test-writer" skill AND a "python-test-writer" agent — the agent IS the executor. Keep the agent, remove the skill (the agent loads its own skills).
- Example: A "security" skill AND an "aegis" agent — different scope (skill = instructions, agent = executor), both valid.

**Agent <-> Agent overlap**: Two agents with the same capabilities.
- Example: "sleuth" agent AND "debug-agent" — both do debugging. Keep ONE based on which better matches the project. Document the other in `[skills.excluded]`.

**Skill <-> Command overlap**: A skill that automates what a command does manually.
- Generally keep both — commands are user-invoked, skills are auto-suggested. But remove the skill if its ONLY purpose is to invoke the command.

**MCP <-> MCP overlap**: Two MCP servers providing the same tools.
- Example: Two browser automation MCPs — keep the one matching the project's existing config.

**Rule <-> Rule conflict**: Two rules that contradict each other.
- Example: A "always-use-mocks" rule AND a "never-use-mocks" rule. Remove the one contradicting the project's testing philosophy.

**5.2 Coherence checklist**

Before writing the final `.agent.toml`, verify ALL of these:

- [ ] No skill duplicates the capability of an MCP server already in `[mcp]`
- [ ] No skill duplicates the capability of an agent already in `[agents]`
- [ ] No two agents in `[agents]` serve the same role
- [ ] No two MCP servers in `[mcp]` provide overlapping tool sets
- [ ] No two rules in `[rules]` contradict each other
- [ ] No skill in primary tier is a strict subset of another primary skill
- [ ] Every command in `[commands]` is relevant to the agent's actual workflow
- [ ] Every rule in `[rules]` applies to the agent's domain (not a different domain)
- [ ] LSP servers match the project's actual languages (not guessed)
- [ ] Framework-specific elements all target the SAME framework (no React + Vue mix)
- [ ] Runtime-specific elements all target the SAME runtime (no Node + Deno mix)
- [ ] All selected elements are compatible with the agent's tech stack
- [ ] No obsolete or deprecated elements remain

**5.3 Resolution strategy**

When an overlap or conflict is found:
1. **Read both elements' SKILL.md/agent.md** to understand exact scope
2. **Determine which provides more value** for this specific agent + project combination
3. **Keep the higher-value element**, remove or demote the other
4. **Document the exclusion** in `[skills.excluded]` with the reason
5. If truly undecidable (both equally valuable, different trade-offs), **ask the user/orchestrator** — but only in this case

**5.4 Autonomous vs Interactive mode**

**Autonomous (default)**: Execute the full pipeline, apply all evaluation and coherence validation, resolve conflicts using the rules above, produce the final `.agent.toml`, and report the result. Only surface truly unresolvable conflicts to the user.

**Interactive (when requested)**: Present the draft profile with a comparison table, accept modifications (add/remove/move/replace elements), re-validate after each change, and confirm before writing.

Interactive mode activates only when:
- The user explicitly asks for review ("let me review the profile first")
- An orchestrator requests collaboration ("present options for approval")
- Truly unresolvable conflicts are detected (equal alternatives with no deciding factor)
