---
name: pss-setup-agent
description: "Analyze an agent and suggest best-fit skills using the Rust scorer + AI post-filtering, writing results to .agent.toml"
argument-hint: "<agent-path-or-name> [--requirements PATH...] [--output PATH]"
allowed-tools: ["Task", "Read", "Bash", "Glob", "Grep", "WebSearch", "WebFetch"]
---

# PSS Setup Agent Command

Analyze an agent definition file and recommend best-fit skills from the PSS skill index, writing results to a `.agent.toml` configuration file. Uses the Rust skill-suggester binary for fast candidate scoring, then an AI agent for intelligent post-filtering.

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

1. Verify the resolved <agent-name>.md path exists and is readable
2. Verify each `--requirements` path exists and is readable (error with specific path if not)
3. Verify `~/.claude/cache/skill-index.json` exists (error if not — tell user to run `/pss-reindex-skills` first)
4. Determine the output path
5. Detect the platform-specific Rust binary:
   ```python
   import platform, os
   system = platform.system()   # 'Darwin', 'Linux', 'Windows'
   machine = platform.machine() # 'arm64', 'x86_64', 'AMD64'
   plugin_root = os.environ["CLAUDE_PLUGIN_ROOT"]

   PLATFORM_MAP = {
       ("Darwin", "arm64"):   "pss-darwin-arm64",
       ("Darwin", "x86_64"):  "pss-darwin-x86_64",
       ("Linux", "x86_64"):   "pss-linux-x86_64",
       ("Linux", "aarch64"):  "pss-linux-arm64",
       ("Windows", "AMD64"):  "pss-windows-x86_64.exe",
       ("Windows", "x86_64"): "pss-windows-x86_64.exe",
   }

   binary_name = PLATFORM_MAP.get((system, machine))
   if binary_name is None:
       raise RuntimeError(f"Unsupported platform: {system}/{machine}")
   BINARY = os.path.join(plugin_root, "rust", "skill-suggester", "bin", binary_name)
   ```
6. Spawn the `pss-agent-profiler` agent using the Task tool

The prompt to the agent MUST include:
- The resolved absolute path to the <agent-name>.md file
- The list of requirements file paths (may be empty)
- The path to skill-index.json (`~/.claude/cache/skill-index.json`)
- The absolute path to the Rust binary (resolved in step 5)
- The desired output path for the .agent.toml file
- Instructions to follow the workflow defined in `${CLAUDE_PLUGIN_ROOT}/agents/pss-agent-profiler.md`

**CRITICAL**: Resolve `${CLAUDE_PLUGIN_ROOT}` to an absolute path BEFORE passing to the agent.

7. Report the result:
   - On success: `[DONE] Agent profile written to: <output-path>`
   - On failure: `[FAILED] <reason>`

## Error Handling

- Missing <agent-name>.md: `ERROR: Agent file not found: <path>`
- Missing requirements file: `ERROR: Requirements file not found: <path>`
- Missing skill-index.json: `ERROR: Skill index not found. Run /pss-reindex-skills first.`
- Missing Rust binary: `ERROR: PSS binary not found for platform <OS>/<ARCH>. Run cargo build.`
- Invalid plugin:agent notation: `ERROR: Could not resolve agent 'plugin:name'. Check plugin is installed.`
