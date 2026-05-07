# TRDD-152e697f — PSS Temporal History Index (event-sourced)

**TRDD ID:** `152e697f-17ff-4e86-aed1-008af90e287a`
**Filename:** `design/tasks/TRDD-152e697f-17ff-4e86-aed1-008af90e287a-temporal-history-index.md`
**Tracked in:** this repo (design/tasks/ is git-tracked)
**Status:** Awaiting design approval (revision 2 — event-sourced model)
**Created:** 2026-05-07
**Revised:** 2026-05-07 (after user feedback: every event must be recorded, not only revisions)

## 1. User request (verbatim)

> Big change to the pss index db: index every Claude Code extension on the
> system AND track them and their changes over time. Don't delete on
> remove — annotate the datetime. Don't replace on update — keep the old
> entry and add a new one. Track every observable event: install, remove,
> enable, disable, scope move, override, marketplace add/remove, size
> change, content change, frontmatter change, etc. Lifecycle CLI queries
> must be instantaneous, no agent, no token waste. Add file size and
> tiktoken token count. Manual reindex for janitor cron. Configurable
> retention, default 9 months. Datetime precision = scan time of the
> indexer, not filesystem mtime.

## 2. Goal

Convert the PSS index from a current-state store into a **deterministic
event log** of every Claude Code extension on the system. Every reindex
emits zero or more events per element; the events table is append-only;
"current state" is materialized from the log. CozoDB Datalog answers
every lifecycle query in single-digit ms.

The model is event-sourcing (Datomic-style). The schema captures every
class of transition the user listed: install, remove, enable, disable,
content change, size change, scope move, override start/end, marketplace
register/unregister, plugin install/uninstall.

## 3. Non-goals

- Not a generic VCS — full body bytes are stored content-addressed once
  per unique hash (not per revision); recover original content via the
  source-file's own git history if older than retention.
- Not real-time — capture is at reindex time only. Event timestamp =
  scan_run.finished_at (per user instruction: precision unimportant).
- Suggestion hot path is unchanged — scoring still queries
  `elements_state` (current view), never the event log directly.

## 4. Element types covered

Currently indexed: skill, agent, command, rule, mcp, lsp.
Adding: hook, plugin, channel, monitor, output-style, marketplace.

| Type | Discovery source |
|------|-------------------|
| skill | already covered |
| agent | already covered |
| command | already covered |
| rule | already covered |
| mcp | already covered (`~/.claude.json` mcpServers + plugin `.mcp.json`) |
| lsp | already covered |
| **hook** | parse hooks blocks from settings.local.json, settings.json (user + project), plugin `hooks/hooks.json` |
| **plugin** | `~/.claude/plugins/installed_plugins.json` v2; one row per (plugin, scope) |
| **channel** | scan settings.json for `channelsEnabled` + the active channels list |
| **monitor** | `plugin.json[experimental.monitors]` (CC v2.1.129+) |
| **output-style** | `~/.claude/output-styles/*.md` + plugin `output-styles/` |
| **marketplace** | `~/.claude.json` `extraKnownMarketplaces` + `installed_plugins.json` `marketplace` keys |

## 5. Schema (event-sourced)

### 5.1 Append-only event log: `events`

```
:create events {
  event_id: String,            -- ULID; sortable, monotone, stable across processes
  =>
  observed_at: String,         -- RFC3339 of indexing run (== scan_run.finished_at)
  scan_id: String,             -- FK to scan_runs
  event_type: String,          -- one of the 18 types in §6 below
  element_type: String,        -- skill | agent | command | rule | mcp | lsp | hook | plugin | channel | monitor | output-style | marketplace
  element_name: String,        -- frontmatter name or filename slug
  scope: String,               -- local | project | user | plugin | marketplace
  scope_path: String,          -- abs path: project root, plugin root, marketplace root, or "" for user
  source: String,              -- legacy descriptor: user | project | local | plugin:<id> | marketplace:<id>

  -- snapshot at event time (denormalized for query speed)
  path: String,
  content_hash: String,        -- sha256 hex; "" if non-file or removal event
  file_size: Int,              -- bytes; -1 if N/A
  token_count: Int,            -- tiktoken cl100k_base; -1 if N/A
  enabled: Bool,
  override_status: String,     -- active | overridden_by:<element_id> | overrides:<element_id> | none

  -- delta payload describing what changed
  diff_json: String,           -- JSON: {"size_delta": +123, "fields_changed": ["description"], "previous_hash": "...", "previous_status": "..."}

  -- pointer into the blob store for content snapshots
  snapshot_ref: String         -- "" or "blob:<sha256>"
}
```

