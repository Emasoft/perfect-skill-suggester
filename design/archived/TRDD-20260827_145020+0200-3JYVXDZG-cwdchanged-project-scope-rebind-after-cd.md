---
trdd-id: 3JYVXDZG
title: Rebind project-scoped element inventory on a mid-session /cd
column: complete
created: 2026-08-27T14:50:20+0200
updated: 2026-08-29T16:05:00+0200
current-owner: perfect-skill-suggester
task-type: bugfix
min-approval-requirement: none
priority: low
labels: [hooks, indexing, cc-compat]
relevant-rules: []
---

# Rebind project-scoped element inventory on a mid-session `/cd`

## ⏵ STATE — READ THIS FIRST ON RESUME (authoritative; supersedes the body) — 2026-08-29

**DONE — but NOT the way this card specified. The card's own diagnosis was WRONG, and the
fix it prescribed would not have worked. Read this before believing anything below it.**

**What the card claimed:** PSS binds the project scope once at index-build time and never
rebinds, so after `/cd` A→B the index still holds A's elements and lacks B's. Fix: declare
`CwdChanged` and rebind.

**What is actually true (measured, not reasoned):** `pss_reindex.py:201` runs
`pss_discover.py` with **`--all-projects`**, so the index is CROSS-PROJECT by construction —
every registered project at once. Live DB, 2026-08-29: **689 `project:` rows spanning 20
distinct projects, plus 111 `local:` rows.** So B's elements were never missing and A's were
never stale; the index simply contains everyone.

**Therefore the prescribed fix was a no-op.** Reindexing bound to B leaves all 20 projects
in the index — A's elements remain exactly as scoreable as before. Declaring `CwdChanged`
would have shipped, passed its own acceptance criteria as written, and fixed nothing.

**The real defect** is the one the card's own "Verified facts" section had already proved
and then talked past: *nothing filters a candidate by its origin* — not at load, not on the
way in, not in the scoring loop. The consequence is not a `/cd` edge case at all; it is that
**every prompt in every project is scored against all 20 projects, always.** `/cd` was only
the most visible symptom.

**Observed live, in-session:** while working in the PSS checkout, PSS suggested
`svg-matrix-tester`, whose source is `project:SVG-MATRIX-d055d603/plugin:svg-matrix-tester`.
An element from an unrelated project, for an unrelated prompt.

**The fix (v3.14.2):** `main.rs::is_foreign_project_element`, applied at the existing
invocability `retain` (`main.rs:~19180`) that already culls `marketplace:` sources — one
predicate at a site that already exists, already re-derives `build_name_index()`, and is
already outside the hot loop. It drops candidates belonging to a project other than the live
`input.cwd`'s. **Because it keys on the live per-prompt cwd, `/cd` is fixed for free** — the
first prompt after the move is already correctly scoped, with no reindex, no hook, and no
window of staleness. That is strictly better than the rebind this card asked for, which
would have left a gap until the async reindex finished.

**Two shapes the obvious implementation gets wrong — do NOT "simplify" these away:**
- `local:<abs-path>` is a raw PATH, not a slug. One `starts_with` cannot cover both.
- Bare `project` and `project:agentskills` carry NO slug — they mean "whatever the cwd was
  at INDEX time" — so they are decided by the element's `path`, not its source. Keeping them
  blindly re-leaks the index-time project; **dropping them blindly erases the current
  project's own elements**, because `pss_discover.py:946` seeds `seen_project_paths` with
  `{cwd}` and skips it in the registry loop — the cwd project has NO slugged duplicate to
  fall back on. Both directions are covered by
  `unslugged_project_sources_are_decided_by_path_not_by_source`.

**Verification:** 306 Rust tests pass (0 failed, 0 own-crate warnings), two of them new; plus
an end-to-end check on the BUILT RELEASE BINARY, no mocks — the same prompt yields the
SVG-MATRIX agents from `Code/SVG-MATRIX` and nothing from the PSS checkout, while unrelated
prompts still return plugin/marketplace agents at HIGH confidence from both.

**Also folded in:** the long-carried "R17.24 suggest-time gap" open item. `R17.24` has
**zero occurrences repo-wide** across every file type — it is an unresolvable citation
carried across two session handoffs. Its described symptom ("suggest-time gap") is precisely
this defect, and the fix lives at suggest time, so it is closed here rather than left to be
re-asked a third time.

