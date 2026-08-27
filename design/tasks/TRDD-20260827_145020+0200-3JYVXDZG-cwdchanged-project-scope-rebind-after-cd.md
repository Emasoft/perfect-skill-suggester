---
trdd-id: 3JYVXDZG
title: Rebind project-scoped element inventory on a mid-session /cd
column: backburner
created: 2026-08-27T14:50:20+0200
updated: 2026-08-27T15:06:00+0200
current-owner: perfect-skill-suggester
task-type: bugfix
min-approval-requirement: none
priority: low
labels: [hooks, indexing, cc-compat]
relevant-rules: []
---

# Rebind project-scoped element inventory on a mid-session `/cd`

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
- No caller-side filter either: the only `source`-based cull before scoring is `main.rs:19182`
  (`retain` dropping `marketplace:` sources and non-invocable ids), which is unrelated to the
  project root. So a project-scoped entry belonging to A is never excluded when the live cwd
  is B — not in `find_matches`, and not on the way in.

  METHOD NOTE (this claim was corrected before it hardened): the first pass searched
  `NR>=8076 && NR<=8900`, a window whose upper bound was arbitrary and 818 lines short of the
  function's real end. It happened to reach the right conclusion, but a filter living in
  8900-9718 would have read identically to no filter at all. Anchor the range, then search.

## The obvious fix does NOT work — record before anyone tries it

Declaring `CwdChanged` → `pss_hook.py --warm-index` (mirroring the SessionStart entry) is a
NO-OP after a `/cd`. `--warm-index` exists (`scripts/pss_hook.py:1132` → `_warm_index`,
`:1043`), but `:1063-1065` early-returns when `db_path.exists() and count_skills() > 0` —
its job is "warm an EMPTY index", not "rebind a stale one". After a `/cd` the DB is
populated with A's elements, so the handler returns immediately and nothing changes.

A real fix needs an explicit re-discovery of PROJECT-scoped elements against the new root
(dropping A's), not the emptiness check.

## Acceptance criteria

- [ ] `CwdChanged` declared in `hooks/hooks.json` (available since CC 2.1.83).
- [ ] Its handler re-resolves the project root from the event's cwd — it MUST NOT trust a
      `CLAUDE_PROJECT_DIR` captured at session start.
- [ ] After `/cd` A→B, project-scoped elements of A are no longer scoreable and B's are.
- [ ] User-scope and plugin-scope elements are untouched by the rebind.
- [ ] The handler is non-blocking and silent, per the existing SessionStart contract.
- [ ] `docs/CC-COMPATIBILITY.md` — replace the `CwdChanged` "not declared (intentional)"
      rationale and fold the v2.1.246 open-question paragraph into this TRDD's id.

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