ULID gives us O(1) ordering by event_id alone. Cozo btrees the key.

### 5.2 Content-addressed blob store: `element_blobs`

```
:create element_blobs {
  hash: String =>
  bytes_b64: String,           -- base64-encoded raw file bytes (or canonical config JSON for non-file)
  size: Int,
  first_seen_at: String,
  ref_count: Int               -- bumped/decremented as events reference/unreference
}
```

A blob is stored once even if 100 events reference it. Pruning collapses
unreferenced blobs.

### 5.3 Materialized view: `elements_state`

```
:create elements_state {
  element_id: String =>        -- "<element_type>:<element_name>@<scope>:<scope_path_slug>"
  last_event_id: String,
  current_path: String,
  current_hash: String,
  current_size: Int,
  current_token_count: Int,
  enabled: Bool,
  override_status: String,
  installed_at: String,        -- observed_at of first `installed` event
  last_changed_at: String,     -- observed_at of last content_changed event
  exists: Bool                 -- false after a `removed` event
}
```

Updated transactionally with each batch of events. Every query that asks
"what is X right now?" reads only this table.

### 5.4 Scan ledger: `scan_runs`

```
:create scan_runs {
  scan_id: String =>
  started_at: String,
  finished_at: String,
  scope_paths_json: String,    -- list of dirs scanned this run
  events_emitted: Int,
  rust_binary_version: String,
  pss_version: String
}
```

A subsequent scan that doesn't visit scope_path P cannot fabricate
removal events for elements within P — we look at this table to know
what was actually checked.

### 5.5 Backward-compat shim

`skills` and `rules` tables stay populated as a read-only mirror,
regenerated from `elements_state WHERE exists = true` after each scan.
Suggestion hot path unchanged. Deprecated in 3.4.0.

## 6. Event taxonomy (18 types)

| event_type | When emitted | Required diff_json fields |
|---|---|---|
| `installed` | First-ever observation of (element_type, name, scope, scope_path) | `path`, `hash`, `size`, `token_count` |
| `removed` | Previously-active element no longer present at its scope_path AND its scope_path was scanned this run | `previous_hash`, `previous_path` |
| `content_changed` | Same element_id; `content_hash` differs from previous event | `previous_hash`, `new_hash`, `size_delta` |
| `size_changed` | Same hash but size differs (rare — symlink swap, line-ending change) | `previous_size`, `new_size` |
| `frontmatter_changed` | Frontmatter dict differs but body unchanged | `fields_changed: [...]` |
| `description_changed` | Special-case shortcut for frontmatter description-only delta | `previous_description`, `new_description` |
| `path_changed` | Element file moved within the same scope (same name + scope, different path) | `previous_path`, `new_path` |
| `enabled` | Element transitioned from disabled to enabled in settings | `enabling_setting_path` |
| `disabled` | Element transitioned from enabled to disabled | `disabling_setting_path` |
| `scope_moved` | Same name+type appeared at a different scope this scan after disappearing from prior scope (heuristic — paired with `removed` + `installed`) | `from_scope`, `to_scope` |
| `override_started` | A higher-priority element with same name+type appeared, hiding this one | `overriding_element_id`, `overriding_scope` |
| `override_ended` | The overriding element disappeared; this element is active again | `previously_overriding_element_id` |
| `marketplace_added` | New marketplace registered in `extraKnownMarketplaces` or `installed_plugins.json` | `marketplace_url`, `marketplace_name` |
| `marketplace_removed` | Marketplace unregistered | `marketplace_url`, `marketplace_name` |
| `plugin_installed_in_scope` | Plugin appeared in `installed_plugins.json` at scope (user/project) | `plugin_name`, `marketplace`, `version` |
| `plugin_uninstalled_from_scope` | Plugin disappeared from `installed_plugins.json` at scope | `plugin_name`, `marketplace`, `previous_version` |
| `plugin_version_changed` | Same plugin name+marketplace+scope, different version | `previous_version`, `new_version` |
| `metadata_changed` | Catch-all: enrichment fields differ (keywords, domains, etc.) | `fields_changed: [...]` |

