---
name: what-this-repo-actually-git-tracks
description: "I edited CLAUDE.md but the change never reaches another clone / project memory is the 'shared' scope but nothing is in git / my !.claude/... gitignore negation does nothing / CPV fails MINOR '.gitignore missing coverage for Claude Code cache directory (.claude/)' / why did my doc edit not ship"
ocd: 2026-07-29
lmd: 2026-09-28
metadata:
  node_type: memory
  type: project
  tier: component
publish-globally: false
---

In the PSS repo, two paths that look tracked are NOT, and one of them cannot be
made tracked without breaking the release gate.

^W7QK2M9D [desc:"CLAUDE.md in the PSS repo is gitignored and untracked; anything documented only there is local to one machine and never reaches another clone, so durable docs belong in tracked docs/.", keywords:"claude_md_gitignored untracked_after_edit doc_edit_did_not_ship claude_md_not_checked_in git_ls_files_empty doc_edits_never_ship local_only_instructions", type:project, ocd:2026-07-29, lmd:2026-09-28]
**`CLAUDE.md` is gitignored and untracked** (`.gitignore`, alongside `.claude/`).
The harness presents it as "project instructions checked into the codebase", but
`git ls-files CLAUDE.md` returns nothing. Anything documented ONLY there is
local to one machine and never reaches another clone or contributor. Durable
architecture/design docs belong in `docs/` (e.g. the tracked
`docs/PSS-ARCHITECTURE.md`); CLAUDE.md is fine for machine-local operating notes.

^T3XN8P4R [desc:"The PROJECT memory dir was long assumed impossible to track because git ignores excluded directories, making later negations inert; that half of the conflict still holds and is unchanged.", keywords:"gitignore_negation_does_nothing bare_directory_ignore negation_after_excluded_dir_inert project_memory_untracked git_descend_excluded_directory", type:project, ocd:2026-07-29, lmd:2026-09-28]
**`.claude/project/memory/` is not tracked either.** Until 2026-08-07 this was
recorded here as a genuine, unresolvable tool conflict. **It no longer is** —
upstream CPV fixed its half. [^2] [^3]

^H5YB2C7K [desc:"Git does not descend into an excluded directory, so a bare .claude/ ignore makes every later negation inert; verified empirically 2026-07-29 — .claude/* plus negations does track the memory files.", keywords:"git_ignores_excluded_directory_negation_inert claude_glob_negation_tracks_memory throwaway_repo_test directory_negation_never_works", type:project, ocd:2026-07-29, lmd:2026-09-28]
- Git does not descend into an excluded DIRECTORY, so with a bare `.claude/`
  every later `!.claude/project/memory/**` negation is INERT. Verified
  empirically 2026-07-29 in a throwaway repo: `.claude/` + negations tracks
  nothing; `.claude/*` + `!.claude/project/` tracks the memory files. This half
  is unchanged and still true.
^L9ZD4V6M [desc:"CPV's .claude/ gitignore check became content-aware (issue #120): a .claude/** spelling plus actual tracked memory files clears the MINOR finding, while an untracked .claude/ cache still flags.", keywords:"cpv_check_content_aware cpv_issue_120 claude_dir_gitignore_spelling tracked_content_clears_finding claude_glob_spelling_minor_gate standardize_plugin_required_entries", type:project, ocd:2026-07-29, lmd:2026-09-28]
- CPV's `.claude/` check is now **content-aware, not spelling-exact** (its issue
  #120). `validate_plugin` carries `_claude_dir_has_tracked_content()`, and
  `tests/test_issue_120_claude_dir_gitignore.py` asserts on a fixture whose
  `.gitignore` says `.claude/**` + negations that
  `test_tracked_claude_content_clears_finding` yields `findings == []`, while an
  untracked `.claude/` cache still flags. Independently, the required-entries
  audit in `standardize_plugin.py` uses `_gitignore_line_covers_entry`, which
  accepts any glob that `fnmatch`-matches the entry — running CPV's own
  predicate, `.claude/*` and `.claude/**` both cover `.claude/`.

^Q2F7G8NJ [desc:"Both gate conditions can hold at once — spell .gitignore .claude/** plus negations AND actually commit the memory files; PSS gates on CPV main via uvx, so the fix is already live in the gating version.", keywords:"gitignore_spelling_and_commit_together cpv_gate_uvx_main fix_already_in_gate claude_glob_plus_negations spell_and_track_both_conditions", type:project, ocd:2026-07-29, lmd:2026-09-28]
So both conditions can hold at once: spell it `.claude/**` + negations **and**
actually track the memory files. PSS runs the gate as
`uvx --from git+https://…` (always CPV main), so the fix is already in the
version that gates this repo.

