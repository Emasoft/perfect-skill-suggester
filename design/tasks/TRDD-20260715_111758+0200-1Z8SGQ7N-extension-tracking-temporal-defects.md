---
trdd-id: 1Z8SGQ7N
title: Extension-tracking temporal-index design defects — deferred cross-cutting fixes
column: backburner
created: 2026-07-15T11:17:58+0200
updated: 2026-07-16T19:55:00+0200
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
**UPDATE 2026-07-16 15:35 — v3.10.1 SHIPPED (release commit `c7296e3`).** Carries F1
step 1 + the review fixes + the xhigh fixes (`4453b11`) + the CPV env-poison
devitalization (`6538cdc`). Both tags (`v3.10.1`, `perfect-skill-suggester--v3.10.1`)
verified on remote; GH release live; shipped `pss-darwin-arm64` verified to contain the
rebuilt temporal.rs (new "events scan failed" string present, reports 3.10.1).
⚠ The INSTALLED plugin on this machine remains v3.10.0 (clobber still live locally)
until the marketplace update propagates and the plugin updates — do NOT run
`/pss-reindex-skills` here before the local install shows 3.10.1.

**UPDATE 2026-07-16 17:40 — F1 STEP 2 IS DONE + COMMITTED (`7e66077`). OPTION B CHOSEN.**
Decided on verified facts, not preference:
- Probed the SHIPPED binary's `db-path` under 3 envs: Rust resolves
  `~/.claude/cache/pss-skill-index.db` with `$CLAUDE_PLUGIN_DATA` set, unset, and
  PSS-scoped — it **never** reads that variable. Only `$PSS_INDEX_PATH`/`--index`
  move it. So Rust was ALREADY canonical; Option A would have moved the ONE correct
  surface and stranded the history behind a migration.
- Live census confirmed the premise exactly: cache = 8965 skills / **9135 events**;
  plugin-data = 8488 skills / **0 events**. The history is at cache. B = zero migration.
- **B is Python-only ⇒ NO Rust rebuild.** The TRDD's "Rust rebuild either way"
  assumption was WRONG — recorded here so it is not repeated.

`pss_cozodb.get_db_path()` now mirrors main.rs exactly (`$PSS_INDEX_PATH` sibling →
`~/.claude/cache`). `$CLAUDE_PLUGIN_DATA` still backs NON-DB state via `get_data_dir()`
(staging JSON, lockfiles, backups); only the DB is pinned.

**Derived fix (found by rechecking consequences, NOT in the original finding):**
`backup_index()` composed `pss-skill-index.db` onto `cache_dir` — a SECOND resolver.
Once the DB pinned to cache, that backup silently copied nothing, leaving the only copy
of the history unprotected during the swap. Now takes the canonical path. Also deleted
the dead `LOCK_FILENAME` constant and corrected `pss_hook`'s false claim that current
writers take LOCK_EX on the legacy `db.lock`.

**PRODUCTION VERIFICATION (real reindex, bug-triggering env, live DB backed up first):**
skills → cache DB (9474); the 9135 events **survived the atomic swap and grew to 17966**;
plugin-data orphan stayed frozen at 8488/0; the backup dir held a real **95 MB** DB
(pre-fix: a silent no-op). Run 1 exit 1 / run 2 exit 0 — see F3 below. 274 tests, ruff clean.

**NEW EVIDENCE FOR F3 (reproduced on the FIRST real run):** run 1's merge-events died
with `state upsert failed: database is locked (code 5)` — the Rust writer racing this
session's own hook readers on the cache DB. It left `events` advanced but
`elements_state` lagging until run 2 reconciled it. **NOT a regression from step 2**
(proved: merge-events targets the cache DB regardless of the env var, so it always raced
readers there). F3 is P1 with a first-try repro; the fail-fast from `ea09f30` reported it
honestly instead of claiming success. Note the stage-4 message says temporal is "NOT
updated" when it can in fact be PARTIALLY updated — tighten when F3 lands.