Every event includes the snapshot context (path, hash, size, token_count,
enabled, override_status) so a single event row is self-describing
without needing to walk back through history.

## 7. Identity, hashing, and emission rules

- **element_id** = `f"{element_type}:{element_name}@{scope}:{scope_path_slug}"`
  lowercased; `scope_path_slug` is `scope_path` with `/` replaced by `_`.
  Same name in two project paths = two distinct element_ids.
- **content_hash** = sha256 hex of:
  - file element: raw bytes
  - non-file element: canonical JSON of config (sorted keys)
- **emission**: each scan compares current discovery against
  `elements_state` and emits the minimum set of events that explain the
  delta. Emission is purely deterministic given (previous state, current
  observation).
- **observed_at** for every event = `scan_run.finished_at`. No mtime
  reading. Per user instruction.
- **override resolution**: priority `local > project > user > plugin >
  marketplace`. For each (name, element_type) group, top scope is
  `active`; lower scopes are `overridden_by:<top_element_id>`. Top
  element is `overrides:<list_of_lower>` if any lower exist, else `none`.

## 8. Token counting

- Add `tiktoken-rs = "0.5"` to `rust/skill-suggester/Cargo.toml` (cl100k_base)
- Compute on file body for file elements; on canonical config JSON for non-file
- Encoder cached in `OnceLock<Encoder>` (~50 ms startup once)
- Per-element: <5 ms; full reindex of 3000 elements: <30 s
- **Caveat**: cl100k_base is OpenAI's tokenizer. Anthropic doesn't
  publish theirs. Counts are typically within ±10% of Claude's actual.
  Documented as approximate. If exact Claude counts ever needed,
  replace with Anthropic `count_tokens` API call (network IO,
  rate-limited — out of scope for this TRDD).

## 9. CLI surface (Rust binary)

Every subcommand returns JSON (`--format json`, default) or
`--format table` for humans. All read CozoDB directly — zero LLM calls.
Most return in <50 ms even on year-old DBs.

### 9.1 Lifecycle queries

| Subcommand | Maps to user example |
|---|---|
| `pss as-of <DATE>` | "list all extensions installed on 2026/03/14" |
| `pss as-of <DATE> --type skill --scope project --scope-path ~/foo` | "what skills were installed in project ~/foo on 2026/03/14" |
| `pss installed-on <DATE> --type plugin --scope user` | "list all plugins enabled at user scope on date X" |
| `pss timeline <ELEMENT_ID>` | full event stream for one element |
| `pss timeline <ELEMENT_ID> --field frontmatter` | frontmatter snapshots only |
| `pss show <ELEMENT_ID> --as-of <DATE>` | "what was the frontmatter of agent X on Jan 30" |
| `pss size-at <ELEMENT_ID> --as-of <DATE>` | "what was the size of agent X on Jan 23" |
| `pss tokens-at <ELEMENT_ID> --as-of <DATE>` | token count at point in time |
| `pss lifespan <ELEMENT_ID>` | first-seen and last-seen timestamps |
| `pss diff <ELEMENT_ID> <DATE1> <DATE2>` | what changed between two dates |
| `pss changed-between <START> <END> [--type T]` | "all skills changed between A and B" |
| `pss installed-between <START> <END>` | every install event in window |
| `pss removed-between <START> <END>` | every removal event in window |
| `pss never-current` | elements that existed at some point but aren't now |
| `pss currently-missing-but-once-was --type command` | "commands installed before today but not now" |
| `pss multi-scope <NAME>` | "find skills present at user-level AND inside a plugin at the same time" |
| `pss installed-from-plugin <PLUGIN> --type mcp --as-of <DATE>` | "find mcp servers installed via user-scoped plugins on date X" |
| `pss override-history <ELEMENT_ID>` | every override_started/override_ended event |
| `pss enable-history <ELEMENT_ID>` | every enabled/disabled event |
| `pss scope-moves <NAME> --type T` | every scope_moved event for matching elements |
| `pss marketplace-history` | all marketplace_added/removed events |
| `pss plugin-history <PLUGIN_NAME>` | all plugin events for one plugin |

### 9.2 Operational subcommands

