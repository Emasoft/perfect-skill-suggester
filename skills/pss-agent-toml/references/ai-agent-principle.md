# Fundamental Principle: AI Agent is ALWAYS Required

**An AI agent MUST be the decision-maker for element selection.** No mechanical script or automated pipeline can produce a correct agent profile. Here is why:

1. **Conflict detection requires reasoning**: A script cannot determine that "jest-testing" and "vitest-testing" are mutually exclusive, or that a "database-management" skill is redundant when a "postgres-mcp" server is already included.

2. **Use case prediction requires understanding**: Choosing the right skills means predicting what the agent will actually encounter — a "security auditor" working on a healthcare app needs HIPAA compliance skills that no keyword matcher would surface.

3. **Cross-type coherence requires judgment**: A skill, an MCP server, and an agent can all provide "browser automation" — deciding which combination to keep requires reading their actual content and understanding the trade-offs.

4. **Framework/runtime compatibility requires knowledge**: Knowing that Vitest is the correct test runner for a Vite-based project, or that Bun replaces npm/yarn, requires real-world understanding that no scoring algorithm provides.

**The Rust binary provides scored candidates. The AI agent makes the decisions.** This is the same principle as the prompt hook: the binary suggests, Claude chooses.

This skill teaches ANY agent or Claude model how to:
1. **Search** the element index to find candidates for each section
2. **Evaluate** candidates by reading their actual SKILL.md/agent.md content
3. **Compare** alternatives to resolve conflicts — including cross-type overlap detection
4. **Add** specific elements from any source (local, marketplace, GitHub, network)
5. **Validate coherence** — ensure no overlapping, conflicting, or redundant elements across ALL types
6. **Assemble** and validate the final `.agent.toml` file

**Default mode is autonomous**: the agent executes the full pipeline, makes all decisions, produces the `.agent.toml`, and reports the result. Interactive collaboration with the user or orchestrator is optional — it only happens when explicitly requested or when truly unresolvable conflicts are detected.
