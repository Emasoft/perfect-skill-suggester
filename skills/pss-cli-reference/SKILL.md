---
name: pss-cli-reference
description: "Use when the user wants to query the PSS index, search/list/inspect elements, run lifecycle or history queries, build a plugin from a profile, or anywhere a `pss …` CLI command is needed. Loaded by pss-agent-profiler."
user-invocable: false
context: fork
---

# PSS CLI Reference Skill

**Loaded by `pss-agent-profiler`** and **Used by** any agent that needs to route a natural-language request to the PSS CLI surface (62 subcommands).

## Overview

The PSS Rust binary (`bin/pss-<platform>-<arch>`) exposes 62 read-only subcommands plus three internal flags across six categories: search/inspect, find-by-attribute, lifecycle filters, temporal queries, indexing/maintenance, and plugin authoring (slash-command wrapped). All query subcommands default to JSON, accept `--format table` for human display, and complete in <10 ms against an 8000+ entry index. Canonical store: CozoDB at `$CLAUDE_PLUGIN_DATA/pss-skill-index.db` (fallback `~/.claude/cache/`).

## Prerequisites

- PSS plugin enabled (`/plugin list`).
- Index healthy: `pss health --verbose`; if empty, run `/pss-reindex-skills`.
- Binary at `$CLAUDE_PLUGIN_ROOT/bin/pss-<platform>-<arch>`.

## Instructions

When a request matches the decision table, route via these numbered steps:

1. Classify the intent against the leftmost column of the [Quick decision table](#quick-decision-table).
2. Pick the subcommand (or its slash-command wrapper if listed).
3. Resolve the binary: `BIN="$CLAUDE_PLUGIN_ROOT/bin/pss-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"`.
4. Run with appropriate flags — `--format table` for display, `--format json` for piping, `--limit N` to cap, `--as-of <DATE>` for point-in-time.
5. Inspect the result. Empty result sets exit 0 with `[]` (JSON) or empty table.
6. Verify termination: results returned and rendered; for maintenance commands the exit code is 0 and stderr is empty.
7. Hand off — if the user wants follow-up action (open a file, install a plugin), invoke the matching slash command.

For ready-to-paste shell recipes covering inventory, find-a-skill, history, plugin authoring, and maintenance, see [references/workflows.md](references/workflows.md).

## Quick decision table

| User says… | Command |
|---|---|
| "what's installed" | `pss list`, `pss stats`, `pss by-plugin <name>` |
| "find a skill that does X" | `pss search "X"`, `pss find-by-keyword X`, `/pss-search X` |
| "show me the details of X" | `pss inspect X`, `pss get X`, `/pss-get-description X` |
| "languages / frameworks / tools covered" | `pss coverage`, `pss vocab languages` |
| "skills for Python / React / Docker / Linux" | `pss find-by-language python`, `find-by-framework react`, `find-by-tool docker`, `find-by-platform linux` |
| "installed since last week" | `pss list-added-since 1w`, `/pss-added-since 1w` |
| "changed since last reindex" | `pss list-updated-since 24h`, `pss last-changes`, `pss changes-summary --window 24h` |
| "snapshot at \<date\>" | `pss as-of <DATE>`, `pss show X --as-of <DATE>` |
| "history of X" | `pss timeline X`, `pss version-history X`, `pss lifespan X` |
| "diff X between two dates" | `pss diff X <D1> <D2>`, `pss compare-snapshots <D1> <D2>` |
| "what disappeared" | `pss removed-since <DATE>`, `pss currently-missing-but-once-was` |
| "duplicate skills across scopes" | `pss dedup-candidates`, `pss multi-scope <NAME>`, `pss scope-diff <S1> <S2>` |
| "what's in plugin / marketplace X" | `pss by-plugin <name>`, `pss by-marketplace <name>`, `pss plugin-history <name>` |
| "tune an agent profile" | `/pss-setup-agent <agent>` (fast: `--fast`) |
| "change an existing profile" | `/pss-change-agent-profile <profile.toml>` |
| "make a plugin from this profile" | `/pss-make-plugin-from-profile <profile.toml>` |
| "rebuild index" | `/pss-reindex-skills`, `pss reindex [--dry-run]` |
| "index health / DB stats" | `pss health [--verbose]`, `pss db-stats`, `pss stats-by-scope` |
| "export the index" | `pss export --json [--path P]` |
| "prune history" | `pss prune-history [--dry-run]`, `pss retention [--set 9m]` |

Date formats: RFC 3339 (`<YYYY-MM-DD>T<HH:MM:SS>Z`), date-only (`<YYYY-MM-DD>` interpreted as UTC midnight), relative (`1d`, `2w`, `24h`), or tokens (`now`, `yesterday`).

## Error Handling

- **Binary not found** → check `$CLAUDE_PLUGIN_ROOT/bin/` for your platform; rebuild with `uv run scripts/pss_build.py`.
- **`health` exit 2 (missing)** → `/pss-reindex-skills` to build the DB.
- **`health` exit 1 (empty/corrupt)** → delete `$CLAUDE_PLUGIN_DATA/pss-skill-index.db` then reindex.
- **`get` / `inspect` returns nothing** → `find-by-name <substring>` to verify the name; try `--source` to disambiguate scopes.
- **Invalid date** → temporal commands fail fast with stderr parse error; no silent fallback.

## Output

Query subcommands accept `--format json` (default) or `--format table` (human-readable). JSON is machine-readable; tables use Unicode box drawing with bold header rows. Empty result sets exit 0 with `[]` (JSON) or an empty table.

## Examples

```bash
BIN="$CLAUDE_PLUGIN_ROOT/bin/pss-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"

"$BIN" list-added-since 1d
"$BIN" search docker --top 5 --format table
"$BIN" get tailwind-4-docs --json
"$BIN" version-history skill:python@plugin:perfect-skill-suggester:
"$BIN" compare-snapshots 1mo now --format table
```

## Resources

- Architecture overview: docs/PSS-ARCHITECTURE.md
- Full CLI reference: docs/pss-cli-reference.md (rebuilt in v3.7 to cover every subcommand)
- Companion skill: pss-usage (interpreting suggestions and troubleshooting)
- Authoring guide: pss-authoring

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
  - Category 1: Search and inspect (12 commands)
  - Category 2: Find by attribute (7 commands)
  - Category 3: Lifecycle filters (3 commands)
  - Category 4: Temporal queries (28 commands)
  - Category 5: Indexing and maintenance (7 commands)
  - Category 6: Internal flags (3 flags)
  - Common output flags
  - Discovering element IDs and scope IDs
- [references/querying-the-index.md](references/querying-the-index.md) — 28 temporal subcommands deep-dive
  - Table of Contents
  - The event-sourced data model
  - Date and duration formats
  - Element ID grammar
  - Reading point-in-time snapshots
  - Walking the timeline of one element
  - Window queries across the whole index
  - Diffing snapshots
  - Set queries — missing, never-current, multi-scope
  - Plugin and marketplace queries
  - Operations and retention
  - Putting it together — common recipes