| Subcommand | Purpose |
|---|---|
| `pss reindex` | Full discover → enrich → emit events. For janitor cron. |
| `pss reindex --dry-run` | Print event set without writing |
| `pss reindex --scope-path P` | Limit scan to one scope_path (faster reruns) |
| `pss prune-history` | Drop events older than retention window; collapse unreferenced blobs |
| `pss retention --get` / `--set <DURATION>` | Configure retention (default 9 months). Stored in `pss_metadata.retention_window` |
| `pss scan-log [--limit N]` | List recent scan_runs |
| `pss db-stats` | Event count, blob count, blob bytes, oldest event, retention window |

### 9.3 Existing subcommands (made history-aware)

`search`, `list`, `find-by-*`, `inspect`, `compare`, `get-description`,
`coverage`, `vocab` — accept optional `--as-of <DATE>`. Without it,
queries hit `elements_state`. With it, they reconstruct state from
events up to that timestamp.

## 10. Janitor integration

Add `scripts/detectors/pss-reindex-due.sh` that compares `now -
last_scan_runs.finished_at` against `PSS_REINDEX_INTERVAL` (env or
metadata, default 24h) and emits one drift line if exceeded:

```
[pss-reindex-due] PSS index last refreshed N hours ago. Run `pss reindex`.
```

The user can either run `pss reindex` interactively or wire a separate
cron entry to `pss reindex` directly. PSS itself does not call cron.

## 11. Retention

- Default 9 months — stored in `pss_metadata.retention_window`
- `pss prune-history` deletes events where `observed_at < (now -
  retention)` AND that event is not the last event for an element
  whose `exists = true` (we never delete the install event of a still-installed element, even if old)
- After event delete: scan `element_blobs` and collapse rows where
  `ref_count = 0`
- Pruning is idempotent — safe to run frequently from cron

## 12. Migration

On first run with new binary:

1. Read `pss_metadata.schema_version`. If missing or `< "2"`:
   a. Create new tables (`events`, `element_blobs`, `elements_state`, `scan_runs`)
   b. For every row in legacy `skills`: emit a synthetic `installed`
      event with `observed_at = first_indexed_at`, populate
      `elements_state`, store body bytes in `element_blobs` if file
      still exists on disk
   c. Same for `rules`
   d. Insert `pss_metadata.schema_version = "2"`
2. Subsequent reindexes operate on v2 schema only

Legacy tables stay populated through 3.3.x for back-compat. Removed in 3.4.0.

## 13. File touch list (per phase)

### Phase 1 — Schema, tiktoken, migration (≤5 files)
- `rust/skill-suggester/Cargo.toml` — add `tiktoken-rs`, `sha2`, `ulid`
- `rust/skill-suggester/src/main.rs` — new schema definitions, migration
- `scripts/pss_cozodb.py` — Python-side schema awareness
- `scripts/pss_paths.py` — DB filename unchanged; gate via schema_version
- `tests/test_temporal_schema.py` — new

### Phase 2 — Event emission + new element types (≤5 files)
- `scripts/pss_discover.py` — add hook/plugin/channel/monitor/output-style/marketplace discovery
- `scripts/pss_merge_queue.py` — replace overwrite-merge with event emission
- `rust/skill-suggester/src/main.rs` — change-detection + override resolution
- `tests/test_event_emission.py` — new
- `tests/test_override_resolution.py` — new

### Phase 3 — Lifecycle CLI subcommands (≤5 files)
- `rust/skill-suggester/src/main.rs` — add subcommand dispatchers
- `rust/skill-suggester/src/temporal.rs` — new module (event queries + state replay)
- `tests/test_lifecycle_cli.py` — new
- `docs/PSS-TEMPORAL.md` — new user-facing doc with every example query
- `CLAUDE.md` — updated architecture section

### Phase 4 — Reindex command + janitor + retention (≤5 files)
- `rust/skill-suggester/src/main.rs` — `pss reindex`, `pss prune-history`, `pss retention`
- `scripts/detectors/pss-reindex-due.sh` — new janitor detector
- `commands/pss-reindex-skills.md` — wrapper around `pss reindex`
- `tests/test_retention.py` — new
- `tests/test_reindex_idempotent.py` — new

Total: ≤20 files across 4 phases.

## 14. Test strategy

- **Schema migration:** snapshot a v1 DB → run binary → assert v2 tables
  populated correctly, no data loss
- **Event emission unit tests:** synthetic before/after states → assert
  exact list of events emitted (including ordering and diff_json content)
