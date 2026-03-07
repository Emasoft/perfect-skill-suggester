# Execution Steps

1. Verify the resolved <agent-name>.md path exists and is readable
2. Verify each `--requirements` path exists and is readable (error with specific path if not)
3. Verify `~/.claude/cache/skill-index.json` exists (error if not — tell user to run `/pss-reindex-skills` first)
4. Determine the output path
5. Validate `CLAUDE_PLUGIN_ROOT` environment variable:
   ```python
   import os
   from pathlib import Path

   plugin_root_str = os.environ.get("CLAUDE_PLUGIN_ROOT")
   if not plugin_root_str:
       raise RuntimeError(
           "CLAUDE_PLUGIN_ROOT is not set. "
           "This variable is set automatically by the Claude Code plugin loader."
       )
   if not Path(plugin_root_str).is_dir():
       raise RuntimeError(
           f"CLAUDE_PLUGIN_ROOT is not a valid directory: {plugin_root_str}"
       )
   ```
6. Detect the platform-specific Rust binary:
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
7. Spawn the `pss-agent-profiler` agent using the Task tool

   The profiler agent is MANDATORY — it applies AI reasoning (conflict detection, mutual exclusivity, cross-type coherence, stack compatibility) that no script can replicate. Do NOT attempt to generate `.agent.toml` without an AI agent.

The prompt to the agent MUST include:
- The resolved absolute path to the <agent-name>.md file
- The list of requirements file paths (may be empty)
- The path to skill-index.json (`~/.claude/cache/skill-index.json`)
- The absolute path to the Rust binary (resolved in step 6)
- The desired output path for the .agent.toml file
- Instructions to follow the workflow defined in `${CLAUDE_PLUGIN_ROOT}/agents/pss-agent-profiler.md`

**CRITICAL**: Resolve `${CLAUDE_PLUGIN_ROOT}` to an absolute path BEFORE passing to the agent.

8. Report the result:
   - On success: `[DONE] Agent profile written to: <output-path>`
   - On failure: `[FAILED] <reason>`