^R8M3K5WP [desc:"Tracking PROJECT memory is still deliberately undone: it needs a machine-specific-content audit first (HOME paths, hostnames) and the gitignore edit must land together with the first commit — both are the user's call.", keywords:"memory_tracking_deliberately_undone machine_content_audit_first gitignore_edit_and_first_commit_together user_decision_pending pushing_memory_needs_privacy_audit", type:project, ocd:2026-07-29, lmd:2026-09-28]
**Still not done, and deliberately so.** Two things gate the switch, neither of
them a tool conflict: (1) tracking PROJECT memory means **pushing** it, so the
corpus needs a machine-specific-content audit first (absolute `$HOME` paths,
hostnames, account state) per the memory scope-routing write gate; (2) the
`.gitignore` edit and the first commit of the memory files must land together —
the finding clears on *tracked content*, so changing the spelling without
committing the files would flag. Both are the user's call.

^P4N8T2XV [desc:"The remaining verification gap: nobody has run a real CPV validation on this repo with the changed .gitignore spelling; all evidence is CPV's source and tests, not an end-to-end run here.", keywords:"cpv_validation_never_run_here evidence_is_source_not_e2e verification_gap_remains no_real_cpv_run_changed_spelling", type:project, ocd:2026-07-29, lmd:2026-09-28]
The verification gap that remains: nobody has yet run a real CPV validation on
this repo with the changed spelling. The evidence above is CPV's source and
tests, not an end-to-end run here.

## Governed by

- [[pss-knowledge-hub]]

## Notes and lessons learned

[^1]: [id:ATOM-7QK3-M2XD, status:valid, keywords:"gitignore_negation_does_nothing untracked_after_edit doc_edit_did_not_ship claude_md_ignored", ocd:2026-07-29, lmd:2026-07-29]
  DO NOT assume a file is tracked because it exists, is named like a project
  file, or is described as "checked in", BECAUSE both `CLAUDE.md` and
  `.claude/project/memory/` exist on disk here yet are gitignored, so edits to
  them silently never ship. DO run `git ls-files <path>` (or `git status
  --porcelain -uall <dir>`) before relying on an edit reaching anyone else.

[^2]: [id:ATOM-4RVB-J8HN, status:superseded, superseded-by:ATOM-8HXQ-P4ND, keywords:"reinclude_excluded_directory bare_directory_ignore cpv_minor_gitignore_coverage", ocd:2026-07-29, lmd:2026-08-07]
  DO NOT "fix" a dead `!.claude/...` negation by changing the parent to
  `.claude/*`, BECAUSE that spelling makes CPV's gate fail MINOR and blocks the
  release — the two requirements are mutually exclusive, not a bug to patch. DO
  test candidate gitignore spellings in a throwaway `git init` repo first, then
  leave the CPV-compliant form in place and escalate the conflict.
  (SUPERSEDED 2026-08-07 — kept verbatim as the dated record of what was true on
  2026-07-29; CPV's check became content-aware in its issue #120.)

[^3]: [id:ATOM-8HXQ-P4ND, status:valid, supersedes:ATOM-4RVB-J8HN, keywords:"guardrail_went_stale upstream_fixed_it two_tools_conflict recheck_the_blocker cpv_issue_120 claude_dir_gitignore_spelling tracked_content_clears_finding", ocd:2026-08-07, lmd:2026-08-07]
DO NOT let a "these two tools are mutually exclusive" guardrail stand unrechecked, BECAUSE it was written against ONE version of an upstream that can fix its half — here CPV made the `.claude/` check content-aware (its issue #120: `validate_plugin._claude_dir_has_tracked_content()`, asserted by `tests/test_issue_120_claude_dir_gitignore.py::test_tracked_claude_content_clears_finding` on a `.claude/**`+negations fixture), so the guardrail flipped from protecting the release to blocking the right change while still reading as settled fact. DO re-verify a cross-tool blocker against upstream's CURRENT source before treating it as a constraint, and date the claim so its age is visible. SUPERSEDED BODY: DO NOT "fix" a dead `!.claude/...` negation by changing the parent to `.claude/*`, BECAUSE that spelling makes CPV's gate fail MINOR and blocks the release — the two requirements are mutually exclusive, not a bug to patch. DO test candidate gitignore spellings in a throwaway `git init` repo first, then leave the CPV-compliant form in place and escalate the conflict.