**SUPERSEDED — do NOT carry forward:**
- The `CwdChanged` hook approach, in full. Not deferred — *disproven*. Do not revive it.
- The premise "PSS binds the project scope ONCE and never rebinds". The binding was never
  the problem; the missing filter was.
- The "Priority note" below calling this low and needing a cross-project `/cd` to bite. It
  fires on every prompt in every project.

**Still true below:** the `--warm-index` analysis (it early-returns on a populated DB, so it
could never have rebound anything) and the METHOD NOTE on anchoring a search range before
searching it.


PSS binds the project scope ONCE, at index-build time, and never rebinds it. After a
mid-session `/cd` from project A to project B, prompt-time *context* follows the move but
the element *inventory* does not: PSS keeps scoring A's project-scoped elements while the
user is working in B.

Claude Code 2.1.246 unloads A's project-scoped elements immediately on `/cd`, which turns
this from "B's elements are missing" into "PSS suggests elements the harness no longer has
loaded". Both halves are live (see Verified facts).

This is a PRE-EXISTING defect, not a v2.1.246 regression — 2.1.246 only sharpened it. It
also makes the `CwdChanged` "not declared (intentional)" rationale in
`docs/CC-COMPATIBILITY.md` imprecise: the event is not declared, and there IS a reason to
declare it.

## Verified facts (first-hand, 2026-08-27)

- `scripts/pss_discover.py:89-94` — `get_cwd()` returns `$CLAUDE_PROJECT_DIR` or
  `Path.cwd()`, resolved once when the index is built. Nothing re-resolves it later.
- `hooks/hooks.json` declares exactly three events — read from the parsed `hooks` object's
  own keys, not matched against a remembered list of event names: `UserPromptSubmit`,
  `SessionStart`, `PostCompact`. No `CwdChanged`.
- `rust/skill-suggester/src/main.rs:19247` — the live `input.cwd` is passed only to
  `scan_project_context`, i.e. prompt-time context inference.
- `find_matches` spans `main.rs:8076-9718` (end established from the first column-0 `}`
  after the signature, not assumed). Across that FULL range `cwd` appears exactly twice:
  `:8080` (the parameter) and `:8680` — `if cwd.contains(dir) { score += weights.directory }`,
  a positive scoring BONUS. No scope-vs-root comparison anywhere in the candidate loop.
- The `cwd` VALUE cannot travel under another name: a rebinding must mention `cwd` on its
  right-hand side, so the same search that found `:8080`/`:8680` would have caught it. The
  other candidate carrier was ruled out by reading the type — `struct ProjectContext` holds
  only `platforms/frameworks/languages/domains/tools/file_types`, no root or path field.
- One REAL hard exclusion exists in the loop, and it is not a root filter: `main.rs:8481-8493`,
  `check_path_gates(&entry.path_gates, &context.file_types, &context.languages)` — for
  `skill_type == "rule"` only, a failing gate `return None`s the entry. It keys on the RULE's
  own declared `paths:` globs versus the project's detected file types/languages. Those come
  from `scan_project_context(&input.cwd)`, i.e. the LIVE cwd — so **rules already re-gate
  correctly across a `/cd`**; skills and agents have no equivalent, which is precisely the
  asymmetry this TRDD is about. (`:8688` `entry.path_patterns` is unrelated — matched against
  the PROMPT text for a scoring bonus.)
- No `continue`-guard filter on origin: all 17 `continue`s in `8076-9718` were read WITH the
  `if` above them, not inferred from the matched line. They key on `LOW_SIGNAL_WORDS`
  (`:8735`/`:8788`/`:8838`), word length (`:8978`/`:9016`/`:9062`/`:9158`/`:9193`/`:9236`),
  `NAME_INFERABLE_FRAMEWORKS` (`:8918`), or an already-matched set (`:9630`). None on
  `entry.source`, a root, or the element's origin.
- No caller-side filter: the only `source`-based cull before scoring is `main.rs:19182`
  (`retain` dropping `marketplace:` sources and non-invocable ids), unrelated to the root.
