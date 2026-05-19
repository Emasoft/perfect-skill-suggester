# Querying the PSS Index — Temporal Queries

Focused guide to the 28 temporal subcommands. For the non-temporal verbs (search, list, find-by-*, etc.) see `quick-reference.md`.

## Table of Contents

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

## The event-sourced data model

Since v3.4.0, PSS stores extension lifecycle history as an append-only event log alongside a materialized current-state view.

**Two tables drive every temporal query:**

- `events` — append-only log. One row per observed change: `installed`, `removed`, `content_changed`, `size_changed`, `description_changed`, `frontmatter_changed`, `path_changed`, `scope_moved`, `enabled`, `disabled`, `marketplace_added`, `marketplace_removed`, `override_started`, `override_ended`. Each row has an `element_id`, a `scan_id` (ULID), a UTC timestamp, an `event_type`, and (where relevant) a diff JSON blob plus a content hash.
- `elements_state` — a materialized view over `events`. One row per `element_id` representing "what is true RIGHT NOW": `exists`, `enabled`, current `path`, current `content_hash`, `scope`, `scope_path`, last-seen timestamp.

Every reindex writes a new `scan_runs` row and emits exactly the events that changed since the last scan. Nothing in the DB is ever mutated in place — old rows stay until pruned by retention.

**Implications for queries:**

- `pss as-of <DATE>` asks `elements_state` to roll itself back to the snapshot at `<DATE>` by reading events with `ts <= DATE`.
- `pss timeline <ELEMENT_ID>` returns every event row for that element_id, ordered by `ts`.
- `pss changed-between` / `installed-between` / `removed-between` filter `events` directly without touching `elements_state`.
- The current-state hot path (`as-of now`, `list`, `get`) is one read against `elements_state`.

## Date and duration formats

All temporal subcommands accept date arguments in the same three forms:

- **RFC 3339**: `2026-04-16T22:00:00Z` (or with offset: `2026-04-16T18:00:00-04:00`). Parsed strict — invalid form is a fail-fast error, no silent fallback to "now".
- **Date-only**: `2026-04-16`. Interpreted as UTC midnight (`2026-04-16T00:00:00Z`).
- **Relative shorthand**: `1d`, `2w`, `24h`, `30m`, `120s` — interpreted as "now minus this duration". `mo` and `y` also accepted by some commands (`9m` may parse as either months or minutes depending on context — prefer ISO 8601 for retention windows: `P9M`, `P30D`, `P1Y`).
- **Special tokens**: `now`, `yesterday` (accepted by `as-of`, `show`, `size-at`, `tokens-at`, `compare-snapshots`).

Retention windows (`pss retention --set <DURATION>`) accept ISO 8601 durations (`P9M`, `P30D`, `P1Y`) or shorthand (`9m`, `30d`, `1y`). The default retention window is **9 months**; older events are dropped by `prune-history`.

## Element ID grammar

Many temporal subcommands take `<ELEMENT_ID>` rather than `<NAME>`. The grammar is:

```
<type>:<name>@<scope>:<scope_path_slug>
```

Components:

- `<type>` — one of `skill`, `agent`, `command`, `rule`, `mcp`, `lsp`, `hook`, `plugin`, `channel`, `monitor`, `output-style`, `theme`, `marketplace`.
- `<name>` — the element's filesystem-safe name.
- `<scope>` — one of `user`, `project`, `local`, `plugin`, `marketplace`.
- `<scope_path_slug>` — a slug of the scope path. Empty for `user` (just `<scope>:`). For `plugin` scope, this is the plugin's `<plugin-name>` (e.g. `plugin:perfect-skill-suggester:`). For `project` scope, it's a slug of the project's absolute path.

Examples:

- `skill:python@user:` — the `python` skill installed at the user scope.
- `skill:docker@plugin:perfect-skill-suggester:` — the `docker` skill provided by the PSS plugin.
- `agent:pss-agent-profiler@plugin:perfect-skill-suggester:` — the PSS agent profiler.
- `command:my-cmd@project:abc123def:` — a project-scoped command (path slug abbreviated).

