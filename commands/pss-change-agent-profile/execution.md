# Execution Steps

1. Parse arguments: extract `PROFILE_PATH` (first arg) and `CHANGE_INSTRUCTIONS` (remaining args)
2. Verify the `.agent.toml` file exists at `PROFILE_PATH`
3. Read the `.agent.toml` to extract `[agent].path` (the agent `.md` file)
4. Verify `~/.claude/cache/skill-index.json` exists
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
   system = platform.system()
   machine = platform.machine()
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
   BINARY = os.path.join(plugin_root, "src", "skill-suggester", "bin", binary_name)
   ```
7. Spawn the `pss-agent-profiler` agent with a CHANGE MODE prompt.

The prompt to the agent MUST include:
- `MODE=change` (not the default create mode)
- The absolute path to the existing `.agent.toml` file
- The agent `.md` path (from `[agent].path` in the TOML)
- The change instructions from the user
- The path to the Rust binary (for searching the index)
- The path to the verification script (`${PLUGIN_ROOT}/scripts/pss_verify_profile.py`)
- The path to the validation script (`${PLUGIN_ROOT}/scripts/pss_validate_agent_toml.py`)
- Instructions to: read the current TOML, apply changes, verify, validate, write back

**CRITICAL**: Resolve `${CLAUDE_PLUGIN_ROOT}` to an absolute path BEFORE passing to the agent.

8. Report the result:
   - On success: `[DONE] Profile updated: <profile-path> — <summary of changes>`
   - On failure: `[FAILED] <reason>`