- No load-time filter, on EITHER loader — the hot path can take either:
  `load_index_from_db` (`:14835`) is an unconditional `*skills{ ... }` scan, and
  `load_candidates_from_db` (`:14954`) narrows via
  `candidates[name] := *kw_lookup{keyword_lower: w, skill_name: name}` — by KEYWORD, with no
  `source`/`path`/root predicate in the Datalog.

  So a project-scoped entry belonging to A is never excluded BY ITS ORIGIN when the live cwd
  is B — not at load, not on the way in, and not in the scoring loop.

  METHOD NOTE (twice corrected before it hardened): the first pass searched
  `NR>=8076 && NR<=8900`, a window whose upper bound was arbitrary and 818 lines short of the
  function's real end. It happened to reach the right conclusion, but a filter living in
  8900-9718 would have read identically to no filter at all. Anchor the range, then search.
  The second pass then over-claimed in the other direction: "no filter anywhere" was a
  UNIVERSAL NEGATIVE gathered from one file with a two-shape regex (`retain(` and a narrow
  `.filter(...)`), structurally blind to `continue` guards, `match` arms, and anything at
  index-load. Each of those was then checked directly. The THIRD pass then caught the worst
  of the three: `:8483 &entry.path_gates` was sitting in my own search output, unaccounted
  for, while the card asserted "none keys on a path" — and 11 of the 17 `continue`s had
  printed bare, their guards never read, with "they key on word length" extrapolated from the
  6 that happened to show a predicate inline. Matched lines are not control flow. Read the
  guard, not the line that matched.

## The obvious fix does NOT work — record before anyone tries it

Declaring `CwdChanged` → `pss_hook.py --warm-index` (mirroring the SessionStart entry) is a
NO-OP after a `/cd`. `--warm-index` exists (`scripts/pss_hook.py:1132` → `_warm_index`,
`:1043`), but `:1063-1065` early-returns when `db_path.exists() and count_skills() > 0` —
its job is "warm an EMPTY index", not "rebind a stale one". After a `/cd` the DB is
populated with A's elements, so the handler returns immediately and nothing changes.