**Discovery:** to find the exact element_id for a name, run `pss show <name>` — it prints the element_id in its output. Alternatively, `pss timeline <name>` will resolve the name when it's unambiguous; if multiple scopes have the same name it errors out and asks you to disambiguate. Use `pss multi-scope <NAME>` to enumerate the scopes for a name.

**Plugins are special**: stored as the composite `<plugin>@<marketplace>` (e.g. `perfect-skill-suggester@emasoft-plugins`). `pss plugin-history` accepts either the full composite form or just `<plugin>` (matches across all marketplaces).

## Reading point-in-time snapshots

The "as of `<DATE>`" family answers "what did the index look like back then?"

```bash
# Whole-index snapshot — every element installed and active at the given date
pss as-of 2026-04-01
pss as-of yesterday
pss as-of 2w                       # snapshot from 2 weeks ago
pss as-of 2026-04-01 --type skill  # restrict to skills
pss as-of 2026-04-01 --scope user --scope-path /Users/me

# One element at a point in time
pss show skill:my-skill@user: --as-of 2026-04-01

# Element's file size and token count at a point in time
pss size-at skill:my-skill@user: --as-of 2026-04-01
pss tokens-at skill:my-skill@user: --as-of 2026-04-01  # cl100k approximation
```

`--as-of` defaults to `now` on every command that accepts it — so `pss show X` is equivalent to `pss show X --as-of now`.

## Walking the timeline of one element

Three commands focus on the full lifecycle of one element_id.

```bash
# Every event row, ordered oldest -> newest
pss timeline skill:my-skill@user: --limit 200

# Filtered timeline — only the signal events: installed, content_changed,
# description_changed, removed. Each row carries content hash + diff JSON.
pss version-history skill:my-skill@user:

# First-seen and last-seen (or null) timestamps — quick "how old is this?"
pss lifespan skill:my-skill@user:

# Specialised slices
pss override-history skill:my-skill@user:   # override_started / override_ended
pss enable-history skill:my-skill@user:     # enabled / disabled events
pss scope-moves my-skill                    # scope_moved events for a name
```

`timeline` shows everything (including high-frequency size_changed noise from a file being edited repeatedly). `version-history` is the right tool for "what versions has this element gone through?" — it dedupes noise and the diff JSON column reconstructs the change story.

## Window queries across the whole index

These answer "what changed between two dates?" without focusing on one element.

```bash
# Every content/size/frontmatter/description/path changed event in the window
pss changed-between 2026-04-01 2026-05-01
pss changed-between 2026-04-01 2026-05-01 --type skill

# Every install / removal event in a window
pss installed-between 2026-04-01 2026-05-01
pss removed-between 2026-04-01 2026-05-01

# Everything removed since a date
pss removed-since 2026-04-01

# Count events by type in a recent window (default --window 24h)
pss changes-summary
pss changes-summary --window 7d --type skill

# Every event from the most recent scan (alias for `changes-in-batch $(latest)`)
pss last-changes

# Every event from one specific scan_id (read scan_id from `pss scan-log`)
pss changes-in-batch 01HX0M5K7QZ8P3R...
```

`changes-summary` is the right top-of-funnel for "anything weird in the last day?" — it returns one row per `event_type` with a count.

## Diffing snapshots

Two diff verbs, depending on whether you want one element or the whole index.

```bash
# Diff one element between two dates — shows the textual diff
pss diff skill:my-skill@user: 2026-04-01 2026-05-01

# Diff two whole-index snapshots — returns:
#   only_at_date1 — elements present at DATE1 but not at DATE2 (removed)
#   only_at_date2 — elements present at DATE2 but not at DATE1 (added)
#   common_count  — elements present at both
pss compare-snapshots 2026-04-01 2026-05-01
pss compare-snapshots 1mo now --type skill
```

`compare-snapshots` is the cheap, set-only diff. Use it for audits like "what got installed vs removed last month?". Use `pss diff` when you want the per-element textual delta.

## Set queries — missing, never-current, multi-scope

The DB remembers everything that has ever existed, so we can answer "what's gone?" and "what's duplicated?" questions.

