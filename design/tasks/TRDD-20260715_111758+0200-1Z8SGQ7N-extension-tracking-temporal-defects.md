---
trdd-id: 1Z8SGQ7N
title: Extension-tracking temporal-index design defects — deferred cross-cutting fixes
column: backburner
created: 2026-07-15T11:17:58+0200
updated: 2026-07-17T09:19:17+0200
current-owner: perfect-skill-suggester
task-type: bugfix
parent-trdd: 152e697f
relevant-rules: []
---

## ⏵ STATE — READ THIS FIRST ON RESUME (authoritative) — 2026-07-17 03:40

**✅ v3.10.7 SHIPPED 2026-07-17 09:07** — carried F11+F12+F13+F14 (NOT F10; F10 already
shipped in v3.10.6, verified against the tag). `publish.py --bump patch` RC=0: lint/tests/
validation passed, all 5 binaries built + verified fresh, submodule ref `877f7de` pushed,
tag `v3.10.7` (`a4c9c6d`) + GH release live on remote, 4 version files in sync at 3.10.7.
Shipped binary verified BEHAVIORALLY (not by wrapper exit, per the stale-binaries memory):
`pss 3.10.7` passes the F12 gate — faked `$HOME` + unresolvable `PSS_INDEX_PATH` ⇒
`merge-events` exits 1 and leaves the fallback index untouched; `db-stats` works normally;
real live DB md5 unchanged. **Expected on the user's next real `/pss-reindex-skills`:** the
F11 one-time re-key — ~91 merged plugin ids sweep Removed, 156 true per-project elements
Install, then steady state. Designed and documented, NOT a regression.

**NEXT ACTION:** nothing time-gated remains. The still-open items below are all P3 and
un-urgent; batch them whenever budget allows. **F15 is the cheapest and highest-value**
(a single null `description:` frontmatter in any third-party skill crashes the whole
discovery run; verified; fix is `(frontmatter.get("description") or "")`).