A real fix needs an explicit re-discovery of PROJECT-scoped elements against the new root
(dropping A's), not the emptiness check.

## Acceptance criteria

Criteria 1, 2 and 5 named a MECHANISM (`CwdChanged` + a rebind handler) that measurement
showed cannot fix the defect — see the STATE block. They are withdrawn as written; the
REQUIREMENT they existed to serve is criterion 3, and it is met. Recorded rather than
silently reworded, because "we shipped the criteria we could pass" is how a card lies.

- [~] ~~`CwdChanged` declared in `hooks/hooks.json`~~ — **WITHDRAWN, deliberately NOT
      declared.** The filter keys on the live `input.cwd` every `UserPromptSubmit` already
      carries, so `/cd` is correct on the very next prompt with no event. Declaring one
      would schedule work the next prompt does anyway.
- [~] ~~handler re-resolves the project root from the event's cwd~~ — **WITHDRAWN**, no
      handler exists. Its intent (never trust a session-start `CLAUDE_PROJECT_DIR`) is
      honoured more strictly: the comparison root is re-derived per prompt from
      `input.cwd`, so nothing is captured at any point.
- [x] **After `/cd` A→B, project-scoped elements of A are no longer scoreable and B's are.**
      Verified end-to-end on the built release binary, no mocks — identical prompt, two
      cwds: from `Code/SVG-MATRIX` the two SVG-MATRIX agents are suggested (HIGH, 0.60);
      from the PSS checkout the same prompt yields nothing. Both halves, one command each.
- [x] **User-scope and plugin-scope elements are untouched.** Three unrelated prompts from
      the PSS cwd still return 4 plugin/marketplace agents each at HIGH confidence, and the
      predicate returns `false` for `user:` / `plugin:` / `built-in:` under test.
- [~] ~~handler is non-blocking and silent~~ — **WITHDRAWN**, no handler. The property is
      met vacuously and then some: the filter is one predicate inside a `retain` the hot
      path already ran, so it adds no process, no I/O and no output.
- [x] **`docs/CC-COMPATIBILITY.md`** — the `CwdChanged` "not declared (intentional)"
      rationale is rewritten (it was right by accident), and the v2.1.246 open-question
      paragraph now carries an explicit RETRACTION of its own diagnosis plus this id.

## Priority note

Low. The defect needs a mid-session cross-project `/cd` to bite. Early signal that it
matters in practice: a post-`/cd` prompt yields suggestions naming the PREVIOUS project's
agents.

## Provenance

Surfaced while assessing CC 2.1.241-246 (commits bd96185..92ba276, docs-only). A
`fable-advisor:advisor` consult confirmed the defect and proposed the `CwdChanged` shape;
its `--warm-index` suggestion was checked here and found insufficient (above). The advisor
also reported the doc header and `CLAUDE.md` still needing a version bump — that was stale,
both already read 2.1.246.

## Approval log

- 2026-08-29T15:08:09+0200 — **COMPLETE**, under the USER's explicit delegation to complete
  every pending TRDD and decide autonomously (2026-08-29). `min-approval-requirement: none`
  (Tier 0) — an in-scope bugfix in this project's own code, no approval gate.

  Closed on the REQUIREMENT, not on the plan: the card's prescribed mechanism was disproven
  mid-execution (see the STATE block) and its three mechanism criteria are marked WITHDRAWN
  with reasons rather than reworded into something passable. What shipped fixes strictly more
  than the card asked — the defect turned out to fire on every prompt in every project, not
  only after a `/cd`.

  Evidence: 306 Rust tests pass (0 failed, 0 own-crate warnings), two new; the Suggestion
  Accuracy Gate (`pss_test_e2e.py`, the gate the local `--gate` does NOT run and which shipped
  red twice before) is 6/6 against the NEW binary, not the old one; and the fix was verified on
  the binary extracted FROM the tag — `git ls-tree v3.14.2 rust` → `merge-base --is-ancestor`
  confirms commit `1189367` is in the shipped gitlink, and `git show v3.14.2:bin/pss-darwin-arm64`
  filters the foreign project's agents while still returning them from that project's own cwd.

  Shipped in **v3.14.2** (`--force-build`, because the change lives inside the `rust/` submodule
  — the shape that produced a stale shipped binary on an earlier release).

- 2026-08-29T16:05:00+0200 — **CORRECTION after adversarial review. Three claims in the entry
  above were overstated or wrong; a real defect in the shipped fix was found and fixed.**
  (`## Approval log` is append-only and EXEMPT from the terminal-column freeze — that exemption
  is exactly for this.)

  **1. A REAL BUG in v3.14.2, now fixed.** `HookInput::cwd` is `#[serde(default)]`, so a payload
  without the field deserializes to `""`. `project_slug("")` is a degenerate slug matching no
  real project, so the filter reported EVERY project-scoped element as foreign — all 689, in
  every project, on every prompt. Verified, not theorised: `echo '{"prompt":"..."}' | pss` with
  no `cwd` returned only plugin-scope agents; the project-scoped ones were gone.
  **How it got past me:** every verification I ran hand-constructed the JSON *with* `cwd`
  present. The one path that resembles the real hook — `pss_test_e2e.py` — passes no `cwd` at
  all, and I noticed that and dismissed it because its fixtures use `source: "test"`, which is
  precisely why it could not have caught this. I made an unverified assumption load-bearing for
  DELETION without re-verifying it at that new load; before the patch an absent `cwd` merely
  degraded ranking.
  **Fix:** an empty `cwd` now DISABLES the predicate instead of applying it. This is the
  deliberate opposite of the per-element unprovable-path rule, and the asymmetry is the point —
  an unknown local to one element costs one suggestion when it fails closed, an unknown that
  destroys the comparison BASIS costs a whole scope class. Degrading to the pre-v3.14.2 leak is
  visible and recoverable; silently emptying a scope is neither. Test:
  `empty_cwd_would_condemn_everything_so_the_caller_must_gate_on_it`. 307 pass.

  **2. The e2e citation above is WITHDRAWN as evidence FOR this change.** `pss_test_e2e.py`
  fixtures carry `source: "test"`, which hits the predicate's final fallthrough — so the
  Suggestion Accuracy Gate never exercises project-scoped filtering at all. It is real evidence
  of pipeline NON-REGRESSION and nothing more. Citing it for the filter was claiming coverage
  that does not exist.

  **3. "0 own-crate warnings" was a COUNT, not a reading**, and taken from a run that predated
  the final code. Re-checked by content on the current tree: the two warnings are a workspace
  `profiles for the non root package` note and a `proc-macro-error2` future-incompat dep note.
  Neither is PSS code. The claim holds — but it did not hold *because I had checked it*.

  Not disputed on review, and re-confirmed: `Path::starts_with` is component-wise, so the
  `/tmpother` vs `/tmp` assertion is sound for the right reason; and `python_resolve` handles
  non-existent paths Python-style.
