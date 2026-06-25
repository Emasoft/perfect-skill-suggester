# PSS CLI Quick Reference

One-line cheat-sheet for every subcommand of the PSS Rust binary, grouped by the six categories used in the v3.7 reference.

Invoke as: `"$CLAUDE_PLUGIN_ROOT/bin/pss-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)" <subcommand>` — or alias to `pss` once.

## Table of Contents

- Category 1: Search and inspect (14 commands)
- Category 2: Find by attribute (7 commands)
- Category 3: Lifecycle filters (3 commands)
- Category 4: Temporal queries (29 commands)
- Category 5: Indexing and maintenance (7 commands)
- Category 6: Internal flags (3 flags + `--contract-version`)
- Common output flags
- Discovering element IDs and scope IDs

## Category 1: Search and inspect (14 commands)

General-purpose query verbs. They all read from the current snapshot (`elements_state` view) — no temporal cutoff.

| Command | One-line purpose |
|---|---|
| `pss search <QUERY>` | Full-text search across name, description, keywords. Filters: `--type`, `--domain`, `--language`, `--framework`, `--tool`, `--category`, `--file-type`, `--keyword`, `--platform`. `--top N` (default 20). |
| `pss list` | List entries with optional filtering and sorting. Same filter flags as `search`, plus `--source-prefix` and `--sort name\|category`. `--top N` (default 50). |
| `pss inspect <NAME>` | Show full details of a named entry (accepts name or 13-char ID). |
| `pss compare <NAME1> <NAME2>` | Side-by-side comparison of two entries (names or IDs). |
| `pss stats` | Index statistics — counts by type, domain, category, language, etc. |
| `pss vocab <FIELD>` | Enumerate distinct values for a field. Valid fields: `languages`, `frameworks`, `tools`, `services`, `domains`, `keywords`, `intents`, `platforms`, `file-types`, `categories`, `types`. |
| `pss coverage` | Per-type coverage breakdown: which languages, domains, frameworks are covered. Optional `--type`. |
| `pss resolve <IDS...>` | Resolve entry IDs (or names) to file paths — so you can read the actual SKILL.md / agent.md / command.md. |
| `pss get-description <NAMES>` | Lightweight metadata (description, type, plugin, keywords). `--batch` for comma-separated list. Designed for tooltips and token-efficient lookups. |
| `pss count` | Total entry count. Default = bare integer; `--json` = `{"count": N}`. Exits non-zero if DB missing/unreadable. |
| `pss get <NAME>` | Fetch one entry by exact name. `--source` to disambiguate (user / plugin:... / marketplace:...). `--json` for raw row. |
| `pss health` | Probe DB. Exit 0 = populated, 1 = empty/corrupt, 2 = missing. `--verbose` adds a one-line diagnostic. |
| `pss db-path` | Print the canonical resolved DB path (`$CLAUDE_PLUGIN_DATA` → `~/.claude/cache/` fallback, same as the runtime). `--format json` = `{"db_path":"..."}`. Locate the store — but read its contents only via this binary. |
| `pss project-slug <ABS_PATH>` | Compute a folder's scope-path slug (`<basename>-<first8 sha256>`, identical to Python `_slugify_project_path`). `--format json` = `{"slug":"..."}`. Use it to build `--scope-path` for `as-of`/`active-in`. |

## Category 2: Find by attribute (7 commands)

Focused single-attribute lookups. Faster than `search` when you already know the filter. All accept `--limit N` (default 50) and `--json`.