- **Override resolution:** insert same-name elements at multiple scopes
  → assert `override_started`/`override_ended` events emit correctly as
  scopes appear and disappear
- **Removal detection:** delete file → reindex → assert `removed` event
  emitted only when scope_path was actually scanned
- **Scope move:** rename element_id field by changing scope_path →
  assert paired `removed` + `installed` events with same `name` and
  `element_type`
- **Token counting:** known file with known tiktoken count → assert match
- **Lifecycle query speed:** 100k events → assert any subcommand <100 ms
- **Retention pruning:** stuff DB with old events → assert prune drops
  expected, keeps current-element install events even if old, collapses
  blobs
- **CLI roundtrip:** every subcommand exercised via subprocess in CI

## 15. Risks and open questions

| # | Question | Default decision |
|---|---|---|
| Q1 | tiktoken approximation vs Claude tokenizer | use cl100k_base; document approx |
| Q2 | Scope move detection is heuristic (renames look like remove+install) | accept; add `pss detect-renames` later if needed |
| Q3 | Blob storage size growth | content-addressed dedup keeps it bounded; prune unreferenced on retention sweep |
| Q4 | DB filename | unchanged; migrate in place via schema_version |
| Q5 | Override priority accuracy for hooks/MCP — settings.local > settings (project) > settings (user) | follow CC's documented precedence; test against current CC version |
| Q6 | What about elements that exist as both a file AND a setting (rare)? | each kind tracked under its own element_type; no conflict |
| Q7 | Retention default 9 months — too short? | configurable; user picked default |

## 16. Phased gate plan

- **Gate A:** TRDD reviewed by user. Approval = green light for Phase 1.
- **Gate B:** Phase 1 done (schema + migration + tiktoken). Diff
  reviewed; tests green. Approval → Phase 2.
- **Gate C:** Phase 2 done (event emission + new element types).
- **Gate D:** Phase 3 done (CLI surface).
- **Gate E:** Phase 4 done (reindex + janitor + retention).
- **Ship:** All four phases committed; version bump to 3.3.0; docs published.

## 17. Estimated effort

Four to six focused sessions. Phase 1 and Phase 2 are the heaviest (event
emission logic + override resolution).

## 18. Out of scope (deferred)

- Web UI for browsing event log
- Storing full body bytes at every revision (we keep one copy per unique
  hash, so revisions of unchanged elements share a blob)
- Cross-machine sync of history
- Streaming events to OpenTelemetry / external aggregators
- Anthropic-exact token counting (would require API calls)
- Inferential rename detection beyond scope_moved

## 19. Anthropic doc verification (mandatory before each phase)

User instruction: **"refer to the anthropic documentation in case of
doubts. even better: always verify, do not assume anything."** Doc index:
`https://code.claude.com/docs/llms.txt`. Each phase must cite the
verifying URL in commit messages.

| Phase | Doc(s) to consult before coding | What to verify |
|---|---|---|
| 1 (schema) | `settings.md`, `claude-directory.md` | exact paths CC scans, scope precedence rules, what counts as an "extension" file |
| 1 (tiktoken) | `env-vars.md` | confirm no env-var override exists for tokenizer; document our cl100k_base choice as approximate |
| 2 (hooks) | `hooks.md`, `hooks-guide.md` | hook config schema, event types, scope-merging behavior, override priority |
| 2 (plugins) | `plugins.md`, `plugins-reference.md`, `plugin-marketplaces.md`, `plugin-dependencies.md` | plugin.json schema (incl. `experimental.themes/monitors`), installed_plugins.json v2 layout, marketplace registration |
| 2 (mcp) | `mcp.md`, `connect-claude-code-to-tools-via-mcp.md` | MCP server config schema (stdio / sse / http), `alwaysLoad` flag, scope precedence, claude.ai connectors |
| 2 (channels) | `channels.md`, `channels-reference.md` | channel definition schema, where channels are stored, enable/disable mechanics |
| 2 (output-styles) | `output-styles.md` | output-style file format, location, plugin-shipped vs user-defined |
| 2 (skills) | `skills.md` | SKILL.md frontmatter schema, scope precedence, `context: fork` semantics |
| 3 (CLI) | `cli-reference.md`, `slash-commands.md` | nothing collides with `pss reindex` semantics |
| 4 (retention/cron) | `env-vars.md` | confirm no scheduling primitives we should integrate with beyond CronCreate |

