---
name: pss-setup-agent
description: "Profile an agent with best-fit skills"
argument-hint: "<agent-path-or-name> [--requirements PATH...] [--output PATH]"
allowed-tools: ["Task", "Read", "Bash", "Glob", "Grep", "WebSearch", "WebFetch"]
---

# PSS Setup Agent Command

Analyze an agent definition file and recommend best-fit skills from the PSS skill index, writing results to a `.agent.toml` configuration file. Uses the Rust skill-suggester binary for fast candidate scoring, then an AI agent for intelligent post-filtering.

**IMPORTANT**: An AI agent is ALWAYS required to produce `.agent.toml` files. The Rust binary generates scored candidates, but element selection requires AI reasoning — conflict detection, cross-type coherence validation, framework compatibility, and use-case prediction cannot be done mechanically. This command spawns the `pss-agent-profiler` agent specifically for this purpose.

## Usage

```
/pss-setup-agent /path/to/<agent-name>.md
/pss-setup-agent plugin-name:agent-name
/pss-setup-agent /path/to/<agent-name>.md --requirements /path/to/prd.md
/pss-setup-agent /path/to/<agent-name>.md --requirements /path/to/prd.md /path/to/tech-spec.md /path/to/arch.md
/pss-setup-agent /path/to/<agent-name>.md --requirements /path/to/prd.md --output /custom/output.agent.toml
```

## Argument Parsing

1. **Agent source** (required, first positional argument):
   - If it contains `:` → treat as `plugin-name:agent-name` notation
     - Resolve by searching `~/.claude/plugins/cache/*/plugin-name/*/agents/<agent-name>.md`
     - Also check `~/.claude/plugins/plugin-name/agents/<agent-name>.md`
   - If it's a file path → use directly as the <agent-name>.md file path
   - If no argument → error with usage instructions

2. **`--requirements PATH...`** (optional, one or more paths):
   - Accepts one or more file paths after the flag (space-separated, until next flag or end)
   - Each path points to a design document: PRD, tech spec, architecture doc, requirements file, etc.
   - The profiler agent reads ALL of them to understand what the agent will actually build
   - These files provide project-specific context that the <agent-name>.md alone cannot convey
   - Without requirements: profiling is based only on the agent's role/description (generic)
   - With requirements: profiling accounts for the specific project stack, APIs, libraries needed

3. **`--output PATH`** (optional):
   - If provided → use as the output .agent.toml path
   - If not provided → default to `team/agents-cfg/<agent-name>.agent.toml` relative to cwd
   - Create the output directory if it doesn't exist

## Execution

See detailed execution steps including `CLAUDE_PLUGIN_ROOT` validation, platform binary detection, and agent spawning instructions:

- [Execution Steps](pss-setup-agent/execution.md)

## Error Handling

- Missing <agent-name>.md: `ERROR: Agent file not found: <path>`
- Missing requirements file: `ERROR: Requirements file not found: <path>`
- Missing skill-index.json: `ERROR: Skill index not found. Run /pss-reindex-skills first.`
- Missing Rust binary: `ERROR: PSS binary not found for platform <OS>/<ARCH>. Run cargo build.`
- Invalid plugin:agent notation: `ERROR: Could not resolve agent 'plugin:name'. Check plugin is installed.`