| Command | One-line purpose |
|---|---|
| `pss find-by-name <SUBSTRING>` | Case-insensitive name substring. `--regex` for a Rust regex pattern (anchored partial). |
| `pss find-by-keyword <KEYWORD>` | Exact keyword match via the `skill_keywords` index. |
| `pss find-by-domain <DOMAIN>` | Entries gated by or tagged with a domain (e.g. `security`, `devops`, `web`). |
| `pss find-by-language <LANGUAGE>` | Entries targeting a language (e.g. `python`, `rust`, `typescript`). |
| `pss find-by-framework <FRAMEWORK>` | Entries targeting a framework (e.g. `react`, `django`, `fastapi`, `rails`). |
| `pss find-by-tool <TOOL>` | Entries integrating with a tool (e.g. `git`, `docker`, `kubernetes`, `jq`). |
| `pss find-by-platform <PLATFORM>` | Entries targeting a platform (e.g. `linux`, `macos`, `windows`, `browser`, `aws`, `gcp`). |

## Category 3: Lifecycle filters (3 commands)

Simple "added since" / "added between" / "updated since" filters against `first_indexed_at` and `last_updated_at` columns. Accept `--limit` (default 50) and `--json`. Date formats: RFC 3339, `YYYY-MM-DD`, or relative shorthand (`1d`, `2w`, `24h`, `30m`, `120s`).

| Command | One-line purpose |
|---|---|
| `pss list-added-since <WHEN>` | Entries whose `first_indexed_at` >= `<WHEN>`. |
| `pss list-added-between <START> <END>` | Entries whose `first_indexed_at` falls within `[start, end]` (inclusive). |
| `pss list-updated-since <WHEN>` | Entries whose `last_updated_at` >= `<WHEN>`. "What changed in the last reindex?" |

## Category 4: Temporal queries (29 commands)

Event-sourced history queries. Each row reads from the `events` table and/or the materialized `elements_state` view. Date formats are the same as Category 3 plus the tokens `now` / `yesterday`. See `querying-the-index.md` for the full schema and date grammar.

> **History only accrues when reindex runs (P-3):** these series are meaningful only if a recurring reindex is running — the janitor `pss-reindex-due` cron, or a periodic manual `pss reindex`. With a single scan, every element's history is one synthetic `installed` event. And external consumers must read the store ONLY via this binary (it is `fcntl`-locked; a raw read races the writer and SIGABRTs). See `querying-the-index.md` → "External time-travel consumers — known limitations".

### Point-in-time snapshots

| Command | One-line purpose |
|---|---|
| `pss as-of <DATE>` | List every element installed and active at the given date. Filters: `--type`, `--scope`, `--scope-path`. `--limit` (**default unlimited**, P-7). Each row carries `first_seen` + `first_seen_is_synthetic` (true = v1→v2 migration placeholder, not a real install). |
| `pss active-in <ABS_PATH>` | Every component active in a FOLDER at a time = union of (a) local-scope rows for the folder slug, (b) all user-scope rows, (c) enabled plugin/marketplace rows. Same row shape as `as-of`. `--as-of <DATE>` (default `now`), `--limit` (default unlimited). Plugin/marketplace members reflect CURRENT enablement (P-8). |
| `pss show <ELEMENT_ID>` | Snapshot of one element. `--as-of <DATE>` (default `now`). |
| `pss size-at <ELEMENT_ID>` | File size at a date. `--as-of <DATE>`. |
| `pss tokens-at <ELEMENT_ID>` | Token count (cl100k approximation) at a date. `--as-of <DATE>`. |
| `pss diff <ELEMENT_ID> <DATE1> <DATE2>` | Diff snapshots of one element between two dates. **Hash-only unless blob capture is enabled** (`element_blobs` is empty by default → reports a content-hash change, not a textual delta) (P-5). |
| `pss compare-snapshots <DATE1> <DATE2>` | Diff two whole-index snapshots — `only_at_date1`, `only_at_date2`, `common_count`. `--type` filter. |

### Walking one element's timeline

| Command | One-line purpose |
|---|---|
| `pss timeline <ELEMENT_ID>` | Full event timeline (every event row). `--limit` (default 200). |
| `pss lifespan <ELEMENT_ID>` | First-seen and last-seen (or `null`) timestamps. |
| `pss version-history <ELEMENT_ID>` | Filtered timeline — only signal events (installed, content_changed, description_changed, removed). Each row carries content hash and diff JSON. |
| `pss override-history <ELEMENT_ID>` | Override start/end events for one element. `--limit` (default 200). |
| `pss enable-history <ELEMENT_ID>` | Enable/disable events for one element. `--limit` (default 200). |

