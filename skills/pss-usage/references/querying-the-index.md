# Querying the PSS Index Directly

## Table of Contents

- Slash command entry points
- Rust CLI subcommand reference
- Python helpers in `scripts/pss_cozodb.py`
- Quick recipes
- JSON export for `git diff` workflows

## Overview

The canonical PSS index is a CozoDB store (`pss-skill-index.db`) under `$CLAUDE_PLUGIN_DATA` (or `~/.claude/cache/` as fallback). The Rust binary exposes read-only subcommands you can invoke directly without going through the hook pipeline. All subcommands run in under 10 ms against an 8000+ entry index.

## Slash command entry points

Two wrapping slash commands surface the most common queries without needing to construct the binary path:

- `/pss-search <query>` — keyword / full-text search across names, descriptions, keywords. Wraps `pss search`. Use to answer "is there already a skill for X?"
- `/pss-added-since <when>` — list entries installed at or after the given time. Accepts RFC 3339 (`2026-04-16T22:00:00Z`), date-only (`2026-04-16`), or relative shorthand (`1d`, `2w`, `24h`, `30m`, `120s`). Use after `/cpv-manage` or `/pss-add-to-index` to verify indexing.

For deeper queries — structured filtering, timestamp windows, domain / language / keyword joins — invoke the Rust CLI directly.

## Rust CLI subcommand reference

Invoke via `"$CLAUDE_PLUGIN_ROOT/bin/pss-$(uname -s)-$(uname -m)" <subcommand>`.

### Overview and health

- `count [--json]` — total number of indexed entries
- `stats [--format table|json]` — per-type / per-source counts plus timestamp banner (oldest install, newest install, last reindex)
- `health [--verbose]` — probe the DB. Exit 0 = populated, 1 = empty / corrupt, 2 = missing. Intended for CI gates.

### Single-entry lookup

- `get <name> [--source S] [--json]` — fetch a single entry by name, with optional source disambiguation (`user`, `plugin:...`, `marketplace:...`). Default output is human-readable; `--json` emits the full row as JSON.
- `inspect <name>` — full details of a single entry for debugging

### Search and list

- `search <query> [--top N] [--type T] [--language L] [--domain D] [--format json|table]` — full-text search with optional structured filters (same matcher as the hook). Default output is JSON; pass `--format table` for a human-readable rendering.
- `list [--type T] [--top N] [--format ...]` — list entries with optional type filter
- `find-by-name <substring>` — case-insensitive name substring match
- `find-by-keyword <kw>` — exact keyword match via the `skill_keywords` index
- `find-by-domain <d>` — entries gated by or tagged with the given domain
- `find-by-language <l>` — entries targeting the given programming language

### Timestamp-windowed queries

All three accept `--limit N` (default 50) and `--json` (boolean; default is human-readable table).

- `list-added-since <when>` — entries whose `first_indexed_at` >= `<when>`
- `list-added-between <start> <end>` — entries whose `first_indexed_at` is in the closed interval
- `list-updated-since <when>` — entries whose `last_updated_at` >= `<when>`, i.e. "what changed in the last reindex?"

`<when>` formats: RFC 3339 (`2026-04-16T22:00:00Z`), date-only (`2026-04-16`, interpreted as UTC midnight), or relative shorthand (`1d`, `2w`, `24h`, `30m`, `120s`). Invalid input fails fast — there is no silent fallback to "now".

### Export

- `export --json [--path P]` — opt-in JSON snapshot dump of the CozoDB. The runtime hook no longer reads JSON — this exists purely so power users can `git diff` successive snapshots of the index.

All query subcommands are read-only. Full help: `"$CLAUDE_PLUGIN_ROOT/bin/pss-$(uname -s)-$(uname -m)" --help`.

## Python helpers in `scripts/pss_cozodb.py`

For scripting, the Python module re-exports the same queries as regular functions backed by `pycozo[embedded]`. All helpers accept an optional `db=` parameter so you can batch multiple queries under a single open DB handle.

### Count and health

- `count_skills()` — total entry count
- `db_is_healthy()` — boolean health probe

### Timestamp-windowed lookups

- `added_since(since, limit=None)` — entries whose `first_indexed_at` >= `since`
- `added_between(start, end, limit=None)` — entries whose `first_indexed_at` is in `[start, end]`
- `updated_since(since, limit=None)` — entries whose `last_updated_at` >= `since`

### Search helpers (seven dimensions)

- `search_by_name(pattern, limit=100)` — case-insensitive name substring
- `search_by_type(elem_type, limit=500)` — filter by `skill` / `agent` / `command` / `rule` / `mcp` / `lsp`
- `search_by_keyword(keyword, limit=100)` — exact keyword match
- `search_by_domain(domain, limit=200)` — domain gate
- `search_by_language(language, limit=500)` — programming language
- `search_by_description(text, limit=100)` — description substring (Python-side O(n) fallback)
- `search_full_text(query, limit=100)` — multi-token search across name + description + keywords

### Single-entry and full-scan

- `get_by_name(name, source=None)` — lightweight metadata lookup (name, type, source, path, description)
- `get_entry_by_name(name, source=None)` — full 33-column entry (keywords, intents, languages, frameworks, etc.)
- `get_all_entries(type_filter=None)` — full-scan returning `{name: entry}` mapping

Import with `from pss_cozodb import added_since, search_by_type, get_by_name`.

## Quick recipes

```bash
# What did I install today?
"$CLAUDE_PLUGIN_ROOT/bin/pss-darwin-arm64" list-added-since 1d

# Find every skill that mentions docker
"$CLAUDE_PLUGIN_ROOT/bin/pss-darwin-arm64" search docker --top 10

# Is a specific skill indexed?
"$CLAUDE_PLUGIN_ROOT/bin/pss-darwin-arm64" get tailwind-4-docs

# CI gate: exit non-zero if the DB is missing or empty
"$CLAUDE_PLUGIN_ROOT/bin/pss-darwin-arm64" health --verbose

# What changed in the last reindex?
"$CLAUDE_PLUGIN_ROOT/bin/pss-darwin-arm64" list-updated-since 24h

# Python scripting: summarise recent installs
python3 -c "from pss_cozodb import added_since; import json; print(json.dumps(added_since('1d'), indent=2))"

# Python scripting: find all skills in a domain
python3 -c "from pss_cozodb import search_by_domain; import json; print(json.dumps(search_by_domain('devops'), indent=2))"
```

## JSON export for `git diff` workflows

The legacy `skill-index.json` file is no longer generated automatically. Run `pss export --json` after a reindex to produce a JSON snapshot suitable for `git diff` or archival. The export goes to `$CLAUDE_PLUGIN_DATA/skill-index.export.json` by default; override with `--path`. The runtime hook path is entirely CozoDB — deleting the exported JSON is harmless.
