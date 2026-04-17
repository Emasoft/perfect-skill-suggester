# Execution Steps

1. Verify the resolved <agent-name>.md path exists and is readable
2. Verify each `--requirements` path exists and is readable (error with specific path if not)
3. Verify the CozoDB index at `$CLAUDE_PLUGIN_DATA/pss-skill-index.db` (fallback `~/.claude/cache/pss-skill-index.db`) exists and contains rows (use `pss health` — exit 0 = populated). Error out if not, instructing the user to run `/pss-reindex-skills` first.
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
   BINARY = os.path.join(plugin_root, "bin", binary_name)
   ```
7. Extract optional flags from command arguments:
   - `--fast`: boolean (present or absent) → enables fast mode (skip AI agent)
   - `--interactive`: boolean (present or absent) → pass as `INTERACTIVE=true/false`
   - `--include NAME...`: list of element names to force-include → pass as `INCLUDE_ELEMENTS`
   - `--exclude NAME...`: list of element names to force-exclude → pass as `EXCLUDE_ELEMENTS`
   - `--max-primary N`: integer override for primary tier limit → pass as `MAX_PRIMARY`
   - `--max-secondary N`: integer override for secondary tier limit → pass as `MAX_SECONDARY`
   - `--max-specialized N`: integer override for specialized tier limit → pass as `MAX_SPECIALIZED`
   - `--domains D...`: domain constraints → pass as `DOMAIN_CONSTRAINTS`
   - `--languages L...`: language constraints → pass as `LANGUAGE_CONSTRAINTS`
   - `--platforms P...`: platform constraints → pass as `PLATFORM_CONSTRAINTS`

8. **If `--fast` is set**: Run fast mode (Rust binary only, no AI agent)

   **Validation**: `--fast` cannot be combined with `--interactive` or `--requirements`. If combined, error:
   `ERROR: --fast cannot be combined with --interactive or --requirements (those require AI agent)`

   a. Invoke the Rust binary directly:
   ```bash
   "${BINARY}" --agent "${AGENT_PATH}" --format json --top 30
   ```
   The binary handles: scoring, mutual exclusivity filtering, non-coding agent detection,
   auto_skills pinning, co-usage discovery, domain affinity re-ranking, and TOML generation.
   It outputs the path of the written `.agent.toml` file to stdout.

   b. If `--output` was specified, move the generated file to the desired path:
   ```bash
   mv "${GENERATED_TOML}" "${OUTPUT_PATH}"
   ```

   c. Validate the generated TOML:
   ```bash
   uv run "${CLAUDE_PLUGIN_ROOT}/scripts/pss_validate_agent_toml.py" "${OUTPUT_PATH}" --check-index --verbose
   ```

   d. Verify element names (anti-hallucination):
   ```bash
   uv run "${CLAUDE_PLUGIN_ROOT}/scripts/pss_verify_profile.py" "${OUTPUT_PATH}" --agent-def "${AGENT_PATH}" --verbose
   ```

   e. Report result:
   - On success: `Profile generated (fast mode): <output-path>`
   - On validation failure: show errors (fast mode has no fix loop — user should re-run without `--fast` for AI-assisted fixes)

9. **If `--fast` is NOT set**: Run AI mode (spawn profiler agent)

   Spawn the `pss-agent-profiler` agent using the Task tool.

   The profiler agent applies AI reasoning (conflict detection, mutual exclusivity, cross-type coherence,
   stack compatibility) on top of the Rust pre-optimizations. This produces higher-quality profiles
   but takes significantly longer.

   The prompt to the agent MUST include:
   - `AGENT_PATH` — the resolved absolute path to the <agent-name>.md file
   - `REQUIREMENTS_PATHS` — the list of requirements file paths (may be empty)
   - `INDEX_PATH` — the path to the CozoDB skill index (`$CLAUDE_PLUGIN_DATA/pss-skill-index.db` or fallback `~/.claude/cache/pss-skill-index.db`)
   - `BINARY_PATH` — the absolute path to the Rust binary (resolved in step 6)
   - `OUTPUT_PATH` — the desired output path for the .agent.toml file
   - Instructions to follow the workflow defined in `${CLAUDE_PLUGIN_ROOT}/agents/pss-agent-profiler.md`
   - `INTERACTIVE` — whether interactive mode is enabled (`true/false`)
   - `INCLUDE_ELEMENTS` — list of elements to force-include (from `--include`, may be empty)
   - `EXCLUDE_ELEMENTS` — list of elements to force-exclude (from `--exclude`, may be empty)
   - Tier size overrides if specified (`MAX_PRIMARY`, `MAX_SECONDARY`, `MAX_SPECIALIZED`)
   - Domain/language/platform constraints if specified

   **CRITICAL**: Resolve `${CLAUDE_PLUGIN_ROOT}` to an absolute path BEFORE passing to the agent.

10. Report the result:
    - On success: `[DONE] Agent profile written to: <output-path>`
    - On failure: `[FAILED] <reason>`