```bash
# Elements that ever existed but aren't currently present.
# `never-current` is an alias for the same query.
pss currently-missing-but-once-was
pss currently-missing-but-once-was --type skill

# A name that lives at multiple scopes simultaneously (e.g. user/skill/foo AND
# plugin/skill/foo). The dedup signal — usually means an accidental override.
pss multi-scope foo
pss multi-scope foo --type skill

# Where is this element actually enabled right now?
pss enabled-where foo                # one row per scope/scope_path with exists+enabled
pss enabled-where foo --type skill

# A name that has moved scopes over time (user -> plugin, plugin -> user, etc.)
pss scope-moves foo

# Whole-index dedup audit — every (type, name) pair living in 2+ scopes.
pss dedup-candidates                 # --min-count 2 by default
pss dedup-candidates --min-count 3 --type skill

# Compare two scopes — what's in one but not the other.
pss scope-diff user project
pss scope-diff user plugin --type skill
```

`dedup-candidates` is the standard tool for "I have shadowing problems — find them all" audits. `multi-scope <NAME>` is the per-element view of the same data.

## Plugin and marketplace queries

Plugins and marketplaces have their own subset of temporal queries.

```bash
# Every currently-active element provided by one plugin
pss by-plugin perfect-skill-suggester
pss by-plugin perfect-skill-suggester --type skill

# Every currently-active element installed from one marketplace
pss by-marketplace emasoft-plugins

# Full plugin event history (every install / remove / scope_moved / etc.)
pss plugin-history perfect-skill-suggester
pss plugin-history perfect-skill-suggester@emasoft-plugins  # exact match form

# Every marketplace_added / marketplace_removed event ever
pss marketplace-history
```

`by-plugin` and `by-marketplace` are current-state queries (read `elements_state`). `plugin-history` and `marketplace-history` walk the event log.

## Operations and retention

Three commands manage the temporal DB itself.

```bash
# Run a full reindex — discover, enrich, emit events.
pss reindex                          # writes to the DB
pss reindex --dry-run                # prints the event set without writing
# Or use the slash command wrapper which adds progress UI:
/pss-reindex-skills

# Recent scan history — most recent first
pss scan-log --limit 10

# Temporal DB statistics: event count, blob count, blob bytes, oldest event,
# retention window
pss db-stats

# Trim old history (default retention: 9 months)
pss retention                        # print current window
pss retention --set 6m               # change it
pss prune-history --dry-run          # preview which rows would be dropped
pss prune-history                    # commit the deletion

# JSON snapshot for git-diff workflows (runtime hook no longer reads JSON;
# this exists only for power-user diffing).
pss export --json --path /tmp/pss-snapshot.json
```

`reindex` is the only thing that writes to the `events` table during normal operation — it streams JSONL discovered observations to `pss merge-events` internally. `prune-history` is idempotent and never deletes events newer than the retention window.

## Putting it together — common recipes

```bash
# Q: What got installed today?
pss installed-between 1d now

# Q: What changed in the last reindex specifically?
pss last-changes
# or, by scan_id:
SCAN_ID=$(pss scan-log --limit 1 | jq -r '.[0].scan_id')
pss changes-in-batch "$SCAN_ID"

# Q: Show me the version history of one element with hashes and diff JSON
pss version-history skill:python@plugin:perfect-skill-suggester:

# Q: What was true 1 month ago vs now?
pss compare-snapshots 1mo now --format table

# Q: Find every duplicate skill across scopes
pss dedup-candidates --type skill --min-count 2

# Q: Which skills are SHADOWING the user scope from a plugin?
pss multi-scope <name>
# or whole-index:
pss scope-diff plugin user --type skill

# Q: What disappeared since last week?
pss removed-since 1w
# or, with the start/end window form:
pss removed-between 1w now

# Q: When did the `python` skill first appear and was it ever removed?
pss lifespan skill:python@plugin:perfect-skill-suggester:

# Q: How big is the temporal DB getting?
pss db-stats
# If > 1GB, consider:
pss prune-history --dry-run    # preview
pss prune-history              # commit
# Or shorten the retention window first:
pss retention --set 6m
```

For non-temporal queries (`search`, `list`, `find-by-*`, plugin generation), see `quick-reference.md`. For the suggestion hot path itself, see the parent `SKILL.md`.
