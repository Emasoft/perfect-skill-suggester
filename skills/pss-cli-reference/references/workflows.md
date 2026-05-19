# PSS CLI — Workflow Recipes

## Table of Contents

- [Workflow 1 — "What's installed?" (inventory)](#workflow-1--whats-installed-inventory)
- [Workflow 2 — "Find a skill"](#workflow-2--find-a-skill)
- [Workflow 3 — History / lifecycle](#workflow-3--history--lifecycle)
- [Workflow 4 — Plugin authoring](#workflow-4--plugin-authoring)
- [Workflow 5 — Database / health / maintenance](#workflow-5--database--health--maintenance)

Five ready-to-paste shell recipes covering the most common PSS query patterns. All recipes assume:

```bash
BIN="$CLAUDE_PLUGIN_ROOT/bin/pss-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
```

## Workflow 1 — "What's installed?" (inventory)

Use when the user wants to know the current state of the index without filtering by attribute.

```bash
# Total count and per-type breakdown
"$BIN" count
"$BIN" stats --format table

# Per-scope breakdown (user / project / plugin / marketplace counts)
"$BIN" stats-by-scope

# Everything a specific plugin provides
"$BIN" by-plugin perfect-skill-suggester

# Everything from a specific marketplace
"$BIN" by-marketplace emasoft-plugins

# Sorted / filtered list
"$BIN" list --type skill --top 100 --format table
```

## Workflow 2 — "Find a skill"

Use when the user wants to locate a skill / agent / command by intent or attribute.

```bash
# Free-text search across name + description + keywords
"$BIN" search "docker container build" --top 10 --format table

# Exact keyword match (uses skill_keywords index — faster than search)
"$BIN" find-by-keyword postgres

# Substring match on name (case-insensitive); pass --regex for full Rust regex
"$BIN" find-by-name auth --limit 20

# Filter by attribute
"$BIN" find-by-language rust
"$BIN" find-by-framework fastapi
"$BIN" find-by-tool kubernetes
"$BIN" find-by-platform aws
"$BIN" find-by-domain security

# Lookup one entry by exact name (use --source to disambiguate user vs plugin)
"$BIN" get my-skill --source plugin:perfect-skill-suggester --json

# Full details for debugging
"$BIN" inspect my-skill --format table
```

Slash-command wrappers: `/pss-search <query>` for quick interactive searches; `/pss-get-description <name>` for token-efficient metadata.

## Workflow 3 — History / lifecycle

Use when the user asks "when did X arrive?", "what changed last week?", "what does X look like at \<date\>?". All temporal subcommands read from the event-sourced `events` table and the materialized `elements_state` view. See [querying-the-index.md](querying-the-index.md) for the schema and the full list of 28 temporal subcommands.

```bash
# Full timeline for one element
"$BIN" timeline skill:my-skill@user:

# Filtered timeline — only signal events (installed / content_changed /
# description_changed / removed)
"$BIN" version-history skill:my-skill@user:

# First-seen / last-seen
"$BIN" lifespan skill:my-skill@user:

# Point-in-time snapshot
"$BIN" as-of <YYYY-MM-DD>
"$BIN" show skill:my-skill@user: --as-of <YYYY-MM-DD>

# Diff two snapshots of one element
"$BIN" diff skill:my-skill@user: <D1> <D2>

# What changed across the whole index between two dates
"$BIN" changed-between <D1> <D2>
"$BIN" compare-snapshots <D1> <D2>

# Last reindex summary
"$BIN" last-changes
"$BIN" changes-summary --window 7d

# What disappeared
"$BIN" removed-since <YYYY-MM-DD>
"$BIN" currently-missing-but-once-was
```

Slash-command wrapper: `/pss-added-since <when>` is the most common entry point.

## Workflow 4 — Plugin authoring

Use when the user wants to create or modify an agent profile, then turn it into an installable plugin. PSS routes through slash commands here — the Rust binary is only invoked via `--agent` internally.

```bash
# Generate a baseline .agent.toml from an agent definition
/pss-setup-agent <agent-name>            # AI mode (~2-5 min, post-filters)
/pss-setup-agent <agent-name> --fast     # Rust-only (~2-5 s)

# Modify an existing profile in natural language
/pss-change-agent-profile <profile.agent.toml>

# Align an existing profile with a project requirements doc
/pss-change-agent-profile <profile.agent.toml> --requirements docs/prd.md

# Generate an installable plugin from the profile
/pss-make-plugin-from-profile <profile.agent.toml>

# Inspect the profile after generation
"$BIN" inspect <agent-name>              # only if the agent is itself indexed
```

The plugin generator emits the standard plugin layout (`plugin.json`, `skills/`, `agents/`, `commands/`, `rules/`) and adds `SessionStart` / `SessionEnd` hooks to symlink rules into the project's `.claude/rules/` (rules are not a native Claude Code plugin component).

## Workflow 5 — Database / health / maintenance

Use when the user is troubleshooting, comparing scopes, or maintaining the index.

```bash
# Probe DB health (exit 0=populated, 1=empty/corrupt, 2=missing)
"$BIN" health --verbose

# Detailed event-store stats (event count, blob count, oldest event, retention)
"$BIN" db-stats

# Recent reindex history
"$BIN" scan-log --limit 10

# Full reindex (or dry-run preview)
"$BIN" reindex                           # writes to the DB
"$BIN" reindex --dry-run                 # prints events without writing
# Recommended slash-command wrapper:
/pss-reindex-skills

# Retention: trim old history (default window: 9 months)
"$BIN" retention                         # print current window
"$BIN" retention --set 6m                # change it
"$BIN" prune-history --dry-run           # preview deletions
"$BIN" prune-history                     # commit

# Catch duplicate installs across scopes
"$BIN" dedup-candidates --min-count 2

# Compare two scopes (e.g. user vs project)
"$BIN" scope-diff user project --type skill

# JSON snapshot for git-diff workflows
"$BIN" export --json --path /tmp/pss-snapshot.json
```
