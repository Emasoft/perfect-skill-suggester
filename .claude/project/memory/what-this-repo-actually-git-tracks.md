---
name: what-this-repo-actually-git-tracks
description: "I edited CLAUDE.md but the change never reaches another clone / project memory is the 'shared' scope but nothing is in git / my !.claude/... gitignore negation does nothing / CPV fails MINOR '.gitignore missing coverage for Claude Code cache directory (.claude/)' / why did my doc edit not ship"
ocd: 2026-07-29
lmd: 2026-07-29
metadata:
  node_type: memory
  type: project
  tier: component
---

In the PSS repo, two paths that look tracked are NOT, and one of them cannot be
made tracked without breaking the release gate.

**`CLAUDE.md` is gitignored and untracked** (`.gitignore`, alongside `.claude/`).
The harness presents it as "project instructions checked into the codebase", but
`git ls-files CLAUDE.md` returns nothing. Anything documented ONLY there is
local to one machine and never reaches another clone or contributor. Durable
architecture/design docs belong in `docs/` (e.g. the tracked
`docs/PSS-ARCHITECTURE.md`); CLAUDE.md is fine for machine-local operating notes.

**`.claude/project/memory/` is not tracked either.** Until 2026-08-07 this was
recorded here as a genuine, unresolvable tool conflict. **It no longer is** —
upstream CPV fixed its half. [^2] [^3]

- Git does not descend into an excluded DIRECTORY, so with a bare `.claude/`
  every later `!.claude/project/memory/**` negation is INERT. Verified
  empirically 2026-07-29 in a throwaway repo: `.claude/` + negations tracks
  nothing; `.claude/*` + `!.claude/project/` tracks the memory files. This half
  is unchanged and still true.
- CPV's `.claude/` check is now **content-aware, not spelling-exact** (its issue
  #120). `validate_plugin` carries `_claude_dir_has_tracked_content()`, and
  `tests/test_issue_120_claude_dir_gitignore.py` asserts on a fixture whose
  `.gitignore` says `.claude/**` + negations that
  `test_tracked_claude_content_clears_finding` yields `findings == []`, while an
  untracked `.claude/` cache still flags. Independently, the required-entries
  audit in `standardize_plugin.py` uses `_gitignore_line_covers_entry`, which
  accepts any glob that `fnmatch`-matches the entry — running CPV's own
  predicate, `.claude/*` and `.claude/**` both cover `.claude/`.

So both conditions can hold at once: spell it `.claude/**` + negations **and**
actually track the memory files. PSS runs the gate as
`uvx --from git+https://…` (always CPV main), so the fix is already in the
version that gates this repo.

**Still not done, and deliberately so.** Two things gate the switch, neither of
them a tool conflict: (1) tracking PROJECT memory means **pushing** it, so the
corpus needs a machine-specific-content audit first (absolute `$HOME` paths,
hostnames, account state) per the memory scope-routing write gate; (2) the
`.gitignore` edit and the first commit of the memory files must land together —
the finding clears on *tracked content*, so changing the spelling without
committing the files would flag. Both are the user's call.

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
