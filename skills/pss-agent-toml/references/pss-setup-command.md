# Using the /pss-setup-agent Command

## Table of Contents

- [Usage Examples](#usage-examples)
- [How It Works](#how-it-works)

## Usage Examples

```
/pss-setup-agent /path/to/agent.md
/pss-setup-agent /path/to/agent.md --requirements /path/to/prd.md /path/to/tech-spec.md
/pss-setup-agent plugin-name:agent-name
/pss-setup-agent /path/to/agent.md --output /custom/output.agent.toml
/pss-setup-agent /path/to/agent.md --interactive
/pss-setup-agent /path/to/agent.md --requirements /path/to/prd.md --interactive
```

## How It Works

This command spawns the `pss-agent-profiler` agent, which follows the full Phase 1-6 workflow with AI reasoning at every step.

### Flags

| Flag | Description |
|------|-------------|
| `--requirements <paths...>` | Design/requirements files for project-specific profiling |
| `--output <path>` | Custom output path for the .agent.toml file |
| `--interactive` | Enable interactive review mode (present profile for user approval with modify/search directives) |

### Interactive Mode

When `--interactive` is passed, the profiler adds a review phase after generating and validating the `.agent.toml`:

1. **Self-Review**: Profiler checks its own output for naming errors, auto_skills demotion, non-coding violations, coverage gaps
2. **Present Summary**: Shows a review table with all sections, tier assignments, exclusions, and issues
3. **Accept Directives**: User can include/exclude/swap/move elements, search the index for alternatives
4. **Re-validate**: After each change, the TOML is re-validated and the summary is updated
5. **Approve**: User types `approve` or `done` to finalize

Without `--interactive`, the profiler still performs self-review (step 1) and auto-fixes issues, but does not present the summary or accept directives.