**UPDATE 2026-07-16 18:20 — F3 IS DONE + COMMITTED (submodule `20b2da2`).** The
`merge-events` arm is intercepted in `main()` BEFORE the DB opens (mirroring Health/DbPath)
and takes two blocking flocks in a fixed, deadlock-free order: `<db>.write.lock` (EX,
excludes a concurrent Python skills-write) then `<db>.lock` (EX, excludes the hook's
LOCK_SH readers). Acquired pre-open because a Python writer `os.replace()`s a fresh inode
over the path. Uses **`fs2`** not `std::fs::File::lock` (the latter is Rust-1.89-only; the
release cross-builds 5 targets in Docker containers with uncontrolled rustc — fs2 removes
the MSRV bet). The now-unreachable old `MergeEvents` arm in `run_query_command` was turned
into an internal-error guard (no duplicate working path).

**F3 PRODUCTION VERIFICATION:** a real reindex under **40 concurrent readers hammering
`LOCK_SH`** — the exact contention that killed the earlier run — completed **exit 0**;
the 17966 events survived and grew to 18555; a standalone probe confirmed the writer
**blocks 1.9s** on a held reader lock instead of racing it. 185 Rust tests, my-code clippy
clean. The stage-4 "temporal NOT updated" wording tightening is folded into F9's batch
(still open). NOTE: on macOS a `cp`-overwritten binary is SIGKILLed by codesign (rc 137) —
a test-harness artifact, not a code path; publish rebuilds the binaries cleanly.

**UPDATE 2026-07-16 18:55 — F2 + F8 DONE + COMMITTED (submodule `f8c463f`).**
- **F2**: removed the `update_state` bool from `persist_event_and_state` (all 4 callers
  now materialize state); the DI-3 change had wired `obs.enabled` into it, freezing
  disabled elements' `elements_state`. Removed rather than pinned to `true` so the footgun
  can't return. **Caveat recorded:** this makes the still-open **F6** (override pass reads
  its own write) apply uniformly to disabled elements — NOT a regression (F6 already broke
  the enabled case); F6's fix must snapshot prior `override_status` before the emit loop.
- **F8**: `compare_and_emit` now emits `PathChanged` on ANY path change (was an `else if`
  that dropped it when content/size also changed → move+edit lost the relocation).
- Tests: F8 unit (move+edit → both events; +size → all three), F2 real-writer in-mem-DB
  (disabled element gets a state row). 188 Rust tests, my-code clippy clean. Production:
  reindex exit 0, events 18555→19258, elements_state grew by the disabled elements F2 tracks.

**UPDATE 2026-07-16 19:20 — F6 DONE + COMMITTED (submodule `f92226f`).** The override
pass now snapshots each element's `override_status` into a map BEFORE the emit loop upserts,
and compares against that snapshot instead of `read_prior` (which returned the value the
emit loop had just written). Red-green test: scan 1 establishes user-overrides-plugin (2
override_started), scan 2 moves the plugin file (clobbers override_status via the emit
loop) without changing the override decision → fixed total 2, buggy total 3 (spurious). 189
Rust tests. This closes the F2 caveat — the override tracking is now correct for both
enabled and disabled elements.

**STILL OPEN:**
- **F9** (P3, observed_at tz/format) + the stage-4 "temporal NOT updated" partial-wording
  tighten. Needs the exact comparison site pinned first. Likely no migration.
- **F7** (P2, full-scope-removal undetectable) — Python cross-file design change
  (enumerate scanned roots independently of results). No migration but larger.
- **F4** (P1, element_id collision) + **F5** (P1, migration scope_path="") — BOTH re-key
  stored `element_id`s ⇒ **need a data migration ⇒ need USER scoping before coding.**
- xhigh-skipped events full-scan growth — batch with F9.

### F4 + F5 EXECUTION PLAN (design done 2026-07-16 19:55; ready to code once the one USER decision below lands)

