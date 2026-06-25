# PSS CLI Reference

The `pss` binary is a Rust CLI that backs every PSS feature: the hook hot path,
agent profiling, temporal history queries, and ad-hoc index inspection. It
exposes **64 subcommands** in six functional groups, plus three internal flags
reserved for orchestration callers and one `--contract-version` probe flag.

Most commands return JSON by default. Newer commands also accept `--format
table` for human inspection; older lifecycle/find-by commands use a simpler
`--json` toggle.

---

## Quick-Start Decision Tree

| You want to... | Use |
|----------------|-----|
| Free-text search the index | [`pss search`](#pss-search) |
| List everything of a type | [`pss list`](#pss-list) |
| Look up one element | [`pss get`](#pss-get) / [`pss inspect`](#pss-inspect) |
| Tooltip-sized metadata | [`pss get-description`](#pss-get-description) |
| Filter by framework / language / tool | [`pss find-by-*`](#find-by-attribute) |
| What changed since yesterday? | [`pss list-added-since`](#pss-list-added-since) |
| What did the last reindex touch? | [`pss last-changes`](#pss-last-changes) |
| Snapshot index state on a past date | [`pss as-of`](#pss-as-of) |
| What's active in a project folder at a date | [`pss active-in`](#pss-active-in) |
| Canonical resolved DB path | [`pss db-path`](#pss-db-path) |
| Scope-path slug for a project folder | [`pss project-slug`](#pss-project-slug) |
| Full event log for one element | [`pss timeline`](#pss-timeline) |
| Diff one element over time | [`pss diff`](#pss-diff) |
| Compare two scopes | [`pss scope-diff`](#pss-scope-diff) |
| Health probe | [`pss health`](#pss-health), [`pss stats`](#pss-stats) |
| Force reindex | [`pss reindex`](#pss-reindex) |
| Compact event history | [`pss prune-history`](#pss-prune-history) |

---

## Identifiers

| Identifier | Shape | Where used | Example |
|------------|-------|------------|---------|
| 13-char ID | base36 FNV-1a hash | `inspect`, `resolve`, search/list output | `1o7bxu6yv8aj8` |
| Event-style element_id | `<type>:<name>@<scope>:<scope_path_slug>` | every temporal command | `skill:react@user:` |
| Plugin composite | `<plugin>@<marketplace>` | `plugin-history`, `enabled-where` | `perfect-skill-suggester@emasoft-plugins` |

The 13-char ID derives from FNV-1a 64-bit hash of `(name, source)` with a
`0xFF` separator byte — deterministic, collision-free across the 64-bit space
(1.8 × 10¹⁹). Use `pss inspect <name>` to discover both identifier forms for
follow-up calls.

For temporal commands, `<scope>` is one of `user`, `project`, `local`,
`plugin`, `marketplace`; `<type>` is `skill`, `agent`, `command`, `rule`,
`mcp`, `lsp`, `hook`, `plugin`, `monitor`, `output-style`, `theme`,
`marketplace`.

---

## Date/Time Formats

| Form | Example |
|------|---------|
| RFC 3339 | `2026-03-14T12:00:00Z` |
| Date only | `2026-03-14` (midnight UTC) |
| Relative | `1d`, `2w`, `24h`, `30m`, `120s` |
| Keyword | `now`, `yesterday` |
| Duration (retention) | `P9M`, `P30D`, `9m`, `30d`, `1y` |

`as-of`, `show`, `size-at`, `tokens-at` default `--as-of` to `now`.
`changes-summary` defaults `--window` to `24h`. Windowed queries
(`[start, end]`) are inclusive on both endpoints.

---

## Search & Inspect

12 commands for finding and inspecting elements.

### `pss search`

Full-text search across name, description, and keywords with attribute
filters. Filter flags: `--type` (string, all — `skill`/`agent`/`command`/
`rule`/`mcp`/`lsp`), `--domain`, `--language`, `--framework`, `--tool`,
`--category`, `--file-type`, `--keyword`, `--platform` (all string, all,
filter by that attribute). Plus `--top` (int, default 20) and `--format`
(string, default `json` — `json` or `table`).

**Synopsis:** `pss search [OPTIONS] <QUERY>`

```bash
pss search "authentication" --type skill --top 10
pss search "deploy" --framework kubernetes --platform cloud
```

**Output:** `[{"id":"...","name":"auth0-authentication","type":"skill","score":0.83}]`

**When to use:** First port of call for any free-text discovery.

---

### `pss list`

List entries by attribute filters (no text query). Shares all
`pss search` filter flags (`--type`, `--domain`, `--language`,
`--framework`, `--tool`, `--category`, `--file-type`, `--keyword`,
`--platform`). Plus `--source-prefix` (string, all — filter where `source`
starts with prefix, e.g. `plugin:`, `marketplace:emasoft-plugins/`),
`--sort` (string, default `name` — `name` or `category`), `--top` (int,
default 50), `--format` (string, default `json`).

**Synopsis:** `pss list [OPTIONS]`

```bash
pss list --type mcp
pss list --type skill --language python --category security
pss list --source-prefix "plugin:emasoft-plugins/" --top 100
```

**Output:** Array of `{id, name, type, category, ...}` objects.

**When to use:** Bulk enumeration for dashboards, audits, plugin-scoped audits.

---

### `pss inspect`

Show all fields of a single entry by name or ID. Flag: `--format` (string,
default `json`).

**Synopsis:** `pss inspect [OPTIONS] <NAME>`

```bash
pss inspect flutter-expert
pss inspect 1o7bxu6yv8aj8 --format table
```

**Output:** Single JSON object with all fields — id, path, type, source,
description, tier, boost, keywords, intents, languages, frameworks,
platforms, domains, `co_usage` chains. If multiple entries share the name
across sources, returns an array (JSON) or each entry separately (table).

**When to use:** Deep-dive on a candidate before adding to `.agent.toml`.

---

### `pss compare`

Side-by-side comparison of two entries — shared, unique, and scalar diffs.
Flag: `--format` (string, default `json`).

**Synopsis:** `pss compare [OPTIONS] <NAME1> <NAME2>`

```bash
pss compare auth0-authentication clerk-authentication
pss compare 1o7bxu6yv8aj8 r5ur3ulziqud --format table
```

**Output:** `{"entry_a":{...},"entry_b":{...},"shared":{...},"unique_a":{...},"unique_b":{...},"scalar_diffs":{"boost":[0,2]}}`

**When to use:** Pick between two near-equivalent candidates.

---

### `pss stats`

Index statistics — counts by type, source, domain, category, language,
framework, platform, tool. Flag: `--format` (string, default `json`).

**Synopsis:** `pss stats [OPTIONS]`

```bash
pss stats
pss stats --format table
```

**Output:** `{"total":9252,"by_type":{"skill":5577,"agent":1566,...},"by_language":{"typescript":1834,"python":1622,...}}`

**When to use:** First step of any audit — detect anomalies fast.

---

### `pss vocab`

Enumerate distinct values for a field — the "menu" of valid filters.
Valid fields: `languages`, `frameworks`, `tools`, `services`, `domains`,
`keywords`, `intents`, `platforms`, `file-types`, `categories`, `types`.
Flags: `--type` (string, all), `--top` (int, default 50), `--format`
(string, default `json`).

**Synopsis:** `pss vocab [OPTIONS] <FIELD>`

```bash
pss vocab languages
pss vocab frameworks --type mcp
pss vocab domains --top 30
```

**Output:** `[{"value":"python","count":1622}, ...]`

**When to use:** Discover valid `--language` / `--framework` values before
running `pss search` or `pss list`.

---

### `pss coverage`

Per-type coverage breakdown — what's covered/uncovered. Flags: `--type`
(string, all — `skill`/`agent`/`command`/`rule`/`mcp`/`lsp`), `--format`
(string, default `json`).

**Synopsis:** `pss coverage [OPTIONS]`

```bash
pss coverage --type skill
pss coverage --type agent
```

**Output:** `{"type":"skill","languages":{"covered":42,...},"frameworks":{"covered":87},"domains":{"covered":38}}`

**When to use:** Audit gaps before profiling an agent — warn users when
skill coverage is sparse for their stack.

---

### `pss resolve`

Resolve IDs or names to on-disk file paths. Flag: `--format` (string,
default `json`).

**Synopsis:** `pss resolve [OPTIONS] [IDS]...`

```bash
pss resolve 1o7bxu6yv8aj8
pss resolve 1o7bxu6yv8aj8 r5ur3ulziqud 3gg562reilpd9
```

**Output:** `[{"id":"...","name":"...","path":"/Users/.../SKILL.md","type":"...","description":"..."}]`

**When to use:** Final step before reading actual SKILL.md/agent files.

---

### `pss get-description`

Lightweight metadata lookup for tooltips, UI panels, token-efficient agent
context. Flags: `--batch` (flag, off — treat `<NAMES>` as comma-separated;
return array), `--format` (string, default `json`). On ambiguity (multiple
sources match), returns `"ambiguous": true` with a `matches` array —
disambiguate via `plugin-name:element-name` or 13-char ID. If no match in
the skill index, falls back to the `rules` CozoDB table.

**Synopsis:** `pss get-description [OPTIONS] <NAMES>`

```bash
pss get-description react
pss get-description "cpv:skill-validation"
pss get-description "react,flutter,vue" --batch
```

**Output:** `{"name":"react","type":"skill","description":"...","source":"user","plugin":null,"trigger":["react","hooks","jsx"]}`

**When to use:** Cheaper than `inspect` when you need only description + type.

---

### `pss count`

Print the total entry count from the CozoDB. Flag: `--json` (flag, off —
emit `{"count": N}` instead of bare integer). Non-zero exit if DB is
missing or unreadable.

**Synopsis:** `pss count [OPTIONS]`

```bash
pss count
pss count --json
```

**Output:** `9252` (or `{"count":9252}` with `--json`).

**When to use:** Liveness check + shell pipeline integration.

---

### `pss get`

Fetch a single entry by exact name, with source disambiguation. Flags:
`--source` (string, any — restrict to specific source), `--json` (flag,
off — JSON output, default is human-readable text).

**Synopsis:** `pss get [OPTIONS] <NAME>`

```bash
pss get react
pss get react --source user --json
```

**Output (JSON):** `{"name":"react","type":"skill","source":"user","path":"/.../SKILL.md","description":"..."}`

**When to use:** Exact-name lookup; prefer `get-description` if you need
only lightweight metadata.

---

### `pss health`

DB health probe. Flag: `--verbose` (flag, off — print a one-line
diagnostic). Exit codes: `0` populated; `1` empty/corrupt; `2` missing.

**Synopsis:** `pss health [OPTIONS]`

```bash
pss health
pss health --verbose
```

**Output (with `--verbose`):** `db=ok count=9252 path=/Users/.../pss-skill-index.db`

**When to use:** Pre-flight in CI / hook startup.

---

### `pss db-path`

Print the canonical resolved path to the CozoDB store (`pss-skill-index.db`),
applying the same `$CLAUDE_PLUGIN_DATA` → `~/.claude/cache/` fallback the
runtime uses. The binary is the single source of truth for this path — an
external consumer asks `db-path` instead of re-deriving the fallback chain
itself. Flag: `--format` (string, default text — `json` wraps it as
`{"db_path":"..."}`).

**Synopsis:** `pss db-path [--format json]`

```bash
pss db-path
pss db-path --format json
```

**Output:** `/Users/.../pss-skill-index.db` (or `{"db_path":"/Users/.../pss-skill-index.db"}`).

**When to use:** Locate the store for backup, inspection, or a health probe —
without hard-coding the fallback logic. Do NOT open the file directly; see
[External time-travel consumers — known limitations](#external-time-travel-consumers--known-limitations).

---

### `pss project-slug`

Compute the project scope-path slug for an absolute folder path — byte-for-byte
identical to the Python `_slugify_project_path` (`<basename>-<first8 sha256>`).
This is the slug that appears as the `scope_path` of `local`-scope rows and as
the `<scope_path_slug>` tail of a `project`/`local` element_id. Flag:
`--format` (string, default text — `json` wraps it as `{"slug":"..."}`).

**Synopsis:** `pss project-slug <ABS_PATH> [--format json]`

```bash
pss project-slug /Users/me/Code/my-project
pss project-slug /Users/me/Code/my-project --format json
```

**Output:** `my-project-1a2b3c4d` (or `{"slug":"my-project-1a2b3c4d"}`).

**When to use:** Build the `--scope-path` argument for `as-of`/`active-in`, or
map a folder to its local-scope rows, without reimplementing the slug hash.

---

## Find by Attribute

7 commands that filter by a single attribute. All accept `--limit` (int,
default 50) and `--json` (flag, off). All output plain text rows like
`flutter-expert (agent)` unless `--json` is set. The framework/tool/platform
variants were added in audit 20260514 as UX-8.

### `pss find-by-name`

Find entries whose name contains the substring (case-insensitive). Extra
flag: `--regex` (flag, off) — treat `<SUBSTRING>` as a Rust regex (matches
anywhere unless anchored). Invalid regex → exit 2 with parse-error.

**Synopsis:** `pss find-by-name [OPTIONS] <SUBSTRING>`

```bash
pss find-by-name auth
pss find-by-name "^react-" --regex
```

**When to use:** Quick "I roughly know the name" lookup.

---

### `pss find-by-keyword`

Find entries with an exact keyword match.

**Synopsis:** `pss find-by-keyword [OPTIONS] <KEYWORD>`

```bash
pss find-by-keyword authentication
pss find-by-keyword react --json
```

**When to use:** Exact keyword from `pss vocab keywords` (for substring use
`find-by-name`).

---

### `pss find-by-domain`

Find entries gated by or tagged with a domain.

**Synopsis:** `pss find-by-domain [OPTIONS] <DOMAIN>`

```bash
pss find-by-domain security
pss find-by-domain devops --limit 100 --json
```

**When to use:** Pull every skill in a domain — feeds the agent profiler's
domain-mismatch penalty calculations.

---

### `pss find-by-language`

Find entries targeting a programming language.

**Synopsis:** `pss find-by-language [OPTIONS] <LANGUAGE>`

```bash
pss find-by-language python
pss find-by-language rust --json
```

**When to use:** Language-scoped audits. Pair with `pss vocab languages`.

---

### `pss find-by-framework`

Find entries targeting a framework.

**Synopsis:** `pss find-by-framework [OPTIONS] <FRAMEWORK>`

```bash
pss find-by-framework react
pss find-by-framework django --limit 10
```

**When to use:** Framework-scoped filtering for `.agent.toml` profiles.

---

### `pss find-by-tool`

Find entries integrating with a given external tool.

**Synopsis:** `pss find-by-tool [OPTIONS] <TOOL>`

```bash
pss find-by-tool docker
pss find-by-tool kubernetes --limit 30
```

**When to use:** Discover skills wrapping a specific CLI tool.

---

### `pss find-by-platform`

Find entries targeting a platform (OS / runtime / cloud).

**Synopsis:** `pss find-by-platform [OPTIONS] <PLATFORM>`

```bash
pss find-by-platform linux
pss find-by-platform aws
```

**When to use:** Targeted scoping when the agent only runs on one platform.

---

## Lifecycle Filters

3 commands filtering elements by their lifecycle timestamps. All accept
relative shorthand, absolute dates, or RFC 3339. All share two flags:
`--limit` (int, default 50) and `--json` (flag, off). Output is plain text
lines like `react-19-rules (skill) — first indexed 2026-05-18T...`.

### `pss list-added-since`

List entries whose `first_indexed_at` ≥ the given datetime.

**Synopsis:** `pss list-added-since [OPTIONS] <WHEN>`

```bash
pss list-added-since 1d
pss list-added-since 2026-03-14
pss list-added-since 1w --json
```

**When to use:** "What did I install since yesterday?" Backs the janitor
`pss-added-since-last-summary` detector.

---

### `pss list-added-between`

List entries whose `first_indexed_at` falls within `[start, end]` inclusive.

**Synopsis:** `pss list-added-between [OPTIONS] <START> <END>`

```bash
pss list-added-between 2026-05-01 2026-05-15
pss list-added-between 7d 1d --json
```

**When to use:** Date-range audits — "what's been added since release X?"

---

### `pss list-updated-since`

List entries whose `last_updated_at` ≥ the given datetime.

**Synopsis:** `pss list-updated-since [OPTIONS] <WHEN>`

```bash
pss list-updated-since 1h
pss list-updated-since 2026-05-14 --json
```

**When to use:** Audit what the last reindex touched (vs creation time).

---

## Temporal Queries

32 commands for event-sourced history against `events` and
`elements_state` tables. The hot path never touches these — they're for
audits, dashboards, and forensic analysis. Most operate on event-style
element_ids; discover them via `pss show <name>` or `pss inspect <name>`.

### `pss as-of`

List every element installed and active at the given date. Flags:
`--type` (string, all), `--scope` (string, all —
`local`/`project`/`user`/`plugin`/`marketplace`), `--scope-path` (string,
all), `--limit` (int, **default unlimited** — pass `--limit N` to cap).

**Synopsis:** `pss as-of [OPTIONS] <DATE>`

```bash
pss as-of 2026-03-14
pss as-of yesterday --type skill
pss as-of now --scope user --limit 200
```

**Output:** per row, `skill:react@user: first_seen=2026-01-10 exists=true`.
Each row also carries:

- `first_seen` — the `observed_at` of the element's earliest install event.
- `first_seen_is_synthetic` — `true` when that instant is the v1→v2 migration
  placeholder (the element pre-existed the temporal index, so its "install"
  was backfilled, not really observed) rather than a real install event. Treat
  a synthetic `first_seen` as "at least this old", not as a true install date.

**When to use:** Reconstruct exactly what was installed at a past date.

> **Default changed (P-7):** `as-of` (and `active-in`) now return the FULL set
> by default — they no longer truncate at 1000. Pass `--limit N` to cap.

---

### `pss active-in`

List every component **active in a specific folder** at a point in time — the
single call an external "what's available here right now / on date T" consumer
should make. The result is the union of three membership sources:

1. **local-scope** rows whose `scope_path` equals the folder's slug (see
   [`pss project-slug`](#pss-project-slug)),
2. **all user-scope** rows (user-scope elements are active in every folder),
3. currently-enabled **plugin / marketplace** rows.

Row shape is identical to [`pss as-of`](#pss-as-of) (same `element_id`,
`first_seen`, `first_seen_is_synthetic`, `exists` fields). Flags: `--as-of`
(date, default `now`), `--limit` (int, **default unlimited**), `--format`
(string, default `json`).

**Synopsis:** `pss active-in [OPTIONS] <ABS_PATH>`

```bash
pss active-in /Users/me/Code/my-project
pss active-in /Users/me/Code/my-project --as-of 2026-03-14
pss active-in /Users/me/Code/my-project --limit 200 --format table
```

**Output:** per-row `element_id first_seen=... exists=true` lines (JSON array
with `--format json`), one row per active component.

**When to use:** Answer "which skills/agents/commands are in effect for folder
X at time T" in one call — instead of unioning `as-of --scope-path <slug>`,
`as-of --scope user`, and the enabled plugin/marketplace sets by hand.

> **Caveat (P-8):** the plugin/marketplace members reflect **current/global**
> enablement — per-project plugin enablement at a PAST instant is not yet
> recorded. See
> [External time-travel consumers — known limitations](#external-time-travel-consumers--known-limitations).

---

### `pss show`

Snapshot of an element at a point in time. Flag: `--as-of` (date, default `now`).

**Synopsis:** `pss show [OPTIONS] <ELEMENT_ID>`

```bash
pss show skill:react@user:
pss show skill:react@user: --as-of 2026-03-14
```

**Output:** JSON with `element_id`, `as_of`, `exists`, `enabled`,
`content_hash`, `size_bytes`, `tokens`, `frontmatter`.

**When to use:** Recover precise frontmatter / size on a past date.

---

### `pss size-at`

File size of an element at a point in time. Flag: `--as-of` (date, default `now`).

**Synopsis:** `pss size-at [OPTIONS] <ELEMENT_ID>`

Example: `pss size-at skill:react@user: --as-of 1w`

**Output:** Bare integer byte count.

**When to use:** Detect content-bloat trends.

---

### `pss tokens-at`

Approximate token count (cl100k) at a point in time. Flag: `--as-of` (date, default `now`).

**Synopsis:** `pss tokens-at [OPTIONS] <ELEMENT_ID>`

```bash
pss tokens-at skill:react@user:
pss tokens-at skill:react@user: --as-of 2026-01-01
```

**Output:** Bare integer token count.

**When to use:** Track skill cost-budget trends over versions.

---

### `pss diff`

Diff two snapshots of an element between two dates.

**Synopsis:** `pss diff <ELEMENT_ID> <DATE1> <DATE2>` (no flags)

```bash
pss diff skill:react@user: 2026-01-01 2026-04-01
pss diff skill:react@user: yesterday now
```

**Output:** Unified-diff-style block showing frontmatter and body changes —
**but only when blob capture is enabled.** Blob capture is off by default
(storage cost), so the `element_blobs` table is normally empty and `diff`
reports a **content-hash change**, not a textual delta. See
[External time-travel consumers — known limitations](#external-time-travel-consumers--known-limitations).

**When to use:** Forensic before-vs-after analysis. Combine with
`version-history` to find the right snapshot dates.

---

### `pss compare-snapshots`

Diff two whole-index snapshots — returns `only_at_date1`, `only_at_date2`,
`common_count`. Tier A F-5 from audit 20260514. Flags: `--type` (string,
all), `--limit` (int, default 5000 — caps elements scanned per snapshot).

**Synopsis:** `pss compare-snapshots [OPTIONS] <DATE1> <DATE2>`

```bash
pss compare-snapshots 7d now
pss compare-snapshots 2026-04-01 2026-05-01 --type skill
```

**Output:** `{"only_at_date1":[...],"only_at_date2":[...],"common_count":9248}`

**When to use:** Release-window delta audits.

---

### `pss timeline`

Full event timeline for one element (every `event_type`, no filtering).
Flag: `--limit` (int, default 200).

**Synopsis:** `pss timeline [OPTIONS] <ELEMENT_ID>`

```bash
pss timeline skill:react@user:
pss timeline agent:flutter-expert@plugin:perfect-skill-suggester:
```

**Output:** Per-event rows with timestamp, event_type, scan id, and
event-specific details.

**When to use:** Full audit trail for one element. For high-signal-only
history, use `pss version-history`.

---

### `pss lifespan`

First-seen and last-seen timestamps for one element (no flags).

**Synopsis:** `pss lifespan <ELEMENT_ID>`

Example: `pss lifespan skill:react@user:`

**Output:** `{"element_id":"...","first_seen":"...","last_seen":null}`
(null = still present).

**When to use:** Quick "is this still installed?" check.

---

### `pss version-history`

High-signal version history — filters timeline to `installed`,
`content_changed`, `description_changed`, `removed`. Each row carries the
content hash and diff JSON when present. Flag: `--limit` (int, default 500).
F-12 from audit 20260514.

**Synopsis:** `pss version-history [OPTIONS] <ELEMENT_ID>`

```bash
pss version-history skill:react@user:
pss version-history agent:flutter-expert@plugin:emasoft/pss: --limit 20
```

**Output:** Rows like `2026-02-02  content_changed  hash=cd34... diff={lines+:14,lines-:3}`.

**When to use:** Reconstruct version chain without size/enabled noise.

---

### `pss override-history`

Override start/end events for one element. Fires when a user-scope copy
shadows a plugin-scope element. Flag: `--limit` (int, default 200).

**Synopsis:** `pss override-history [OPTIONS] <ELEMENT_ID>`

Example: `pss override-history skill:react@user:`

**Output:** Rows like `2026-03-14T10:11:22Z  override_start  shadows=plugin:...`.

**When to use:** Debug "why does my user-scope skill behave differently
from the plugin version?"

---

### `pss enable-history`

Enable/disable events for one element. Flag: `--limit` (int, default 200).

**Synopsis:** `pss enable-history [OPTIONS] <ELEMENT_ID>`

```bash
pss enable-history skill:react@user:
pss enable-history plugin:perfect-skill-suggester@user:
```

**Output:** Rows like `2026-02-22T14:00:00Z  disabled`.

**When to use:** Track toggle history — "this used to work, now it doesn't".

---

### `pss scope-moves`

`scope_moved` events for a name — fires when the same name appears at a
different scope. Flags: `--type` (string, all), `--limit` (int, default 200).

**Synopsis:** `pss scope-moves [OPTIONS] <NAME>`

```bash
pss scope-moves react
pss scope-moves debug --type skill
```

**Output:** Rows like `2026-03-14T...  scope_moved  from=user to=project name=react`.

**When to use:** Track migration between scopes (e.g. user → project).

---

### `pss changed-between`

All content/size/frontmatter/description/path change events in
`[start, end]`. Flags: `--type` (string, all), `--limit` (int, default 1000).

**Synopsis:** `pss changed-between [OPTIONS] <START> <END>`

```bash
pss changed-between 2026-04-01 2026-05-01
pss changed-between 7d now --type skill
```

**Output:** Per-event rows with date, element_id, and event_type.

**When to use:** "What got updated this release window?"

---

### `pss installed-between`

Every install event in a time window. Flags: `--type` (string, all),
`--limit` (int, default 500).

**Synopsis:** `pss installed-between [OPTIONS] <START> <END>`

```bash
pss installed-between 7d now
pss installed-between 2026-01-01 2026-02-01 --type plugin
```

**Output:** Rows like `2026-01-10  installed  skill:react@user:`.

**When to use:** "What got added in this window?" report.

---

### `pss removed-between`

Every removal event in a time window. Flags: `--type` (string, all),
`--limit` (int, default 500).

**Synopsis:** `pss removed-between [OPTIONS] <START> <END>`

```bash
pss removed-between 7d now
pss removed-between 2026-01-01 2026-02-01 --type skill
```

**Output:** Rows like `2026-01-12  removed  skill:legacy-thing@user:`.

**When to use:** Audit cleanup deltas; post-mortem on accidental removals.

---

### `pss removed-since`

All `removed` events since a date (inclusive). Flag: `--limit` (int,
default 1000).

**Synopsis:** `pss removed-since [OPTIONS] <DATE>`

```bash
pss removed-since 30d
pss removed-since 2026-05-01
```

**Output:** Rows like `2026-05-02  removed  skill:legacy-thing@user:`.

**When to use:** Open-ended "what got removed lately?"

---

### `pss changes-summary`

Count events by `event_type` in a recent time window. Flags: `--window`
(duration, default `24h`), `--type` (string, all).

**Synopsis:** `pss changes-summary [OPTIONS]`

```bash
pss changes-summary
pss changes-summary --window 7d
pss changes-summary --window 30d --type plugin
```

**Output:** `{"window":"7d","installed":12,"content_changed":4,"description_changed":2,"removed":1}`

**When to use:** Daily/weekly dashboard widget.

---

### `pss currently-missing-but-once-was`

Elements that ever existed but aren't currently present.

**Synopsis:** `pss currently-missing-but-once-was [OPTIONS]`

Flags: `--type` (string, all), `--limit` (int, default 500).

```bash
pss currently-missing-but-once-was
pss currently-missing-but-once-was --type skill --limit 100
```

**Output:** Rows like `skill:legacy-thing@user:  last_seen=2026-04-01`.

**When to use:** Inventory drift — what used to exist but doesn't now?

---

### `pss never-current`

Alias for `pss currently-missing-but-once-was`. Same flags and output.

**Synopsis:** `pss never-current [OPTIONS]`

```bash
pss never-current
pss never-current --type plugin
```

**When to use:** Either phrasing is intuitive depending on the question.

---

### `pss multi-scope`

Find the same name living at multiple scopes simultaneously. Flag: `--type`
(string, all). (No `--limit` — returns all scope rows for the name.)

**Synopsis:** `pss multi-scope [OPTIONS] <NAME>`

```bash
pss multi-scope react
pss multi-scope debug --type skill
```

**Output:** Rows like `skill:react@user:  exists=true  enabled=true` and
`skill:react@project:/p1  exists=true  enabled=true`.

**When to use:** Detect override conflicts — user-scope shadowing
project-scope or plugin-scope.

---

### `pss dedup-candidates`

`(element_type, element_name)` pairs appearing in ≥2 scopes — catches
accidental duplicates. Tier A F-8 from audit 20260514. Flags:
`--min-count` (int, default 2), `--type` (string, all), `--limit` (int,
default 200).

**Synopsis:** `pss dedup-candidates [OPTIONS]`

```bash
pss dedup-candidates
pss dedup-candidates --type skill --min-count 3
```

**Output:** `[{"type":"skill","name":"react","scope_count":3,"scopes":["user","project","plugin"]}]`

**When to use:** Periodic hygiene audit.

---

### `pss enabled-where`

List scopes where the given element name is currently enabled. Flag:
`--type` (string, all).

**Synopsis:** `pss enabled-where [OPTIONS] <NAME>`

```bash
pss enabled-where react
pss enabled-where "perfect-skill-suggester@emasoft-plugins" --type plugin
```

**Output:** Rows showing each scope/scope_path where `exists=true AND
enabled=true`.

**When to use:** Confirm "where is this active right now?" Accepts plain
`<name>` or `<plugin>@<marketplace>` composite for plugins.

---

### `pss by-plugin`

List every currently-active element provided by a plugin. Flags: `--type`
(string, all), `--limit` (int, default 500).

**Synopsis:** `pss by-plugin [OPTIONS] <NAME>`

```bash
pss by-plugin perfect-skill-suggester
pss by-plugin code-auditor-agent --type skill
```

**Output:** Rows like `skill:pss-usage@plugin:perfect-skill-suggester:`.

**When to use:** "What does this plugin contribute?" Useful for context-cost
audits.

---

### `pss by-marketplace`

List every currently-active element from a marketplace. F-2 from audit
20260514. Flags: `--type` (string, all), `--limit` (int, default 500).

**Synopsis:** `pss by-marketplace [OPTIONS] <NAME>`

```bash
pss by-marketplace emasoft-plugins
pss by-marketplace anthropic-skills --type skill
```

**Output:** Rows like `plugin:perfect-skill-suggester@marketplace:emasoft-plugins`.

**When to use:** Track marketplace surface area.

---

### `pss scope-diff`

Show elements present in `scope1` but not `scope2`, and vice versa. F-6
from audit 20260514. Flags: `--type` (string, all), `--limit` (int,
default 500).

**Synopsis:** `pss scope-diff [OPTIONS] <SCOPE1> <SCOPE2>`

```bash
pss scope-diff user project
pss scope-diff user plugin --type skill
```

**Output:** `{"only_at_scope1":[...],"only_at_scope2":[...]}`

**When to use:** "What does the user scope have that project doesn't?"

---

### `pss stats-by-scope`

Count elements per scope (and per type within each scope). F-19 from
audit 20260514. Flag: `--type` (string, all).

**Synopsis:** `pss stats-by-scope [OPTIONS]`

```bash
pss stats-by-scope
pss stats-by-scope --type skill
```

**Output:** `{"user":{"skill":87,"agent":12,"rule":24},"plugin":{"skill":5471,"agent":1554}}`

**When to use:** Surface scope-level distribution.

---

### `pss marketplace-history`

All `marketplace_added` / `marketplace_removed` events. Flag: `--limit`
(int, default 500).

**Synopsis:** `pss marketplace-history [OPTIONS]`

```bash
pss marketplace-history
pss marketplace-history --limit 50
```

**Output:** Rows like `2026-01-15T...  marketplace_added  emasoft-plugins`.

**When to use:** Audit which marketplaces ever existed in the system.

---

### `pss plugin-history`

All events for one plugin (across versions / scopes / marketplaces).
DI-9 from audit 20260514 made plugins composite `<name>@<marketplace>`.
Accepts `<plugin>@<marketplace>` (exact) or `<plugin>` (cross-marketplace).
Flag: `--limit` (int, default 500).

**Synopsis:** `pss plugin-history [OPTIONS] <PLUGIN_NAME>`

```bash
pss plugin-history perfect-skill-suggester
pss plugin-history "perfect-skill-suggester@emasoft-plugins" --limit 20
```

**Output:** Rows like `2026-01-15  installed  perfect-skill-suggester@emasoft-plugins  v3.0.0`.

**When to use:** Track plugin install/upgrade history.

---

### `pss scan-log`

List recent scan runs (most recent first). Flag: `--limit` (int, default 20).

**Synopsis:** `pss scan-log [OPTIONS]`

```bash
pss scan-log
pss scan-log --limit 100
```

**Output:** Rows like `scan_id=01HM...  started=2026-05-19T...  duration=4.2s  events=12`.

**When to use:** Map a reindex to its scan_id for `pss changes-in-batch`.

---

### `pss db-stats`

Statistics about the temporal database (no flags).

**Synopsis:** `pss db-stats`

Example: `pss db-stats`

**Output:** `{"event_count":18421,"blob_count":9252,"blob_bytes":41382204,"oldest_event":"...","retention_window":"P9M"}`

**When to use:** Quick health/size check; pairs with `pss prune-history`.

---

### `pss changes-in-batch`

List every event from a specific scan_id. F-17 from audit 20260514.
Flag: `--limit` (int, default 500).

**Synopsis:** `pss changes-in-batch [OPTIONS] <SCAN_ID>`

Example: `pss changes-in-batch 01HM2YSAQK8R7XAYHQE2X1N8M0`

**Output:** Per-event rows with event_type and element_id.

**When to use:** "What happened during this specific reindex?" Pair with
`pss scan-log` to discover scan_ids.

---

### `pss last-changes`

Every event from the most recent scan — shortcut for
`changes-in-batch $(pss scan-log | latest)`. F-18 from audit 20260514.
Flag: `--limit` (int, default 500).

**Synopsis:** `pss last-changes [OPTIONS]`

```bash
pss last-changes
pss last-changes --limit 50
```

**Output:** Per-event rows with event_type and element_id.

**When to use:** First call after `pss reindex` to confirm what changed.

---

## External time-travel consumers — known limitations

The temporal commands above are designed for external "time-travel" consumers
(dashboards, audit tooling, a janitor lifecycle monitor). Four constraints
matter before you build on them:

### History only accrues when reindex runs (P-3)

Lifecycle history is written **only by a reindex** — `merge-events` emitting
events into the `events`/`elements_state` tables. PSS does **not** reindex on
every prompt: `_warm_index()` early-returns the moment the DB is non-empty, so
after the initial seed the ONLY writers are a manual `/pss-reindex-skills` or
the janitor **`pss-reindex-due` cron** detector.

**Consequence:** with a single scan, every element's "history" is one synthetic
`installed` event — there is nothing to diff or to trace. For real lifecycle
history to accumulate (and for `as-of`/`active-in`/`diff`/`timeline` to return
meaningful series), the janitor `pss-reindex-due` cron — or an equivalent
periodic manual `pss reindex` — **must** be running on a cadence. Treat a
recurring reindex as a hard prerequisite of any time-travel consumer.

### `pss diff` is hash-only unless blob capture is enabled (P-5)

`pss diff <EID> <D1> <D2>` produces a true textual delta **only when the
`element_blobs` table holds the two snapshots**. Blob capture is **off by
default** (the captured bodies are large and inflate the store), so
`element_blobs` is normally empty and `diff` reports **that the content hash
changed**, not what changed line-by-line. Do not expect a unified diff unless
blob capture has been explicitly enabled for the store you are querying.

### Never read `pss-skill-index.db` directly (P-10)

External consumers MUST NOT open `pss-skill-index.db` (or its CozoDB sidecars)
themselves. The store is guarded by an **undocumented `fcntl` advisory-lock
protocol** (`LOCK_SH` for readers, `LOCK_EX` for the atomic-rename writer); the
underlying cozo-ce engine **SIGABRTs on a read/write race** rather than
blocking. The native `pss` binary is the **only sanctioned reader** — it speaks
the lock protocol and survives concurrent reindexes.

Shell out to the binary with an **argument array**, never a shell string
(avoids quoting/injection):

```js
// Node — correct: argv array, no shell
const { execFile } = require("node:child_process");
execFile(BIN, ["active-in", absPath, "--format", "json"], (err, stdout) => { /* … */ });
```

```python
# Python — correct: list args, shell=False
import subprocess, json
out = subprocess.run([BIN, "active-in", abs_path, "--format", "json"],
                     capture_output=True, text=True, check=True)
rows = json.loads(out.stdout)
```

Resolve `BIN` to the platform binary, and resolve the store path via
[`pss db-path`](#pss-db-path) if you need it for backup/inspection — but read
its CONTENTS only through the binary.

### Per-project plugin enablement at a past instant is not recorded (P-8)

[`pss active-in`](#pss-active-in)'s plugin/marketplace members reflect
**current/global** enablement, not what was enabled in that specific folder at
the requested `--as-of` instant. The temporal index does not yet carry
per-project plugin enablement history, so the plugin/marketplace portion of an
`active-in` result is *not* time-travelled even when `--as-of` is in the past
(the local-scope and user-scope portions ARE). A focused follow-up issue tracks
the per-project enablement-history schema work; until it lands, treat the
plugin/marketplace rows as "currently enabled", not "enabled then".

---

## Indexing & Maintenance

7 commands that build, mutate, or clean the index.

### `pss index-rules`

Index rule files from `~/.claude/rules/` (user) and `.claude/rules/`
(project) into the `rules` CozoDB table. Rules aren't suggestable
(auto-injected by CC) but are needed for agent profiling and
`get-description` lookups. Flags: `--project-root` (path, default cwd),
`--format` (string, default `json`). Name from filename; description from
first non-heading, non-empty content line; idempotent.

**Synopsis:** `pss index-rules [OPTIONS]`

```bash
pss index-rules
pss index-rules --project-root /path/to/project
```

**Output:** `{"user_scope":{"indexed":24,"errors":0},"project_scope":{"indexed":3,"errors":0}}`

**When to use:** Run once before agent profiling. PSS plugin runs this
lazily on the profiler's behalf.

---

### `pss list-rules`

List all indexed rules with their descriptions. Flags: `--scope` (string,
all — `user` or `project`), `--format` (string, default `json`).

**Synopsis:** `pss list-rules [OPTIONS]`

```bash
pss list-rules
pss list-rules --scope user
pss list-rules --format table
```

**Output:** `[{"name":"claim-verification","scope":"user","description":"...","path":"/.../.md"}]`

**When to use:** Inventory rules before agent profiling.

---

### `pss export`

Export a JSON snapshot of the CozoDB for `git diff` workflows. As of
v2.11.0 (Phase B), the runtime hook no longer reads JSON — this exists
purely so power users can diff the index. Flags: `--json` (flag, on —
only json supported), `--path` (path, default
`$CLAUDE_PLUGIN_DATA/skill-index.export.json`).

**Synopsis:** `pss export [OPTIONS]`

```bash
pss export
pss export --path /tmp/snap.json
```

**Output:** `Exported 9252 entries to /Users/.../skill-index.export.json`.
Written atomically — readers never see a partial file.

**When to use:** `git diff` the snapshot across two states for forensic analysis.

---

### `pss reindex`

Run a full reindex — discover → enrich → emit events. Canonical trigger is
the janitor `pss-reindex-due` detector. Flag: `--dry-run` (flag, off —
print event set without writing).

**Synopsis:** `pss reindex [OPTIONS]`

```bash
pss reindex
pss reindex --dry-run
```

**Output:** Progress lines for discover/enrich/emit phases, ending with
`Scan complete: scan_id=01HM...`.

**When to use:** After installing new plugins or editing skills in place.
`/pss-reindex-skills` wraps this with progress UI.

---

### `pss prune-history`

Drop events older than the retention window (default: 9 months).
Idempotent. Flag: `--dry-run` (flag, off — print rows to drop without
committing).

**Synopsis:** `pss prune-history [OPTIONS]`

```bash
pss prune-history
pss prune-history --dry-run
```

**Output:** `Pruned 1421 events older than 2025-08-19T00:00:00Z`

**When to use:** Periodic temporal-store maintenance (janitor schedules this).

---

### `pss retention`

Get or set the retention window. Flag: `--set` (duration — ISO 8601 like
`P9M` or shorthand like `9m`, `30d`, `1y`; omit to print current value).

**Synopsis:** `pss retention [OPTIONS]`

```bash
pss retention
pss retention --set P12M
pss retention --set 30d
```

**Output:** `Current retention window: P9M (9 months)` or
`Retention window updated: P12M (12 months)`.

**When to use:** Shorten on disk pressure; lengthen for longer audit horizons.

---

### `pss merge-events`

Read JSONL observations from stdin and emit temporal events. The only
writer of the `events` table during normal reindex flow. For every
observation, reads `elements_state`, calls `compare_and_emit()`, persists
resulting events, refreshes `elements_state`. After stream end, issues a
`removed` event per element_id previously `exists=true` for a visited
scope_path but NOT observed in this scan. Records a `scan_runs` row.
Flags: `--batch-stdin` (flag, on), `--quiet` (flag, off).

**Synopsis:** `pss merge-events [OPTIONS]`

Example: `python scripts/pss_discover.py --jsonl | pss merge-events --quiet`

**Output:** `[merge-events] scan_id=01HM... events=12 duration=1.4s` plus
per-line stats unless `--quiet`.

**When to use:** Internal — invoked by `pss_reindex.py`. End users should
use `pss reindex` instead.

---

## Internal Flags

Three top-level flags reserved for orchestration callers. These do NOT
take a subcommand — they're flags on the `pss` binary itself.

### `--pass1-batch`

Run Pass 1 batch enrichment — read JSONL from stdin (one element per
line), enrich with deterministic keywords/category/intents/languages/
frameworks, output enriched JSONL to stdout. Replaces what used to be
Sonnet agent calls for 10K-scale indexing.

**Synopsis:** `pss --pass1-batch < input.jsonl > output.jsonl`

Example: `python scripts/pss_discover.py --jsonl | pss --pass1-batch | pss merge-events`

**Output:** One enriched JSONL line per input line.

**When to use:** Internal — `pss_reindex.py` Step 2.

---

### `--index-file`

Index a single element file: read `.md`, parse frontmatter + body, enrich,
output enriched JSON to stdout.

**Synopsis:** `pss --index-file <PATH>`

Example: `pss --index-file ~/.claude/skills/react/SKILL.md`

**Output:** Single JSON object representing the enriched element.

**When to use:** Internal — used by `/pss-add-element` and
`/pss-add-to-index`. For ad-hoc single-file enrichment.

---

### `--extract-prev-msg`

Extract the previous user message from a JSONL transcript using mmap +
backward scan — zero-copy, constant memory, ~3 ms on 500 MB files. Outputs
the 2nd most recent user message (skips current prompt). Empty string if
not found.

**Synopsis:** `pss --extract-prev-msg <PATH>`

Example: `pss --extract-prev-msg /path/to/transcript.jsonl`

**Output:** Plain-text content of the 2nd most recent user message.

**When to use:** Internal — used by `scripts/pss_hook.py` to avoid Python
I/O overhead on large transcripts. Critical to PSS's <30 ms hot-path budget.

---

### `--contract-version`

Print the binary's machine-readable contract triple and exit. An external
consumer probes this once at startup to confirm it understands the binary's
on-the-wire shapes before issuing any other call. This is a top-level flag,
not a subcommand — output is always JSON.

**Synopsis:** `pss --contract-version`

```bash
pss --contract-version
```

**Output:** `{"cli_version":"3.8.0","schema_version":"2","contract_version":"1"}`
where `cli_version` is the release version, `schema_version` is the CozoDB
schema generation, and `contract_version` is the CLI input/output contract
generation (bumped only on a breaking change to argument or JSON shapes).

**When to use:** Version-gate an external integration — fail fast if
`contract_version` differs from the one the consumer was written against.

---

## Top-Level Scoring Options

When invoked without a subcommand (legacy hook entry point), `pss` accepts:

| Flag | Type | Default | Purpose |
|------|------|---------|---------|
| `--incomplete-mode` | flag | off | Pass 2 co-usage analysis; ignore `co_usage`, use keyword similarity |
| `--top` | int | 4 | Top N candidates (reduced from 10 to save context) |
| `--min-score` | float | 0.5 | Minimum normalized score (0.0–1.0) |
| `--format` | string | `hook` | `hook` (default) or `json` |
| `--load-pss` | flag | off | Load and merge `.pss` matcher files |
| `--index` | path | `~/.claude/cache/skill-index.json` | Override (also `PSS_INDEX_PATH`) |
| `--registry` | path | `~/.claude/cache/domain-registry.json` | Override (also `PSS_REGISTRY_PATH`) |
| `--agent` | path/name | none | Generate `.agent.toml` profile for an agent |

Surface area for `pss_hook.py` and the agent-profiling pipeline; most
users don't invoke them directly. Use `/pss-setup-agent` for the
recommended user-facing entry point to agent profiling.

---

## Environment Variables

| Variable | Description | Since |
|----------|-------------|-------|
| `CLAUDE_PLUGIN_DATA` | Persistent data directory. Stores `skill-index.json`, `pss-skill-index.db`, CozoDB blobs. Falls back to `~/.claude/cache/` on older CC. | CC v2.1.78+ |
| `CLAUDE_PLUGIN_ROOT` | Root of installed plugin. Used to locate `VERSION` and `bin/`. | CC v2.1.0+ |
| `PSS_INDEX_PATH` | Override `skill-index.json` path. Same as `--index`. | v1.0.0+ |
| `PSS_REGISTRY_PATH` | Override `domain-registry.json` path. Same as `--registry`. | v2.7.0+ |
| `PSS_NO_LOGGING` | Set to `1` to disable activation logging. | v1.0.0+ |

`CLAUDE_PLUGIN_DATA` fallback: no manual migration needed —
`/pss-reindex-skills` writes to the new location automatically when the
env var is present.

---

## Typical Workflows

**Agent profiler shortlisting:** `pss stats` → `pss coverage --type skill`
→ `pss vocab frameworks --type skill` → `pss search "<topic>" --top 30` →
`pss list --type agent --language <lang> --framework <fw>` →
`pss compare <id1> <id2>` → `pss inspect <id>` → `pss resolve <ids>`.

**Audit drift since last release:** `pss changes-summary --window 7d` →
`pss scan-log --limit 14` → `pss last-changes` →
`pss currently-missing-but-once-was --limit 50` → `pss dedup-candidates`.

**Forensic version diff:** `pss show react` → `pss version-history
skill:react@user:` → `pss diff skill:react@user: 2026-04-01 2026-05-01` →
`pss compare-snapshots 2026-04-01 2026-05-01 --type skill`.

**Scope hygiene:** `pss enabled-where react` → `pss scope-diff user project
--type skill` → `pss scope-moves react` → `pss stats-by-scope`.

**Health check + cleanup:** `pss health` → `pss stats` → `pss db-stats` →
`pss retention --set P9M` → `pss prune-history --dry-run` →
`pss prune-history`.

---

## Notes on Undocumented Behaviour

`pss lifespan`, `pss diff`, `pss size-at`, `pss tokens-at` print minimal
help text — refer to this document for shape. `pss multi-scope` returns
all scope rows for the name (no `--limit`). Internal flags
(`--pass1-batch`, `--index-file`, `--extract-prev-msg`) are top-level
flags on the binary; they cannot combine with a subcommand. `pss help`
is not itself a subcommand — use `pss --help` or `pss <cmd> --help`.

Run `pss <command> --help` for the authoritative flag set on your
installed binary version.
