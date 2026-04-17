# Error Handling

## Table of Contents

- [Binary Not Found](#binary-not-found)
- [Missing Skill Index](#missing-skill-index)
- [Validation Failure](#validation-failure)
- [Missing Environment Variable](#missing-environment-variable)

## Binary Not Found

If the Rust binary is not found or not executable, abort with an explicit error message — do not fall back to manual scoring.

## Missing Skill Index

If the CozoDB skill index (`$CLAUDE_PLUGIN_DATA/pss-skill-index.db`, fallback `~/.claude/cache/pss-skill-index.db`) does not exist, instruct the user to run `/pss-reindex-skills` first.

## Validation Failure

If validation fails (exit code != 0), fix all errors and re-validate — do not deliver an invalid `.agent.toml`.

## Missing Environment Variable

If `CLAUDE_PLUGIN_ROOT` is not set, abort immediately with instructions to set it.