Verification protocol per phase:
1. WebFetch each relevant doc URL
2. Compare doc claims against PSS code assumptions
3. If divergence found: log a finding in the phase's report file
4. Adjust implementation; re-verify
5. Cite verified-against URL + doc-version date in the commit message

**Never assume** — if a behavior isn't documented, write a small probe
(throwaway script that exercises CC's actual behavior) and treat its
output as ground truth, not the docs.

## 20. Test rigor (mandatory)

User instruction: **"write also tests"**. Beyond §14:

- **Unit tests** for every event-emission rule in §6 — synthetic
  before/after states, assert exact event lists.
- **Integration tests** that spin up a temp `~/.claude/`-like tree, run
  `pss reindex`, mutate the tree, run again, assert event log.
- **Property-based tests** (hypothesis or proptest) for the override
  resolution: random scope combinations → assert priority math.
- **Negative tests**:
  - corrupt DB on disk → migrate gracefully
  - missing source file mid-scan → tombstone emitted, no crash
  - tiktoken encoder unavailable → fall back to char-count, log warning
  - clock-skew (observed_at < previous event's observed_at) → reject and warn
- **Smoke tests** for every CLI subcommand — exit code, JSON shape.
- **CI gate**: `scripts/publish.py --gate` must include the temporal test
  suite. Tests must run in <60 s on the publish-gate runner.
- **Coverage target**: ≥85% line coverage for the new Rust module
  `temporal.rs` and the new Python event-emission code in
  `pss_merge_queue.py`.

## 21. Post-implementation audit (Gate F)

User instruction: **"when you finish, launch an in depth scan and audit
of all your changes. fix all."**

After Phase 4 ships and before version bump:

1. Run `/cpv-validate-plugin .` — fix all findings except known-FP
   classes documented in issue #8.
2. Run `tldr diagnostics .` — fix all type-check + lint errors.
3. Run `cargo clippy --all-targets --all-features -- -D warnings` — fix all.
4. Run `cargo audit` — fix all high/critical.
5. Run `scripts/publish.py --gate` — must pass clean.
6. Spawn `code-auditor-agent:caa-audit-codebase-cmd` against the diff —
   apply its TODO fixes.
7. Spawn `code-review:code-review` for a fresh-eyes review — address all
   blockers.
8. Spawn `pr-review-toolkit:silent-failure-hunter` — all fail-fast paths
   verified.
9. Spawn `pr-review-toolkit:type-design-analyzer` on the new schema and
   Rust modules.
10. **Before ship** — re-run all tests; final verification probe.

Audit report goes to `reports/audit/<timestamp>-final-audit.md`. Any
unfixable finding (architectural deferral, etc.) must be logged as a
follow-up TRDD before shipping.

## 22. Cross-reference: GitHub issue #8

Open issue [#8](https://github.com/Emasoft/perfect-skill-suggester/issues/8)
(2026-04-29) is a CPV v2.41 audit report against the current main branch:

- 2 CRITICAL — both confirmed false-positives (chat history scan + docs
  prose). Action: ensure CPV scan filter excludes `.claude/chat_history/`
  and `anthropic_dev/`.
- 52 MAJOR + 11 MINOR — distribution dominated by:
  - 28 trufflehog noise in `.git/objects/`, `.venv/`, `rust/target/`,
    `docs_dev/anthropic_official_documentation/` (filter out)
  - 12 RC-76 prompt-injection signals in NLP training corpora (domain-aware
    exception)
  - 12 RC-87 RFC-1918 IP mentions in docs/changelog (CPV v2.41 has guard,
    confirm firing)
  - 3 RC-21 `os.environ.copy()` for subprocess pass-through (CPV v2.41
    guard)
  - 3 RC-93 column-aligned `printf` (CPV v2.41 guard)
- Real items needing fix in PSS code:
  - `scripts/pss_reindex.py:145` — `subprocess.run(..., shell=True)`;
    refactor to argv list
  - `skills/pss-usage/references/pss-commands.md:94` — hardcoded
    `/Users/<name>/` path; replace with `${CLAUDE_PLUGIN_ROOT}` or `~`

Decision: address the **two real items** in Phase 1's prep step (smaller
than the temporal work) and let the FPs persist until CPV's
context-aware guards land. After all 4 temporal phases ship, re-run CPV
in the Gate F audit and reconcile.
