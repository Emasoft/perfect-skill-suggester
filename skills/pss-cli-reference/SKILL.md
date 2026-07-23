---
name: pss-cli-reference
description: "Use when the user wants to query the PSS index, search/list/inspect elements, run lifecycle or history queries, build a plugin from a profile, or anywhere a `pss …` CLI command is needed. Loaded by pss-agent-profiler."
user-invocable: false
context: fork
background: false
---

# PSS CLI Reference Skill

**Loaded by `pss-agent-profiler`** and **Used by** any agent that routes a natural-language request to the PSS CLI surface (64 subcommands).

## Overview

The PSS Rust binary (`bin/pss-<platform>-<arch>`) exposes 64 read-only subcommands across six categories: search/inspect, find-by-attribute, lifecycle filters, temporal queries, indexing/maintenance, plugin authoring. Defaults to JSON, `--format table` for human display. <10 ms against 8000+ entries. Store: CozoDB at `$CLAUDE_PLUGIN_DATA/pss-skill-index.db` — read it ONLY via this binary (it is `fcntl`-locked; a raw read races the reindex writer and SIGABRTs).

## Prerequisites

PSS enabled; `pss health --verbose` passes. If empty, run `/pss-reindex-skills`.

## Instructions

1. Match the request against the [Quick decision table](#quick-decision-table).
2. `BIN="$CLAUDE_PLUGIN_ROOT/bin/pss-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"`.
3. Run with flags: `--format table|json`, `--limit N`, `--as-of <DATE>`.
4. Hand off to a slash command for follow-up (`/pss-search`, `/pss-setup-agent`, `/pss-make-plugin-from-profile`).

Shell recipes: [references/workflows.md](references/workflows.md).

## Quick decision table

| User says… | Command |
|---|---|
| "what's installed" | `pss summary`, `pss list`, `pss stats`, `pss tree` |
| "find a skill for X" | `pss search "X"`, `pss find-by-keyword X`, `/pss-search X` |
| "details of X" | `pss inspect X`, `pss get X`, `/pss-get-description X` |
| "skills for \<attribute\>" | `pss find-by-{language,framework,tool,platform,domain} X` |
| "installed since \<when\>" | `pss list-added-since 1w`, `/pss-added-since 1w` |
| "changed since \<when\>" | `pss list-updated-since 24h`, `pss last-changes`, `pss changes-summary` |
| "snapshot at \<date\>" | `pss as-of <DATE>`, `pss show X --as-of <DATE>` |
| "what's active in folder X at time T" | `pss active-in <ABS_PATH> --as-of <DATE>` |
| "canonical db path" | `pss db-path` |
| "project slug for folder X" | `pss project-slug <ABS_PATH>` |
| "binary version / contract" | `pss --contract-version` |
| "history of X" | `pss timeline X`, `pss version-history X`, `pss lifespan X` |
| "diff between dates" | `pss diff X <D1> <D2>`, `pss compare-snapshots <D1> <D2>` |
| "what disappeared" | `pss removed-since <DATE>`, `pss currently-missing-but-once-was` |
| "duplicates across scopes" | `pss dedup-candidates`, `pss multi-scope <NAME>`, `pss scope-diff` |
| "in plugin / marketplace X" | `pss by-plugin <name>`, `pss by-marketplace <name>`, `pss plugin-history <name>` |
| "tune / build plugin from profile" | `/pss-setup-agent`, `/pss-change-agent-profile`, `/pss-make-plugin-from-profile` |
| "rebuild / health / export" | `/pss-reindex-skills`, `pss health`, `pss db-stats`, `pss export --json` |

Dates: RFC 3339, `<YYYY-MM-DD>` (UTC midnight), relative (`1d`, `2w`, `24h`), tokens (`now`, `yesterday`).

## Error Handling

- Binary missing → rebuild via `uv run scripts/pss_build.py`.
- `health` exit 2 → `/pss-reindex-skills`. Exit 1 → delete `$CLAUDE_PLUGIN_DATA/pss-skill-index.db` then reindex.
- `get`/`inspect` empty → `find-by-name <substring>`; use `--source` to disambiguate.
- Invalid date → temporal cmds fail fast with stderr parse error.

## Output

Query subcommands accept `--format json` (default) or `--format table` (Unicode box drawing). Empty result sets exit 0 with `[]` or an empty table.

## Examples

```bash
BIN="$CLAUDE_PLUGIN_ROOT/bin/pss-$(uname -s)-$(uname -m)"
"$BIN" summary
"$BIN" search docker --top 5 --format table
"$BIN" version-history skill:python@plugin:perfect-skill-suggester:
```

## Resources

`docs/pss-cli-reference.md` documents every subcommand. Companion skill: `pss-usage`.

## References

- [references/workflows.md](references/workflows.md) — five ready-to-paste shell recipes
  - Table of Contents
  - Workflow 1 — "What's installed?" (inventory)
  - Workflow 2 — "Find a skill"
  - Workflow 3 — History / lifecycle
  - Workflow 4 — Plugin authoring
  - Workflow 5 — Database / health / maintenance
- [references/quick-reference.md](references/quick-reference.md) — one-line description per subcommand
  - Table of Contents
  - Category 1: Search and inspect (14 commands) — incl. `db-path`, `project-slug`
  - Category 2: Find by attribute (7 commands)
  - Category 3: Lifecycle filters (3 commands)
  - Category 4: Temporal queries (29 commands) — incl. `active-in`
  - Category 5: Indexing and maintenance (7 commands)
  - Category 6: Internal flags (3 flags + `--contract-version`)
  - Common output flags
  - Discovering element IDs and scope IDs
- [references/querying-the-index.md](references/querying-the-index.md) — 29 temporal subcommands deep-dive
  - Table of Contents
  - The event-sourced data model
  - Date and duration formats
  - Element ID grammar
  - Reading point-in-time snapshots (incl. `active-in`, the per-folder union)
  - Walking the timeline of one element
  - Window queries across the whole index
  - Diffing snapshots
  - Set queries — missing, never-current, multi-scope
  - Plugin and marketplace queries
  - Operations and retention
  - Putting it together — common recipes
  - External time-travel consumers — known limitations
