# Error Handling

- If the Rust binary is not found or not executable, abort with an explicit error message — do not fall back to manual scoring.
- If the skill index (`~/.claude/cache/skill-index.json`) does not exist, instruct the user to run `/pss-reindex-skills` first.
- If validation fails (exit code != 0), fix all errors and re-validate — do not deliver an invalid `.agent.toml`.
- If `CLAUDE_PLUGIN_ROOT` is not set, abort immediately with instructions to set it.
