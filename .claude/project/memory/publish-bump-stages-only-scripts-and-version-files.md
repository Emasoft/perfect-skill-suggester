---
name: publish-bump-stages-only-scripts-and-version-files
description: "Release shipped without its docs or tests / publish.py says Git working tree is dirty, commit or stash changes before releasing / --bump refuses to run on staged changes: the release commit carries only version files, bin/, the submodule gitlink and TRACKED changes under scripts/ and .github/ — so commit your own work FIRST (git add BY NAME, never -A) and let --bump add a version-only commit on top"
ocd: 2026-08-22
lmd: 2026-08-22
metadata:
  node_type: memory
  type: project
  tier: component
publish-globally: false
---

# publish-bump-stages-only-scripts-and-version-files


^ATOM-ENU6-YI0D [desc: "publish.py --bump never stages docs/ or tests/ — stage them by name or the release ships the fix without its guard", keywords: release_missing_docs tests_not_in_release_commit untracked_test_not_staged publish_bump_left_file_behind doc_change_not_shipped git_add_by_name_before_bump, ocd: 2026-08-22, lmd: 2026-08-22]

`scripts/publish.py::git_commit` stages a fixed set: `VERSION`, `plugin.json`,
`pyproject.toml`, `README.md`, `CHANGELOG.md`, `uv.lock`, `bin/`, the `rust`
submodule gitlink, plus `git add -u -- scripts .github` (TRACKED modifications
only, deliberately never `git add -A`).

Everything else is left behind, silently:

- `docs/**` — a compatibility-doc or design-doc change is NOT in the release commit.
- `tests/**` — a new regression test is NOT in the release commit.
- any UNTRACKED file anywhere (`publish.py:1231` and `:1297` say so explicitly, but
  the warning it prints covers only `scripts/` and `.github/`, so an untracked file
  under `tests/` or `docs/` gets no warning at all).

The damage is worse than a missing file: the fix ships WITHOUT the test that guards
it, and any doc sentence citing that test path becomes false at HEAD on the very
commit that introduced it.

**So COMMIT your own work first — `--bump` cannot carry it** (see the lesson below:
`preflight_checks` fatals on ANY dirty tree, staged paths included):

```bash
git add docs/<changed>.md tests/unit/<new_test>.py   # BY NAME, never -A
git commit -m "fix: <what changed>"
git status --porcelain                               # MUST be empty
uv run python scripts/publish.py --bump <level>      # adds a version-only commit
```

The release commit is not where your change lands; your own commit is.

Measured 2026-08-22 on the CC 2.1.222→2.1.240 alignment: three script fixes would
have shipped while `docs/CC-COMPATIBILITY.md` and both new BOM regression tests
stayed in the working tree. [^1]

## Notes and lessons learned

[^1]: [id: ATOM-CA71-I3LU, status: valid, supersedes: ATOM-ENU6-YI0D, desc: "the atom's staging recipe cannot work: --bump fatals on ANY dirty tree before it ever reaches git_commit", keywords: "working_tree_is_dirty commit_or_stash_changes_before_releasing bump_refuses_to_run publish_preflight_fatal staged_changes_block_release commit_before_bump", ocd: 2026-08-22, lmd: 2026-08-22] DO NOT stage docs/ or tests/ and then run `publish.py --bump` expecting the release commit to carry them, BECAUSE `--bump` runs `preflight_checks()` as its Step 1 (`scripts/publish.py::preflight_checks`) which calls `fatal("Git working tree is dirty. Commit or stash changes before releasing.")` on ANY non-empty `git status --porcelain` — staged paths included, so the recipe fatals before `git_commit` is ever reached. `git_commit`'s `git add -u -- scripts .github` exists to catch the files the PIPELINE ITSELF dirties (version rewrite, `bin/` rebuild, vendored CPV helpers), not your feature work. DO commit the feature work FIRST — stage by name (`git add docs/... tests/...`, never `-A`), commit, verify `git status --porcelain` is empty — and only then run `publish.py --bump`, which adds a version-only release commit on top. The release commit is NOT where your change lands; your own commit is. SUPERSEDED BODY: `scripts/publish.py::git_commit` stages a fixed set: `VERSION`, `plugin.json`, `pyproject.toml`, `README.md`, `CHANGELOG.md`, `uv.lock`, `bin/`, the `rust` submodule gitlink, plus `git add -u -- scripts .github` (TRACKED modifications only, deliberately never `git add -A`). Everything else is left behind, silently: - `docs/**` — a compatibility-doc or design-doc change is NOT in the release commit. - `tests/**` — a new regression test is NOT in the release commit. - any UNTRACKED file anywhere (`publish.py:1231` and `:1297` say so explicitly, but the warning it prints covers only `scripts/` and `.github/`, so an untracked file under `tests/` or `docs/` gets no warning at all). The damage is worse than a missing file: the fix ships WITHOUT the test that guards it, and any doc sentence citing that test path becomes false at HEAD on the very commit that introduced it. **Before every `--bump`, `git add` the non-pipeline paths BY NAME** (never `-A`): ```bash git add docs/<changed>.md tests/unit/<new_test>.py git status --short # expect M/A on exactly what belongs in the release uv run python scripts/publish.py --bump <level> ``` `git commit` (which `--bump` runs without a pathspec) commits the whole index, so pre-staged paths ride along correctly. Measured 2026-08-22 on the CC 2.1.222→2.1.240 alignment: three script fixes would have shipped while `docs/CC-COMPATIBILITY.md` and both new BOM regression tests stayed in the working tree.
