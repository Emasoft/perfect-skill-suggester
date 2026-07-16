---
trdd-id: 1Z8SGQ7N
title: Extension-tracking temporal-index design defects — deferred cross-cutting fixes
column: backburner
created: 2026-07-15T11:17:58+0200
updated: 2026-07-16T10:51:50+0200
current-owner: perfect-skill-suggester
task-type: bugfix
parent-trdd: 152e697f
relevant-rules: []
---

## ⏵ STATE — READ THIS FIRST ON RESUME (authoritative) — 2026-07-15

**What this is:** the durable record of the VERIFIED-REAL-but-DEFERRED findings from
the 2026-07-15 `/code-review high --fix` on "tracking of installed extensions across
all projects and across time" (the temporal index, TRDD-152e697f). The MECHANICAL /
non-behavior-changing fixes already landed (commits below); everything here changes
stored id / timestamp / state semantics or spans Python+Rust+migration, so it was
deferred to a coordinated, migration-aware fix rather than half-applied in the review.

**Already fixed + committed (NOT in this TRDD's scope):** merge-events failure→fail-fast,
hardcoded marketplace name, resolver dedup (pss_reindex.py); DI-4 scope_path derivation
mismatch (pss_discover.py); dead code, stale DDL comment, empty-timestamp guard, N+1
query (temporal.rs). Commits: parent `ea09f30`, rust submodule `1e05984`. Gates: ruff
clean, pytest 256, cargo check clean + 185/185.

**Evidence (read for exact fix + blast radius per finding):**
`reports/pss-extension-tracking-review/20260715_104606+0200-pss_reindex.md`,
`…-085200+0000-pss_discover.md`, `…-083000+0200-temporal.md`.

**UPDATE 2026-07-16 — F1 STEP 1 (the P0 clobber) IS FIXED + COMMITTED (`e6d94b9`).**
`atomic_write_cozodb` now preserves every non-schema-owned relation across the staging
swap via `_snapshot_extra_relations` (schema derived from the live DB via
`::relations`/`::columns` — no hardcoded Rust-DDL copy), with a drift-guard test
(`_KNOWN_SCHEMA_RELATIONS` == exactly what `_create_db_schema` creates). 259 tests green.
⚠ The INSTALLED plugin (v3.10.0) still carries the clobber until a release ships and the
plugin updates — do NOT run `/pss-reindex-skills` on this machine before then.

**NEXT ACTION — F1 step 2 needs ONE design decision before coding (Rust rebuild either
way):** the path split is caused by ENV-DEPENDENT resolution (Python `get_data_dir`
prefers `$CLAUDE_PLUGIN_DATA` when set+guarded; Rust `get_db_path` and any non-plugin
invocation always use `~/.claude/cache`) — different surfaces resolve different DBs.
- Option A: mirror Python's env preference in Rust `get_db_path` + add a one-time
  history migration (plugin-data lacking events + legacy cache having them → migrate),
  because a path flip strands the 9135-event history.
- Option B (RECOMMENDED): canonicalize the DB at `~/.claude/cache` on every surface
  (env-independent, matches live reality where skills+events already co-reside, zero
  migration, kills the flip-flop class entirely); plugin-data keeps non-DB state only.
  Costs: reverses the documented v2.4.6 plugin-data preference for the DB.
F1 step 3 (retire the April orphan at the plugin-data path — 0 real events, regenerable)
follows whichever option lands.

### Deferred findings, ranked

**F1 — P0 DATA LOSS — full-reindex wipes the events tables.** `run_pipeline` stage 1-3
writes the `skills` table via Python `get_data_dir()` (prefers `$CLAUDE_PLUGIN_DATA`) and
`atomic_write_cozodb` replaces the ENTIRE db file via staging-swap; the Rust `merge-events`
writer resolves its db path via a *different* resolver (`get_db_path`) than Python, so when
both land on the same file the stage-1-3 swap clobbers the `events`/`elements_state` rows
merge-events just wrote. Empirically confirmed: **~9135 events in the `~/.claude/cache` DB
are wiped on the next full reindex.** Fix spans `pss_cozodb.py` (`atomic_write_cozodb` /
`_create_db_schema` must PRESERVE the events tables across the swap) + align Rust
`get_db_path` with Python `get_data_dir`. A naive in-file path-unify in pss_reindex.py
would *cause* the clobber — do NOT do that. Blast radius: all historical temporal data.

**F2 — P1 — `obs.enabled` misrouted into `update_state` freezes disabled elements.**
`cmd_merge_events` passes `obs.enabled` as the `persist_event_and_state` `update_state`
bool, so `elements_state` is not updated for disabled elements → their state silently stops
tracking. Blast radius: every disabled element's history (temporal.rs ~L3089).

**F3 — P1 — merge-events writer has no advisory/staging lock (live SQLite race).** Rust
`open_db` (the merge-events writer) opens the CozoDB SQLite with no fcntl/staging
coordination; the project's v3.5.0 staging-file + atomic-rename fix protects the PYTHON
writer path, NOT this Rust path → a live read/write race with the hot path (potential
corruption / SIGABRT). Blast radius: concurrent reindex + `UserPromptSubmit` reads
(main.rs ~L14680).

**F4 — P1 — `compute_element_id` collision.** Lowercases name/scope/scope_path and replaces
`/`→`_` before joining → case-distinct or path-distinct elements collapse to the SAME
element_id, merging two elements' histories. Blast radius: cross-scope/cross-project
tracking (two project paths differing only in case/separators share history)
(temporal.rs ~L162). NOTE: changing the id scheme re-keys existing rows → needs a migration.

**F5 — P1 — `migrate_v1_to_v2` hardcodes `scope_path=""` for every legacy row.** All
project/plugin/marketplace/local elements get the wrong `element_id` on migration, so their
pre-migration history is mis-keyed vs post-migration observations. Blast radius: all v1→v2
migrated multi-scope elements (temporal.rs ~L450,487).

**F6 — P1 — override-resolution reads its own write.** The override pass calls `read_prior`
for `override_status` AFTER the main emit loop already upserted `elements_state`, so it
reads the value it just wrote, not the true prior → override transitions mis-detected.
Related: the main loop persists ContentChanged with `override_status="active"` and upserts
before resolution (F6b, temporal.rs ~L3088/3176).

**F7 — P2 — full-scope-removal is undetectable.** `visited_scope_paths` in the DI-4 removal
manifest is built only from surviving/observed elements, so a scope that becomes FULLY
uninstalled (zero surviving elements) is never visited → its complete removal is never
emitted. Fix: derive visited scopes from the set of SCANNED ROOTS, or carry forward
previously-known scope_paths (pss_discover.py ~L2122). (The related scope_path derivation
half of this finding was already FIXED in `ea09f30`.)

**F8 — P2/P3 — `PathChanged` dropped on coincident content change.** `compare_and_emit`
drops the `PathChanged` event when an in-scope move coincides with a content/size change, so
a move+edit records only the content change and loses the relocation (temporal.rs ~L773).

**F9 — P3 — `observed_at` tz/format.** Written with `chrono::Utc::now().to_rfc3339()`
(`+00:00`, fractional seconds) but compared elsewhere against a differently-formatted
timestamp; pin down the exact comparison site before fixing (temporal.rs ~L2953).

## Scope

One coordinated follow-up (or a small set of child TRDDs, F1 first as its own). Each fix
either changes stored id/timestamp/state semantics or spans Python+Rust — hence deferred
from the review's `--fix` pass. Terminal when every F# is fixed-or-consciously-accepted with
a migration for the id/timestamp-schema changes (F4, F5).