**Verified facts (read the source, not guessed):**
- `compute_element_id` (temporal.rs:156) builds `"{type}:{name}@{scope}:{scope_path}"` after
  `scope_path.replace('/', "_")` AND `.to_lowercase()` on name/scope/scope_path_slug. BOTH
  transforms are LOSSY: `/a/b`, `/a_b`, `_a_b` all slug to `_a_b`; `Foo`/`foo` and
  `/Users/Me`/`/users/me` lowercase-collapse → distinct elements share one id, merging histories.
- `element_id` is **opaque** — grepped both files; it is NEVER split/parsed back into components
  (the only `split(':')`/`split('@')` sites operate on an evidence string and a user-query
  namespace, not element_id). So the id may safely carry raw `/`, `:`, `@` from a path; dropping
  the slug breaks no parser. **This is the load-bearing fact that makes F4 safe.**
- The events row stores `element_name`, `scope`, `scope_path` as their OWN columns in ORIGINAL
  case (persist writes `obs.name`/`obs.scope`/`obs.scope_path` raw; only `element_id` is
  lowercased). ⇒ the true (name, scope, scope_path) survives for every historical row, so a
  migration can recompute the correct new element_id per row — **lossless, and it UN-merges
  previously-collided histories** (each row re-keys from its own columns).
- F5: `migrate_v1_to_v2` (temporal.rs:464) hardcodes `scope_path = "".to_string()`, so every
  legacy row's element_id is `type:name@scope:` while the live writer keys the same element with
  its real `scope_path_from_discovery_source(source)` → the pre/post-migration histories split.

**The fix (code):**
1. `compute_element_id`: use `scope_path` RAW (drop the `/`→`_` slug and its `.to_lowercase()`).
   Paths are separator- and case-significant (Linux fs is case-sensitive); slugging/lowercasing
   them is the clear bug. **← THE ONE USER DECISION: should the element NAME stay
   case-insensitive** (skill `Foo` == `foo`, likely intended for Claude-Code name matching) **or
   become case-sensitive?** Keep `name.to_lowercase()` for case-insensitive; drop it for
   case-sensitive. `scope` is a small enum-ish set — lowercasing it is harmless either way.
2. F5: `migrate_v1_to_v2` line 464 → `let scope_path = scope_path_from_discovery_source(&source);`
   (mirror the writer). Bare legacy sources still yield "" — consistent, documented blind spot.

**The migration (run-once, deterministic, preserves history — NO reset):**
- Gate on a `pss_metadata` key (e.g. `element_id_scheme_version=2`) so it runs exactly once.
- For each `events` row: `new_id = compute_element_id_v2(element_type, element_name, scope,
  scope_path)`; rewrite the row's `element_id`. Then rebuild `elements_state` from the re-keyed
  events (it is materialized FROM events, so drop + replay, or recompute the latest-per-id view).
- Idempotent + crash-safe via the same staging-swap `atomic_write_cozodb` used everywhere.
- **USER APPROVAL REQUIRED before running it against the live ~19k-event DB** (it rewrites every
  element_id key). Back up the DB first (`cp ~/.claude/cache/pss-skill-index.db …`), same as F1.

**Why deferred, not done now:** (a) the name-case decision is genuinely the user's; (b) executing
a full re-key against real history at ~100% window-burn risks a half-migrated DB — the one state
worse than not starting. Fresh session + the case decision → this plan executes cleanly.

**F1 step 3 — retire the plugin-data orphan — NEEDS USER PERMISSION, NOT DONE.** It sits
OUTSIDE the project (`~/.claude/plugins/data/perfect-skill-suggester-emasoft-plugins/`)
and is untracked, so RULE 0 forbids deleting it autonomously. It is now inert (nothing
writes it; verified frozen across two reindexes) and regenerable, so leaving it costs
36 MB and nothing else. Ask before removing.

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
