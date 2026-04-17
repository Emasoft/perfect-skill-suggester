# Execution Steps

1. Parse arguments: extract `PROFILE_PATH` (first arg), `--requirements PATHS` (optional), and `CHANGE_INSTRUCTIONS` (remaining args after flags). If `--requirements` is present but no change instructions follow, default to "align with project requirements".
2. Verify the `.agent.toml` file exists at `PROFILE_PATH`
3. Read the `.agent.toml` to extract `[agent].path` (the agent `.md` file) as `AGENT_PATH`
4. If `--requirements` provided, verify each requirements file exists
5. Verify the CozoDB index at `$CLAUDE_PLUGIN_DATA/pss-skill-index.db` (fallback `~/.claude/cache/pss-skill-index.db`) exists and has rows (use `pss health`)
6. Validate `CLAUDE_PLUGIN_ROOT` environment variable:
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
7. Detect the platform-specific Rust binary:
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
   BINARY = os.path.join(plugin_root, "bin", binary_name)
   ```
8. Spawn the `pss-agent-profiler` agent with a CHANGE MODE prompt.

The prompt to the agent MUST include:
- `MODE=change` (activates change mode — see "Change Mode" section in pss-agent-profiler.md)
- `PROFILE_PATH` — the absolute path to the existing `.agent.toml` file
- `AGENT_PATH` — the agent `.md` path (from `[agent].path` in the TOML)
- `CHANGE_INSTRUCTIONS` — the change instructions from the user
- `REQUIREMENTS_PATHS` — list of requirements file paths (may be empty). When non-empty, the profiler uses the `pss-design-alignment` skill: scores requirements separately (Pass 2), cherry-picks elements matching the agent's specialization, and merges into the existing profile
- `BINARY_PATH` — path to the Rust binary (for searching the index)
- `INDEX_PATH` — path to the CozoDB skill index (`$CLAUDE_PLUGIN_DATA/pss-skill-index.db`, fallback `~/.claude/cache/pss-skill-index.db`)
- The path to the verification script: `${PLUGIN_ROOT}/scripts/pss_verify_profile.py`
- The path to the validation script: `${PLUGIN_ROOT}/scripts/pss_validate_agent_toml.py`
- Instructions to: read the current TOML, apply changes, run verification with `--agent-def "${AGENT_PATH}"`, validate, write back

**CRITICAL**: Resolve `${CLAUDE_PLUGIN_ROOT}` to an absolute path BEFORE passing to the agent.

9. Report the result:
   - On success: `[DONE] Profile updated: <profile-path> — <summary of changes>`
   - On failure: `[FAILED] <reason>`