### Window queries across the index

| Command | One-line purpose |
|---|---|
| `pss changed-between <START> <END>` | Every content/size/frontmatter/description/path changed event in `[start, end]`. `--type` filter. |
| `pss installed-between <START> <END>` | Every install event in `[start, end]`. `--type` filter. |
| `pss removed-between <START> <END>` | Every removal event in `[start, end]`. `--type` filter. |
| `pss removed-since <DATE>` | All `removed` events since `<DATE>` (inclusive). |
| `pss changes-summary` | Count events by event_type in a window. `--window 7d` (default `24h`). `--type` filter. |
| `pss last-changes` | Emit every event from the most recent scan. Shortcut for `changes-in-batch $(latest scan_id)`. |
| `pss changes-in-batch <SCAN_ID>` | Every event from one specific `scan_id`. |

### Set queries — missing, never-current, multi-scope

| Command | One-line purpose |
|---|---|
| `pss currently-missing-but-once-was` | Elements that ever existed but aren't currently present. `--type`, `--limit`. |
| `pss never-current` | Alias for `currently-missing-but-once-was`. |
| `pss multi-scope <NAME>` | Find the same name living at multiple scopes simultaneously. `--type` filter. |
| `pss enabled-where <NAME>` | List the scopes where this element is currently enabled (exists=true AND enabled=true). `--type` filter. |
| `pss scope-moves <NAME>` | All `scope_moved` events for a name. `--type` filter. |
| `pss dedup-candidates` | `(element_type, element_name)` pairs that appear in 2+ scopes. `--min-count` (default 2), `--type`, `--limit`. |
| `pss scope-diff <SCOPE1> <SCOPE2>` | Elements present in `scope1` but not `scope2`, and vice versa. `--type` filter. |

### Plugin / marketplace history

| Command | One-line purpose |
|---|---|
| `pss by-plugin <NAME>` | Every currently-active element whose `source` is `plugin:<NAME>`. `--type` filter. |
| `pss by-marketplace <NAME>` | Every currently-active element whose `source` starts with `marketplace:<NAME>`. `--type` filter. |
| `pss plugin-history <PLUGIN_NAME>` | All events for one plugin name (across versions/scopes). Accept either `<name>@<marketplace>` (exact) or `<name>` (any marketplace). |
| `pss marketplace-history` | All `marketplace_added` / `marketplace_removed` events. |

### Scope statistics + scan log + DB stats

| Command | One-line purpose |
|---|---|
| `pss scan-log` | Recent scan runs (most recent first). `--limit` (default 20). |
| `pss db-stats` | Statistics about the temporal DB: event count, blob count, blob bytes, oldest event, retention window. |
| `pss stats-by-scope` | Count elements per scope (and per type within each scope). JSON object keyed by scope. `--type` filter. |

## Category 5: Indexing and maintenance (7 commands)

Write-side and operational subcommands. Most users hit these through `/pss-reindex-skills`, not directly.

| Command | One-line purpose |
|---|---|
| `pss reindex` | Full reindex (discover → enrich → emit events). `--dry-run` prints events without writing. Suitable for cron via the janitor's `pss-reindex-due` detector. |
| `pss index-rules` | Index `~/.claude/rules/*.md` and `.claude/rules/*.md` into the `rules` table. `--project-root` for explicit project. Required before agent profiling. |
| `pss list-rules` | List all indexed rules with descriptions. `--scope user\|project` filter. |
| `pss merge-events` | Read JSONL observations from stdin and emit temporal events. `--batch-stdin` (default), `--quiet`. Only writer of the `events` table during normal reindex flow. |
| `pss prune-history` | Drop events older than the retention window (default 9 months). `--dry-run` previews. Idempotent. |
| `pss retention` | Get or set the retention window. `--set <DURATION>` accepts ISO 8601 (`P9M`, `P30D`) or shorthand (`9m`, `30d`, `1y`). |
| `pss export` | Export a JSON snapshot of the CozoDB for `git diff` workflows. `--json` (only format supported), `--path` (default `$CLAUDE_PLUGIN_DATA/skill-index.export.json`). Runtime hook no longer reads JSON — this exists for power users. |