**STILL OPEN after v3.10.7 (all P3, un-urgent):** F9 (needs its comparison site pinned
first), F15 (null `description:` crashes discovery — cheapest, verified), F16 (unhardened
traversals), F17 (non-UTF-8 files invisible; fixing it dissolves F13's deviation). All
specified in the findings list below.

---

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

**UPDATE 2026-07-17 00:15 — F4's "one USER decision" is DISSOLVED: it was a VERIFIABLE
FACT, not a preference. Name case-sensitivity = CASE-SENSITIVE.** Decided on evidence:
- **Internal consistency (the load-bearing fact):** `merge_events_from_reader` groups
  observations by `(element_type, obs.name.clone())` — RAW, original case (temporal.rs
  ~L3096-3099). The pipeline ALREADY treats `Foo` and `foo` as distinct elements at the
  grouping layer; only `compute_element_id` folded them together. Lowercasing the id was
  the LONE outlier, manufacturing collisions between observations the pipeline itself
  considers distinct. Case-preserving RESTORES consistency.
- **Losslessness:** lowercasing is lossy (irrecoverably merges two elements' append-only
  histories); case-preserving is lossless (worst case a spurious, VISIBLE split). For an
  audit log, lossless wins on principle — not preference.
- **The name `name` arrives RAW:** discovery JSONL → `value.get("name")…to_string()`
  (~L3031), and events store `element_name` raw (~L2873). The id was the only fold point.

**EMPIRICAL PROOF on the live 19,258-event / 11,891-element DB (probe, read-only, on a
copy — `scripts_dev/f4f5_probe.py`), BEFORE any migration code ran:**
- **Old-scheme model fidelity: 0 mismatches** — recomputing the old id from each row's own
  columns reproduced the stored `element_id` for all 11,891. The model is exactly right.
- **Un-merge collisions (old_id → >1 new_id): 0.** The re-key is a clean BIJECTION on real
  data; the fail-fast cannot trip. **Injective too** (11,891 distinct new / 11,891 old) ⇒
  the new scheme introduces NO new merges.
- **1,574 / 11,891 ids change (13%):** 1,360 scope_path slug reversal
  (`plugin:buildwithclaude_agents-…` → `…buildwithclaude/agents-…`), 310 name case
  (`agent:explore` → `agent:Explore`), 46 scope_path case.
- **CORRECTION to a prior assumption:** 310 real elements DO carry uppercase names
  ("Explore", "YouTube Researcher", "SVG Matrix Tester") — "CC names are all lowercase-kebab
  so case-sensitivity is a no-op" was WRONG. With 0 collisions it splits nothing, so
  case-preserving is pure fidelity gain at zero risk — a stronger basis than the assumption.
- **No F5 damage in this DB:** the 16 rows with empty `scope_path` on a path-bearing scope
  all have `source='local'` (bare) ⇒ `scope_path_from_discovery_source('local')` = `""`,
  exactly what the live writer emits. Legitimate, not migration damage.
- **The slug's stated rationale is FALSE:** the doc comment claims `/`→`_` keeps the id "a
  single Datalog string token", but ids already contain `:`, `@`, and SPACES today
  (`agent:svg matrix tester@…`) and are always passed as bound `$params`, never bare
  tokens. The slug bought nothing and cost fidelity.

**UPDATE 2026-07-17 00:55 — F4+F5 IMPLEMENTED + GATE PASSED (pre-ship).** Delegated impl
(203/203 Rust tests, red-green proven by breaking the desc `:put` and watching the tests
bite) + THREE mid-flight spec corrections, each from a ground-truth probe of the live DB:
1. `element_descriptions` is element_id-KEYED (9,687 rows) — re-keyed with the same
   pss_id_remap join + the two `:rm` guards (skip unmoved keys; never rm a key that is some
   row's NEW key — the A→B,B→C chain protection).
2. element_ids are EMBEDDED in string VALUES — `override_status` ("overridden_by:<id>" /
   "overrides:<id>", 6 stale each in events + elements_state) and `events.diff_json` (6) —
   remapped via small value-level scratch maps (`pss_status_remap`, `pss_diff_remap`) with
   the matched/unmatched two-rule pattern. Leaving elements_state.override_status stale
   would have re-broken F6 (spurious override events on the next scan).
3. The `migrate-element-ids` verb initially dispatched on the UNLOCKED query path — moved to
   a main() intercept holding both F3 flocks in MergeEvents order (a full-table rewrite has
   a LONGER write window than merge-events; racing hook readers = F3's SIGABRT).
**Empirical ship gate PASSED on the real history** (scripts_dev/f4f5_validate.py, PRE=backup
vs POST=migrated fresh copy, red-tested to FAIL 9 ways on an unmigrated DB): all row counts
invariant (19,258 events / 11,891 state / 9,687 desc), per-element event counts survive,
payloads + state/desc values verbatim (override_status = remapped-expected), 1,369 desc rows
re-keyed, NO changed old id survives anywhere (columns or embedded), changed=1574 —
reproduced identically by 3 independent runs (my probe prediction, agent copy-run, my
fresh-copy run). Idempotent ({"changed":0} on rerun). Live DB untouched (backup at
`~/.claude/cache/pss-skill-index.db.pre-f4f5-validation.20260717_001310+0200`).
**Accepted residual (documented, not fixed):** a SIGKILL in the sub-second window between a
keyed table's `:put` and its `:rm` leaves stale old-keyed duplicates that the re-run
(changed==0) stamps over without sweeping. One-time migration + `backup_index()` always runs
immediately before the auto-run (F1) ⇒ restorable; a cozo two-op transaction does not exist
to reach for, and a residue-sweep would add complexity to guard a backup-covered corner.
**CPV note:** the migration doc comment's safety prose ("never destroy history", "does NOT
drop") tripped skillaudit INTENT_DESTRUCTIVE_INTENT (MAJOR) — reworded positively with an
inline wording-note so it is not "simplified" back into the detector.
**META-LESSON (why 3 corrections):** the spec inventory was assembled from code reading; each
correction came from a LATER ground-truth enumeration. For any key migration, step 0 must be:
enumerate every carrier of the key from the LIVE data — key columns, value columns, ids
EMBEDDED in string values, indices — and every writer path's locking. Column-name scans
structurally cannot see embedded refs.

**UPDATE 2026-07-17 01:06 — F4+F5 SHIPPED (v3.10.5) + LIVE DB MIGRATED + PROVEN.**
- v3.10.5 released via publish.py (submodule 6cd61bf + cc6dc41, parent 09e9871 + release
  commit); both tags on remote; GH release live; shipped binary verified (reports 3.10.5,
  carries the verb + gate key). CPV at ship: CRITICAL=0 MAJOR=0 MINOR=0 (two skillaudit FPs
  devitalized: INTENT_DESTRUCTIVE_INTENT on the safety prose; TOOL_SHADOW on a test fixture
  named "CoolTool" — renamed CoolSkill, uppercase property preserved).
- LIVE migration: fresh backup (`…db.pre-f4f5-live.20260717_010504+0200`) → shipped binary
  `migrate-element-ids` → {"changed":1574}, rerun {"changed":0}; db-stats invariant
  (19,258 events / 11,891 state); FINAL validator PASS (PRE=fresh backup, POST=live);
  `timeline 'agent:Explore@marketplace:my-plugins'` resolves on live.
- Backups retained (do not delete): `…db.pre-f4f5-validation.20260717_001310+0200` (pristine
  pre-migration), `…db.pre-f4f5-live.20260717_010504+0200` (pre-live-migration),
  `~/.claude/cache/f4f5-gate-validation/` (migrated copy used for the gate).
- Installed-plugin note: local install still lags the marketplace; when it updates to
  3.10.5+, the auto-run in merge-events is a gated no-op here (live already migrated).
  Fresh installs / other machines auto-migrate on their first reindex, behind backup_index.

**UPDATE 2026-07-17 01:40 — F7 GROUND-TRUTHED + SPECED + IN FLIGHT.** Step-0 carrier
enumeration FIRST (the F4/F5 meta-lesson), on the live DB + a real discovery run:

- **Removal detection is not leaky, it is INOPERATIVE.** Of 10,484 active elements,
  **799 are genuinely gone** (absent from a real `--jsonl --all-projects` run); today's
  policy marks **1** of them removed — **0.13 %**. 7.6 % of the index is zombie state.
  Measured, then reproduced independently by the ship gate against the shipped v3.10.5
  binary (`removed=1`). Probes: `scripts_dev/f7_probe.py`, `f7_blast.py` (gitignored).
- **Three real shapes, all verified on disk:** (1) scope ROOT GONE (`kazuph-dotfiles` 46,
  `serena-refactor-marketplace` 32); (2) root PRESENT but now yields ZERO elements
  (**`melodic-software` 599** — dir + marketplace.json still there, content changed to 4
  formatter plugins; all 599 rows are `installed` at the single 2026-05-13 seed scan and
  were never seen again); (3) scope RENAMED (`APIAS` → `APIAS-4cc52adb`).
- **DESIGN CHANGED vs this TRDD's original suggestion.** "Derive visited scopes from the
  set of SCANNED ROOTS" **cannot fix shape 1** — a root that no longer exists cannot be
  enumerated from the filesystem. So the fix is a **domain-level claim**: the discoverer
  emits `exhaustive_scopes` (manifest v2) naming the scopes it enumerated COMPLETELY;
  removal detection then sweeps any unobserved active in a claimed scope. One rule, all
  three shapes, ~2 files, no migration. Spec: `scripts_dev/F7-scan-coverage-spec.md`.
- **The claim is the danger** — a false one mass-deletes history — so every filter drops
  a scope (name/type filter ⇒ claim nothing; no `--all-projects` ⇒ no project/local;
  `--exclude-inactive-plugins` ⇒ no plugin/marketplace, since a DISABLED plugin's
  elements are unobserved-but-present and would be reported removed, re-breaking F2's
  distinction; zero elements ⇒ claim nothing; any walk I/O error ⇒ claim nothing —
  `os.walk` at pss_discover.py L548 has NO `onerror`, so an unreadable dir is silently
  indistinguishable from an empty one). Under-claiming only delays a sweep.
- **Predicted post-fix outcome (to be reproduced):** the next full reindex emits **799**
  Removed events over 25 buckets — marketplace 726, plugin 50, project 22, local 1,
  **user 0** — and every one of those 25 buckets is FULLY wiped (100 % of its actives),
  the signature of full-scope removal and the proof the policy does not over-reach into
  partially-present scopes.
- **Ship gate** `scripts_dev/f7_validate.py` (end-to-end on a COPY of the live 19k index;
  predicts the removal SET from PRE+JSONL independently, then asserts POST matches it
  exactly — set equality, not a count). **RED-TESTED: FAILs on the shipped pre-F7 binary**
  (2 checks: 798 zombies survive; removal set off by 798). Also asserts no over-reach,
  no collateral exists-flips, element_ids untouched, idempotency, and non-vacuity.
- **Implementation delegated** (kraken, TDD) against the complete spec — the F4/F5 pattern
  (a mid-flight correction costs a full agent cold-restart, so the spec is finished first).
- **BYCATCH: F11 discovered by the gate's idempotency check** (see below) — an identical
  rescan emitted 51 events; root cause is 64 same-scope install entries collapsing to one
  element_id. Recorded, NOT fixed here (F7 stays one atomic change).

**UPDATE 2026-07-17 02:05 — F7 IMPLEMENTED + GATE PASS (submodule `486e141`, parent
`283c752`; local commits, ride the next release).**
- Producer emits manifest v2 `exhaustive_scopes`; consumer `read_active_in_scope_paths` →
  `read_removal_candidates` adds the domain rule on the SAME bulk projection (DI-4's N+1
  stays fixed). v1 manifest ⇒ empty claim ⇒ byte-identical old behavior.
- **A 4th ground-truth correction — and this one was MY spec's, in the data-loss
  direction.** Spec §4/test 11 gated the `project` claim on `args.all_projects`, but
  `scan_all_projects = args.all_projects and not (args.project_only or args.user_only)`
  (pss_discover.py L2106) makes that flag **INERT** under `--project-only`: only the CWD
  project is enumerated, so the claim would have marked **every other project's elements
  Removed**. The implementer caught it, verified it empirically, and resolved it by the
  spec's own tie-breaker (under-claim ⇒ `[]` unconditionally, no dead branch). Verified
  by me at L2106. Lesson: I enumerated the FLAGS but not the flag→behavior mapping —
  the carrier-enumeration lesson applies to CONTROL flow, not just data.
- **GATE PASS (mine, authoritative): 9/9** on a COPY of the live 19k index —
  `removed=799` reproducing the prediction EXACTLY, 25/25 buckets 100 % wiped, user 0,
  idempotent (2nd identical run: 0 removals), live DB md5 asserted unchanged, producer
  claim == the full scope space. Red-tested first: the same gate FAILS on the shipped
  pre-F7 binary (798 zombies survive). Suites verified by me: rust 208/208, py 284/284,
  ruff clean.
- **±1 drift explained:** the implementer measured 800/2, I measure 799/1 — the janitor
  daemon updates plugins in the background, so the disk moves between runs. NEWLY-removed
  is **798 in both**, and every structural invariant reproduced exactly. The gate predicts
  from the SAME inputs it validates, so it is drift-proof by construction (no magic number).
- **Report's residual G2 is WRONG — corrected here, do not act on it.** It claims
  `Path.exists()/is_dir()` "swallow OSError → False", which would let an UNREADABLE
  marketplace root masquerade as an absent one and wipe ~7k elements. Tested empirically:
  an unreadable dir returns `exists()`/`is_dir()` **True** (stat only needs +x on the
  parent), and the subsequent `iterdir()`/`os.walk` raises PermissionError(13) which IS
  caught and recorded ⇒ claim drops. The catastrophic shape is COVERED.
- **INCIDENT (disclosed by the implementer, verified closed by me):** it ran merge-events
  against the LIVE DB (1368 events incl. 800 removals) after `PSS_INDEX_PATH` was
  **silently ignored** — `get_db_path` (main.rs ~L14507) applies an existence gate on the
  sibling DB and falls back to the real index when it does not resolve. It restored from
  its own pre-write snapshot; I independently confirmed the live DB is byte-identical
  (md5 `5938ad92…`) to my 01:25 pre-kraken copy, both retained backups intact, no staging
  leftovers. → filed as **F12**.

**STILL OPEN:**
- **F9** (P3, observed_at tz/format) + the stage-4 "temporal NOT updated" partial-wording
  tighten. Needs the exact comparison site pinned first. Likely no migration.
- ~~**F11**~~ **DONE 2026-07-17 03:00** (parent `e441687`, local commit — rides the next
  release with F10/F12). Verified three ways: red test on the unfixed code (both sources
  collapse to bare `"local"` — the finding's signature), 289/289 unit suite re-run by me,
  and END-TO-END against the real `installed_plugins.json` (read-only): **156 plugin
  elements now emit 156 distinct identities** (was 91 effective), shapes 76 bare-`user` +
  80 `local:<projectPath>`, `ai-maestro-plugin` 1 → 65 elements — exactly the enumerated
  prediction. Live DB md5 unchanged. The one-time Removed/Installed transition lands on
  the user's next real reindex, as designed. Implementer residuals (accepted, cosmetic):
  `description` string omits the project; pre-existing `version` shadowing in the loop.
  Diagnosis history retained below.
  **(P2, NEW 2026-07-17; DIAGNOSIS CORRECTED 2026-07-17 02:50 — the originally
  filed FIX WAS WRONG IN THE DATA-LOSS DIRECTION)** — same-scan element_id collision in
  `discover_plugins` ⇒ ~51 churn events per scan + non-deterministic recorded version.
  **The filed prescription was "dedupe to ONE entry per (plugin_id, scope) with a
  deterministic winner". DO NOT DO THAT — it would destroy real data.** Ground truth from
  the live `installed_plugins.json` (156 entries / 88 plugin keys), enumerated before
  writing any code:
  - Entries carry a **`projectPath`** field (present on 64/65 of
    `ai-maestro-plugin@ai-maestro-plugins`; absent only on the single `user`-scope entry).
    A `local` install is **per-project**. The 64 local entries are **64 DIFFERENT
    PROJECTS**, each with its own install — **all 64 projectPaths are distinct**, zero
    duplicates. They are not junk to collapse; they are the data.
  - **(scope, projectPath) collides ZERO times across the entire file** — it is empirically
    a total key. So there is nothing to dedupe and **no winner/tiebreak rule to design**.
  - `discover_plugins` sets `source` to the **bare scope string** (`"local"`), so
    `scope_path_from_discovery_source` finds no `local:` prefix and returns `""`. Every
    local entry therefore computes the identical id `plugin:<name>@local:` and they
    overwrite each other in one scan (last-in-array wins). **65 of 156 entries (42%) are
    silently lost today** — which project has which plugin at which version is simply not
    recorded. The churn is the SYMPTOM; the lost 42% is the defect.
  - The function's own docstring ("Each (plugin_id, scope) tuple becomes a separate
    element") **is itself wrong** — it ignores `projectPath`, and the loop iterates
    *entries* anyway. Doc and code are both wrong, in different ways.
  **Corrected fix:** emit `source = f"{scope}:{projectPath}"` when `projectPath` is present,
  else the bare scope. The infrastructure already expects this — `local:`/`project:` are
  already in `scope_path_from_discovery_source`'s prefix list, and post-F4 `element_id`
  carries the scope_path RAW (no lossy slug/lowercase), so distinct projectPaths yield
  distinct ids. No migration is possible (old rows recorded `scope_path=""`, so the merged
  history cannot be un-merged — the projectPath was never captured); the old merged id was
  a fiction conflating N elements, so retiring it is the honest record. Expect a bounded
  ONE-TIME transition: the ~91 old merged ids sweep as Removed (F7 covers `local`/`user`/
  `project` on a full scan) and 156 true elements appear as Installed, then steady state —
  versus ~51 junk events **every scan, forever** today. `user`-scope elements have no
  projectPath, so their ids and history are UNCHANGED.
- ~~**F12**~~ **DONE 2026-07-17 02:45** (submodule `45b2834`, parent `b55ddce`, local
  commits — ride the next release alongside F10). Verified by an independent behavioral
  gate under a faked `$HOME` (`dirs::home_dir()` honors it, so the incident is
  reproducible with zero risk to the live index): the shipped v3.10.6 binary
  **exits 0 having WRITTEN the fallback index**; the fixed build **exits 1 with
  "no CozoDB index found" and leaves it untouched**. RED arm proves the gate can fail.
  214/214 Rust (re-run by me, not taken on trust), 284/284 Python, clippy 62→62.
  Real live DB md5 `5938ad92…` unchanged throughout. Original analysis retained below.
  **Accepted residuals:** (a) `--index ""` now yields `None` where
  `resolve_db_path_canonical` still reports the home default — degenerate, documented
  inline, and it makes the two RUNTIME resolvers agree (`get_index_path("")` already
  errors), so nothing silently reads the real index; (b) tests use a hand-rolled 12-line
  `TmpDir` because `tempfile` is NOT a dev-dependency (my spec claimed it was — wrong;
  the implementer verified and worked within the edit-only-main.rs constraint). Its
  `Drop` can only remove the exact `$TMPDIR/pss-f12-*` path it created — reviewed;
  (c) test 1 is not hermetic (it can only fail where a real index exists) — **test 3 is
  the machine-independent regression guard**; both kept.
  **Original analysis —** `PSS_INDEX_PATH` set-but-unresolvable is silently ignored and falls back to the user's
  REAL index (main.rs `get_db_path`, existence gate with no else). A fail-fast violation
  that already caused one accidental live write; any tool aiming at a scratch DB silently
  writes the real one.
  **WORSE THAN FIRST FILED — verified by reading all three resolvers 2026-07-17:**
  1. It is **two** fall-throughs, not one: `--index <json>` (L14501) has the identical
     no-`else` gate, so a failed `--index` silently defers to `PSS_INDEX_PATH` —
     a **priority inversion** against the documented `--index` > env order.
  2. PSS has **three** resolvers claiming one resolution order, and only the runtime one
     falls back: `resolve_db_path_canonical` (L14547, backs `pss db-path`) and
     `pss_cozodb.get_db_path` (scripts/pss_cozodb.py:159) both honor an override
     **unconditionally**. So **`pss db-path` reports a path the binary does not use** —
     and that subcommand's own doc-comment says it exists so external consumers "stop
     reverse-engineering PSS's path-resolution". The P-2 contract lies exactly the way
     that misled the F7 implementer. This is the real severity.
  **Fix (refined):** an override is AUTHORITATIVE — resolve only from it, return `None`
  when it does not resolve, never fall through. **No caller changes:** `None` is already
  correct at all 8 sites (3 writers eprintln+exit; `open_db_for_query` → `IndexNotFound`;
  3 readers fall back to the JSON index, which honors the SAME override via
  `get_index_path`, so they never silently read the real one).
  **Invariant to preserve:** the `.db` asymmetry (`--index x.db` → `x.db` itself;
  `PSS_INDEX_PATH=x.db` → the *sibling* `pss-skill-index.db`) is intentional, documented
  at pss_cozodb.py:150-153, and mirrored by all three resolvers — a shared
  `db_from_override` helper would silently break it and `tests/unit/test_pss_db_path_parity.py`.
  Spec: `scripts_dev/F12-override-authoritative-spec.md` (gitignored).
- ~~**F13**~~ **DONE 2026-07-17 03:35** (parent `34c1287`, local — rides the next release).
  All 25 `except OSError` sites classified under one rule (record iff the failure can make
  an on-disk element absent from the stream), per-site audit table in
  `reports/pss-f13-scan-error-routing/20260717_031127+0200-f13-impl.md`. 12 grep sites +
  3 sibling JSONDecodeError arms wired (the realistic unreadable-file failure lands there —
  `_safe_read_text` swallows the OSError and `json.loads("")` raises); 2 probe-gated
  (marketplace-MCP/monitor manifest loops parse EVERY third-party manifest, and a real
  BOM'd `plugin.json` on this machine would have kept the claim off forever under blanket
  recording); **2 deliberately NOT wired** (per-element non-UTF-8 reads: a never-emitted
  element is never Installed so never swept — no churn to prevent — while wiring would
  permanently disable removal detection on any machine hosting one such file; two exist
  here; pinned by test). Red test demonstrated (unreadable `installed_plugins.json` dropped
  all plugin elements with an empty `_scan_errors` and a FULL claim); 295/295 suite re-run
  independently; post-fix real-machine full run: 0 scan errors, all 5 scopes claimed.
  Original entry: F7's scan-error accumulator covers only the scope-root
  enumeration in `get_all_element_locations`. The type-specific discoverers
  (`discover_hooks`/`_plugins`/`_marketplaces`/`_mcp_servers`/`_monitors`/`_output_styles`/
  `_themes`) have their own `except OSError: continue` paths that do NOT feed
  `_scan_errors`, so a transient per-file read failure can drop elements while the claim
  still stands ⇒ spurious Removed/Installed churn. Bounded and self-healing (append-only
  events; next clean scan re-installs), so accepted for F7. Route those handlers into
  `_record_scan_error`.
- **F15** (P2/P3, NEW 2026-07-17, VERIFIED by F13's implementer against a fixture) — a
  SKILL.md / agent / command `.md` whose frontmatter has `description:` with NO value makes
  `frontmatter.get("description", "")[:200]` raise `TypeError: 'NoneType' object is not
  subscriptable`, UNCAUGHT — the entire discovery run dies (`discover_elements`, pre-F13
  L1823/L1888). One third-party skill with an empty description bricks PSS reindexing
  outright. Fail-safe in the narrow sense (no manifest ⇒ nothing swept ⇒ no data
  corruption), but a total indexing outage. Fix: `(frontmatter.get("description") or "")`.
- **F16** (P3, NEW 2026-07-17, VERIFIED by F13's implementer) — remaining unhardened
  traversals in the type discoverers: (a) `os.walk` in `_discover_marketplace_mcps`
  (~L842) has no `onerror=` — an unreadable subdirectory silently truncates the config
  enumeration without recording (the F13 shape, but not one of the 25 except sites);
  (b) bare `.iterdir()` chains in `discover_hooks` (plugin-cache traversal),
  `discover_monitors`, `discover_output_styles`, `discover_themes` — an OSError there
  propagates and ABORTS the whole run (nothing emitted, exit non-zero; fail-fast, so no
  wrong sweep, but a scan outage). Fix: `onerror=_record_scan_error` + `_iterdir_safe`.
- **F17** (P3, NEW 2026-07-17, VERIFIED) — non-UTF-8 element files are permanently
  INVISIBLE to discovery (never emitted; two live cp1252 `.md` files on this machine).
  Suggested fix: read element content with `errors="replace"` (or catch
  `UnicodeDecodeError` in `_safe_read_text`), converting the drop into a degrade — after
  which F13's deliberate 1839/1905 deviation becomes moot and can be removed.
- ~~**F14**~~ **DONE 2026-07-17 03:25** (submodule `bcbc6d5`, parent `1ce32a4`, local —
  rides the next release). Pure `resolve_db_path_canonical_gated(cli, env)` + 3-line
  wrapper; ZERO behavior change with all three deliberate properties pinned by tests (no
  existence gate; `.db` asymmetry; the empty-`--index` fall-through divergence, test-pinned
  with the TRDD reference so changing it requires a conscious decision). No canonical test
  skips on env anymore. 219/219 re-run independently; clippy diagnostics byte-identical;
  9/9 fresh-vs-prebuilt `db-path` outputs byte-identical (the prebuilt binary embodies
  pre-change behavior, closing the stale-binary parity gap). Implementer observation:
  `get_index_path` (main.rs:9998) also reads the env var directly but contains no
  conditional logic that could hide an F12-shaped bug — observation only, no finding.
  Original entry: `resolve_db_path_canonical`
  still reads `std::env::var("PSS_INDEX_PATH")` directly, so it stays env-untestable and its
  test (`resolve_db_path_canonical_default_is_home_cache_db`, main.rs ~L22533) **SKIPS**
  whenever that var is set. **That is the exact coverage hole that let F12 live**: the
  resolver nobody could test was the resolver nobody noticed was wrong. F12 closed the hole
  for `get_db_path` only (by parameterizing the env value into `resolve_db_path_gated`);
  the canonical twin still has it. Give it the same `(cli, env)` parameterization. Not done
  under F12 because the spec scoped it out ("only if it falls out for free" — it does not:
  separate signature, 3 call sites). Cheap; batch with F9/F11/F13.
- ~~F10~~ DONE 2026-07-17 01:15 (submodule `bbdfa8f`, local commit — rides the next
  release): prune-history now intercepted in main() holding both F3 flocks; old arm is an
  internal-error guard; 203/203 tests; dry-run verified against the live DB.
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

**F11 — P2 — same-scan element_id collision in `discover_plugins` ⇒ permanent event
churn + NON-DETERMINISTIC state.** FOUND 2026-07-17 by the F7 ship gate's idempotency
check (a re-run of an IDENTICAL scan emitted 51 events — a no-change rescan must emit
zero). `discover_plugins` (pss_discover.py ~L1377) emits one element per install ENTRY,
but its own docstring states the intended grain: "Each (plugin_id, **scope**) tuple
becomes a separate element". `installed_plugins.json` v2 accumulates one entry per
install, so the same (plugin_id, scope) recurs — **verified live: `ai-maestro-plugin@
ai-maestro-plugins` has 64 entries ALL at scope `local`** (versions 2.5.0 … 2.10.0),
`dev-browser@ai-maestro-plugins` has 3; 67 colliding entries over 2 plugin ids. All
64 collapse to the single element_id `plugin:ai-maestro-plugin@ai-maestro-plugins@local:`
(the id has no version component — correctly so, per F4), so within ONE scan they
overwrite each other, each transition emitting content/description/size/path_changed.
Consequences: (a) ~51 spurious events EVERY scan, forever — a prime suspect for the
"events full-scan growth" item below; (b) `elements_state` ends up holding whichever
entry the HashMap happened to yield last, so the recorded version is non-deterministic
across runs; (c) `version-history`/`plugin-history` read that churn as real version
flapping. Fix: dedupe to ONE entry per (plugin_id, scope) with a DETERMINISTIC winner
(newest `lastUpdated`/`installedAt`, tie-broken explicitly) so a genuine upgrade emits
exactly one `version_changed`. NOT a temporal-index bug — the writer is faithfully
recording what the discoverer hands it. Batch with F9 (both are event-quality).

## Scope

One coordinated follow-up (or a small set of child TRDDs, F1 first as its own). Each fix
either changes stored id/timestamp/state semantics or spans Python+Rust — hence deferred
from the review's `--fix` pass. Terminal when every F# is fixed-or-consciously-accepted with
a migration for the id/timestamp-schema changes (F4, F5).
