---
name: pss-index-is-cross-project
description: "PSS suggested an agent from a different project / why is it suggesting something the harness never loaded / unrelated project's skills scored against my prompt / cross-project suggestion leak / is the PSS index bound to one project / does a mid-session /cd rebind the element inventory / do I need a CwdChanged hook to rescope suggestions / the index still has the old project's elements after cd / how many projects are in the skill index / what does --all-projects do to the index / what is the bare 'project' source / project: vs local: source format / why does the cwd project have no slug / seen_project_paths skips the cwd / how do I filter candidates by their origin project / where is the suggest-time origin filter / is_foreign_project_element / agents from another checkout keep appearing / the TRDD prescribed a fix that turned out wrong / acceptance criteria all pass but the bug remains / I implemented what the card said and nothing changed / should I trust a card's diagnosis or re-measure the premise / shipped a no-op fix / draining the board blindly / confident wrong fix / my test passes when I delete the guard / tautological test asserting trim is_empty / testing a copy of the logic instead of the logic / how do I mutation test a guard / is my test actually a tripwire / the guard has no regression coverage / fail open vs fail closed / all project-scoped elements dropped at once"
ocd: 2026-08-29
lmd: 2026-08-29
publish-globally: true
metadata:
  node_type: memory
  type: project
  tier: component
---

# pss-index-is-cross-project


^ATOM-JNE2-WNZJ [desc: "The PSS index holds EVERY registered project at once (--all-projects), so origin must be filtered at suggest time, not by rebinding the index.", keywords: cross-project_suggestion agent_from_another_project --all-projects index_bound_to_one_project CwdChanged_rebind mid-session_cd project_scoped_elements is_foreign_project_element bare_project_source seen_project_paths pss_reindex.py_all-projects suggest-time_origin_filter 689_project_rows_20_projects harness_never_loaded_that_element rescope_after_cd, trdd: TRDD-3JYVXDZG, ocd: 2026-08-29, lmd: 2026-08-29]
PSS's index is **cross-project by construction**: `pss_reindex.py:201` runs
`pss_discover.py` with **`--all-projects`**, so every project registered in
`~/.claude.json` lands in one DB. Measured 2026-08-29 on the live index: **689
`project:`-scoped rows spanning 20 distinct projects, plus 111 `local:` rows.**

So an element's presence in the index says **nothing** about which project owns it.
Until v3.14.2 nothing filtered by origin at any stage — not at either DB loader, not
entering the scoring loop, not inside it — so every prompt in every project was scored
against all 20 projects. Those suggestions are worse than noise: the harness has not
LOADED another project's elements, so naming one is unactionable by construction.

The filter is `main.rs::is_foreign_project_element`, applied at the invocability
`retain` that already culls `marketplace:`. It keys on the **live per-prompt
`input.cwd`**, which is why a mid-session `/cd` needs no hook at all: the next prompt is
already correctly scoped, with no reindex and no stale window.

Source shapes are NOT uniform — see [[pss-index-is-cross-project]]'s sibling atom.
Related: [[incremental-merge-must-seed-from-live-db]], [[pss-knowledge-hub]]. [^1] [^2]


^ATOM-QE22-ADRI [desc: "The five project-scoped source spellings, and why bare 'project' must be judged by path rather than kept or dropped.", keywords: project_source_format local_source_absolute_path bare_project_source project:agentskills slug_vs_path seen_project_paths cwd_project_has_no_slug how_to_tell_which_project_owns_an_element project_slug_8_hex filter_by_origin_project scope_path_from_discovery_source element_origin which_project_does_this_element_belong_to, trdd: TRDD-3JYVXDZG, ocd: 2026-08-29, lmd: 2026-08-29]

The five project-scoped `source` spellings, and how each is judged against the live cwd:

| source | meaning | judge by |
|---|---|---|
| `project:<slug>` | a specific project (`<basename>-<8 hex>`) | slug |
| `project:<slug>/plugin:<n>` | that project's local plugin | slug, up to the first `/` |
| `local:<absolute path>` | a raw PATH, **not** a slug | resolved path |
| `project` (bare) | whatever the cwd was AT INDEX TIME | the element's `path` |
| `project:agentskills` | the index-time cwd's `.agents/` | the element's `path` |

**The trap is the bare `project` row, and it bites in BOTH directions.** Keeping it
unconditionally re-leaks the index-time project through the one case a slug comparison
cannot see. Dropping it unconditionally **erases the current project's own elements** —
`pss_discover.py:946` seeds `seen_project_paths` with `{cwd}` and skips it in the
registry loop, so the cwd project is emitted ONLY in bare form and has no slugged
duplicate to fall back on. A path test is the only honest discriminator; an unprovable
path must fail closed (one missing suggestion beats restoring the leak).

## Notes and lessons learned

[^1]: [id: ATOM-U2RW-Y4R2, status: valid, desc: "A card's stated fix can pass its own acceptance criteria while fixing nothing — verify the DIAGNOSIS, not just the criteria.", keywords: "TRDD_prescribed_the_wrong_fix acceptance_criteria_pass_but_bug_remains card_diagnosis_wrong implement_what_the_card_says verify_the_premise_not_the_plan CwdChanged_would_not_have_worked confident_wrong_fix resume_a_card_without_rechecking_its_facts drain_the_board_blindly I_fixed_it_but_the_bug_is_still_there shipped_a_no-op_fix trust_the_TRDD_or_re-measure", ocd: 2026-08-29, lmd: 2026-08-29] DO NOT implement a card's prescribed fix without first re-verifying the DIAGNOSIS it rests on, BECAUSE acceptance criteria are written against the assumed mechanism, so a wrong premise ships a change that passes every box and fixes nothing — TRDD-3JYVXDZG specified a `CwdChanged` rebind for an index it believed was bound to one project; the index holds all 20, so the rebind was a no-op and its criteria would still have gone green. DO re-measure the premise first (here: one query showed 689 rows over 20 projects), and when it falls, mark the mechanism criteria WITHDRAWN with the reason rather than rewording them into something passable.
[^2]: [id: ATOM-8PRE-WMO2, status: valid, desc: "A guard tested by re-expressing it in the test is untested — assert on the composed function the caller actually invokes, and prove it by mutation.", keywords: "tautological_test test_passes_when_I_delete_the_guard cwd_guard_regression assert_on_trim_is_empty testing_a_copy_of_the_logic mutation_test_the_guard is_my_test_actually_a_tripwire guard_has_no_test_coverage fail_open_fail_closed_guard unused_guard_silently_removed project_scoped_elements_all_dropped PSS_index_wipe", ocd: 2026-08-29, lmd: 2026-08-29] DO NOT test a guard by re-expressing its condition in the test, BECAUSE you then assert a fact about the stdlib that cannot fail while the real guard drifts or is deleted — here `assert!("".trim().is_empty())` left all 307 green with the guard neutered, re-arming a 689-element wipe. DO compose guard+predicate into the one function the caller invokes, assert on THAT, and prove the tripwire by mutation (neuter it, watch the test fail, restore).