## Category 6: Internal flags (3 flags + `--contract-version`)

These flags live on the top-level `pss` invocation rather than as subcommands. They drive the hook pipeline and indexing internals; user-facing usage is rare. `--contract-version` is the one exception meant for external callers.

| Flag | One-line purpose |
|---|---|
| `--pass1-batch` | Pass 1 batch enrichment. Reads JSONL on stdin, enriches each line with deterministic keywords/category/intents/languages/frameworks, writes enriched JSONL on stdout. Replaces the legacy Sonnet enrichment for 10K-scale indexing. |
| `--index-file <PATH>` | Index a single element file. Reads `.md`, parses frontmatter + body, runs Pass 1 enrichment, prints enriched JSON on stdout. Used to add one element without a full reindex. |
| `--extract-prev-msg <PATH>` | Extract the previous user message from a JSONL transcript file. Uses mmap + backward scan (zero-copy, constant memory, ~3 ms on 500 MB transcripts). Outputs the 2nd most recent user message text; empty string if not found. Used by the Python hook. |
| `--contract-version` | Print the binary's machine-readable contract triple and exit: `{"cli_version":...,"schema_version":"2","contract_version":"1"}`. Always JSON. An external integration probes this once to version-gate its assumptions about the CLI's argument/JSON shapes (`contract_version` bumps only on a breaking shape change). |

Other top-level flags (`--incomplete-mode`, `--top`, `--min-score`, `--format`, `--load-pss`, `--index`, `--registry`, `--agent`) configure the suggestion hot path that the `UserPromptSubmit` hook drives. They are documented inline in `pss --help` and rarely invoked manually.

## Common output flags

Most query subcommands accept some combination of these:

| Flag | Purpose |
|---|---|
| `--json` | Boolean flag: emit JSON instead of human-readable output. (Legacy form; being replaced by `--format` in v3.7.) |
| `--format json\|table` | Newer form: pick the output format explicitly. Default is `json` for most subcommands, `table` for `list`/`stats` and a few others. |
| `--limit N` / `--top N` | Cap rows returned. Defaults vary: 20 (`search`), 50 (most lists), 200 (timelines), 500 (window queries), 5000 (`compare-snapshots`). Snapshot verbs `as-of` / `active-in` default to **unlimited** (P-7). |
| `--type T` | Restrict to one element type: `skill`, `agent`, `command`, `rule`, `mcp`, `lsp`, `hook`, `plugin`, `channel`, `monitor`, `output-style`, `theme`, `marketplace`. |
| `--scope S` | Restrict to one scope: `user`, `project`, `local`, `plugin`, `marketplace`. |

JSON output is the contract for downstream tools (`jq`, scripts, the suggestion hook). Tables use Unicode box-drawing with bold header rows.

## Discovering element IDs and scope IDs

Many temporal subcommands take `<ELEMENT_ID>` rather than `<NAME>`. The grammar is:

```
<type>:<name>@<scope>:<scope_path_slug>
```

Examples:

- `skill:my-skill@user:`
- `skill:docker@plugin:perfect-skill-suggester:`
- `agent:pss-agent-profiler@plugin:perfect-skill-suggester:`
- `command:pss-reindex-skills@plugin:perfect-skill-suggester:`

To discover the exact element ID for a given name, run `pss show <name>` (it prints the element ID in its output), or `pss timeline` against any name to see the ID in the first event row. Plugin names are stored as the composite `<plugin>@<marketplace>` in `plugin-history` — pass either form (exact or just the plugin name).
