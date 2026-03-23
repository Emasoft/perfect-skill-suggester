---
name: pss-setup-agent
description: "Profile an agent with best-fit skills"
argument-hint: "<agent-path-or-name> [--fast] [--requirements PATH...] [--output PATH] [--interactive] [--include NAME...] [--exclude NAME...] [--max-primary N] [--max-secondary N] [--max-specialized N] [--domains D...] [--languages L...] [--platforms P...]"
allowed-tools: ["Task", "Read", "Write", "Edit", "Bash", "Glob", "Grep", "WebSearch", "WebFetch", "mcp__plugin_llm-externalizer_llm-externalizer__batch_check", "mcp__plugin_llm-externalizer_llm-externalizer__code_task", "mcp__plugin_llm-externalizer_llm-externalizer__chat"]
---

# PSS Setup Agent Command

Analyze an agent definition file and recommend best-fit skills from the PSS skill index, writing results to a `.agent.toml` configuration file.

**Two modes:**
- **Default (AI mode)**: Rust binary scores candidates → AI agent applies intelligent post-filtering (conflict detection, cross-type coherence, use-case prediction). Thorough but takes minutes.
- **Fast mode (`--fast`)**: Rust binary scores candidates → applies built-in pre-optimizations (mutual exclusivity, non-coding filter, auto_skills pinning) → writes TOML directly. Takes seconds, no AI agent needed.

Both modes benefit from the same Rust pre-optimizations. Fast mode skips AI reasoning but produces a good baseline profile suitable for most use cases.

## Usage

```
/pss-setup-agent /path/to/<agent-name>.md
/pss-setup-agent /path/to/<agent-name>.md --fast
/pss-setup-agent plugin-name:agent-name
/pss-setup-agent /path/to/<agent-name>.md --requirements /path/to/prd.md
/pss-setup-agent /path/to/<agent-name>.md --requirements /path/to/prd.md /path/to/tech-spec.md /path/to/arch.md
/pss-setup-agent /path/to/<agent-name>.md --requirements /path/to/prd.md --output /custom/output.agent.toml
/pss-setup-agent /path/to/<agent-name>.md --interactive
/pss-setup-agent /path/to/<agent-name>.md --include websocket-handler --exclude jest-testing
/pss-setup-agent /path/to/<agent-name>.md --max-primary 5 --max-secondary 8
/pss-setup-agent /path/to/<agent-name>.md --domains security backend --languages python rust
```

## Argument Parsing

1. **Agent source** (required, first positional argument):
   - If it contains `:` → treat as `plugin-name:agent-name` notation
     - Resolve by searching `~/.claude/plugins/cache/*/plugin-name/*/agents/<agent-name>.md`
     - Also check `~/.claude/plugins/plugin-name/agents/<agent-name>.md`
   - If it's a file path → use directly as the <agent-name>.md file path
   - If no argument → error with usage instructions

2. **`--fast`** (optional, boolean flag):
   - If present → skip AI agent entirely, use Rust binary's built-in profiling with pre-optimizations
   - The Rust binary handles: scoring, mutual exclusivity filtering, non-coding agent detection, auto_skills pinning, co-usage discovery, domain affinity re-ranking, and TOML generation
   - Output is validated with `pss_validate_agent_toml.py` and `pss_verify_profile.py`
   - Takes seconds instead of minutes. Best for quick profiles or batch profiling
   - Cannot be combined with `--interactive` (interactive requires AI agent)
   - Cannot be combined with `--requirements` (requirements analysis requires AI agent)

3. **`--requirements PATH...`** (optional, one or more paths):
   - Accepts one or more file paths after the flag (space-separated, until next flag or end)
   - Each path points to a design document: PRD, tech spec, architecture doc, requirements file, etc.
   - The profiler agent reads ALL of them to understand what the agent will actually build
   - These files provide project-specific context that the <agent-name>.md alone cannot convey
   - Without requirements: profiling is based only on the agent's role/description (generic)
   - With requirements: profiling accounts for the specific project stack, APIs, libraries needed

4. **`--output PATH`** (optional):
   - If provided → use as the output .agent.toml path
   - If not provided → default to `team/agents-cfg/<agent-name>.agent.toml` relative to cwd
   - Create the output directory if it doesn't exist

5. **`--interactive`** (optional, boolean flag):
   - If present → activate interactive review mode after profile generation
   - Profiler presents a review summary and accepts user directives (include/exclude/swap/move/search)
   - User must type `approve` or `done` to finalize the profile
   - Without this flag → profile is auto-approved after self-review

6. **`--include NAME...`** (optional, one or more element names):
   - Elements that MUST be included in the final profile
   - Profiler adds them to the appropriate section/tier regardless of binary scoring
   - Takes precedence over binary exclusion decisions

7. **`--exclude NAME...`** (optional, one or more element names):
   - Elements that MUST NOT appear in the final profile
   - Profiler removes them even if the binary scores them highly
   - Documented in `[skills.excluded]` with reason "Excluded by user directive"

8. **`--max-primary N`**, **`--max-secondary N`**, **`--max-specialized N`** (optional, integers):
   - Override default tier size limits (default: primary=7, secondary=12, specialized=8)
   - Auto-skills from frontmatter still take priority and can extend primary beyond the max

9. **`--domains D...`**, **`--languages L...`**, **`--platforms P...`** (optional, one or more strings):
   - Constrain profiling to specific domains (security, frontend, backend, devops, data)
   - Constrain to specific languages (python, typescript, rust, go, etc.)
   - Constrain to specific platforms (linux, macos, windows, ios, android, web)
   - Elements outside these constraints are excluded from consideration

## Execution

See detailed execution steps including `CLAUDE_PLUGIN_ROOT` validation, platform binary detection, and agent spawning instructions:

- [Execution Steps](pss-setup-agent/execution.md)

## Error Handling

- Missing <agent-name>.md: `ERROR: Agent file not found: <path>`
- Missing requirements file: `ERROR: Requirements file not found: <path>`
- Missing skill-index.json: `ERROR: Skill index not found. Run /pss-reindex-skills first.`
- Missing Rust binary: `ERROR: PSS binary not found for platform <OS>/<ARCH>. Run cargo build.`
- Invalid plugin:agent notation: `ERROR: Could not resolve agent 'plugin:name'. Check plugin is installed.`
