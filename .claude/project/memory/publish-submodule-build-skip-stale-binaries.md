---
name: publish-submodule-build-skip-stale-binaries
description: "release shipped but the new CLI verb is missing from the binary / publish.py said 'No Rust source changes, skipping build' even though I changed main.rs / stale bin/ binaries / build skipped after editing rust source / git log -S returned no commits and I concluded no history exists / grep across the repo found nothing inside rust/ / CPV validation timed out at 900s with exit code 124 and pre-warming did not help / a command run at the repo root reported a confident nothing about a submodule it never entered"
ocd: 2026-06-25
lmd: 2026-08-16
metadata:
  node_type: memory
  type: project
  tier: component
publish-globally: false
---

^6UX3F1IC [desc:"publish.py's rebuild detection diffed the PARENT repo, blind to the rust/ submodule gitlink, so v3.8.0 shipped with stale binaries lacking new Rust CLI verbs.", keywords:"submodule_gitlink_diff_blind stale_binaries_shipped rust_source_changed_false_negative parent_repo_diff_empty", type:project, ocd:2026-06-25, lmd:2026-07-16]
**publish.py's binary-rebuild detection must diff INSIDE the `rust/` submodule, not the parent repo.** PSS's Rust sources live in the `rust/` git **submodule**; the parent repo tracks `rust/` only as a **gitlink** (one commit SHA). So `git diff <tag> HEAD -- rust/skill-suggester/src` run in the **parent** repo NEVER sees file-level `.rs` changes — it only ever sees the gitlink flip — and always returns empty.

`rust_source_changed()` / `nlp_source_changed()` used that parent-repo diff, so after editing `main.rs`/`temporal.rs` they reported **"No Rust source changes since last tag, skipping build"** and `build_binaries` was skipped → `bin/` was never recompiled → **v3.8.0 shipped with STALE binaries** lacking the new lifeline verbs.

**Why:** in a submodule architecture every parent-repo `git diff -- <submodule>/...` is blind to the submodule's internal file changes. [^2]

^U9PLH7LT [desc:"Fix: diff git rev-parse <tag>:rust vs git -C rust rev-parse HEAD inside the submodule (shipped v3.8.1); force a landed-but-uncompiled fix with --force-build; always verify the actual shipped binary, never the wrapper's exit code.", keywords:"submodule_diff_fix force_build_flag verify_shipped_binary wrapper_exit_code_lie", type:project, ocd:2026-06-25, lmd:2026-07-16]
**How to apply:**
- Detection must diff inside the submodule: `git rev-parse <last_tag>:rust` (the gitlink SHA the parent recorded at the tag) → `git -C rust rev-parse HEAD` → `git -C rust diff --name-only <old> <new> -- skill-suggester/src`. Fixed in `scripts/publish.py::_submodule_src_changed` (shipped v3.8.1).
- If the `.rs` change already landed in a prior tag's submodule ref but was never compiled (the v3.8.0 case), the fixed detector correctly sees "no change since that tag" — you must `publish.py --bump patch --force-build` to force the rebuild.
- ALWAYS verify the actual artifact after a release: run the **shipped** `./bin/pss-darwin-arm64 <new-verb>` — do NOT trust the wrapper exit code or the background "completed" notification (a `cmd > log; echo EXIT=$?` wrapper's exit is the `echo`'s, not the command's).

Related: [[publish-cpv-validation-180s-timeout]] (pre-warm the CPV cache before a release), [[feedback_publish_mandatory_gates]], [[verify-shipped-status-against-the-tag]] (that page verifies the shipped COMMIT SET against the tag; this one verifies the shipped BINARY behaviorally). The cargo workspace lock that #51 syncs is `rust/Cargo.lock` (workspace root), not the orphan `rust/skill-suggester/Cargo.lock`. This same submodule-blindness was first logged as a secondary gotcha during the v3.7.3 CPV FP-storm — see [[cpv-skillaudit-fp-blocks-373]].

## Governed by
- [[pss-knowledge-hub]] — entry point to PSS's PROJECT-scope memory corpus.


^ATOM-1WT3-ZMJ2 [desc:"publish.py must stage every TRACKED submodule change plus scripts/ and .github/ — build_binaries compiles from the WORKING TREE, not the gitlink.", keywords: binary_cannot_be_rebuilt_from_shipped_source submodule_main.rs_not_staged publish.py_stages_only_Cargo.toml release_left_my_scripts_fix_behind push-only_pushed_a_tag_with_no_github_release, ocd: 2026-08-01, lmd: 2026-08-01]

`build_binaries()` compiles from the rust/ submodule's WORKING TREE, so an
uncommitted `main.rs` is baked into the shipped binary while the submodule commit —
and therefore the gitlink the parent records — still points at the OLD source. The
release then ships a binary that cannot be rebuilt from the source it shipped with.
This nearly shipped v3.12.2 (2026-08-01): a prompt-injection sanitizer was compiled
in while its source was unstaged; only `git status` caught it.

Fixed in `c7d5b3d`. `git_commit()` now enumerates every TRACKED submodule change BY
NAME from `git status --porcelain` (rename destinations included) and stages it;
untracked files are warned about loudly and deliberately NOT staged, because a
release must never silently absorb scratch. The parent also stages
`git add -u -- scripts .github` — tracked-only, never `git add -A` — so a fix to the
publisher or the CI workflows can no longer be left behind by the release that
depends on it. `--push-only` now also ensures the GitHub release (idempotent via a
`gh release view` probe), closing the pushed-tag-with-no-release half-state.


^ATOM-J5U3-OTPO [desc:"PSS's publish.py divergence from CPV's canonical is BY DESIGN — the submodule-build profile. Determine the profile before diffing.", keywords: publish.py_is_1400_lines_shorter_than_canonical canonical_pipeline_drift_is_huge should_I_port_the_canonical_publish.py validate_canonical_pipeline_drift_passes_anyway, ocd: 2026-08-01, lmd: 2026-08-01]

CPV declares a **`submodule-build` profile** (`cpv-canonical-pipeline/SKILL.md:21`):
build sources in a git submodule, prebuilt binaries committed to `bin/`, and a
submodule-aware `publish.py`. PSS is that profile, so its publish.py is EXPECTED to
diverge from CPV's own — measured 1805 vs 3236 lines with 40+ "missing" functions on
2026-08-01, which reads as catastrophic drift and invites a destructive wholesale
port. It is not drift, and `validate_canonical_pipeline_drift` passing is CORRECT.

Determine the profile BEFORE diffing: a profile mismatch makes every subsequent diff
meaningless. Also note `<cpv>/scripts/publish.py` is CPV's OWN pipeline, not the
plugin template — the template is `gen_publish_py()` in `generate_plugin_repo.py`,
which is where the documented G2e/G2f build gates actually live (filed as
claude-plugins-validation#187).

## Notes and lessons learned

[^1]: After committing a fix INSIDE the `rust/` submodule, you MUST also commit the
  PARENT's submodule-ref bump (`git add rust && git commit`) BEFORE running
  `publish.py --bump`. publish.py's pre-flight refuses a dirty tree ("Git working
  tree is dirty. Commit or stash changes before releasing."), and a moved submodule
  HEAD shows in the parent as ` M rust`. Symptom: the release exits 1 immediately
  with no bump (tree stays at the prior version) and `git status` shows only
  ` M rust`. This bit v3.8.3 (committed the cli_version fix in the submodule, forgot
  the parent ref bump). The v3.8.0/v3.8.1 flow avoided it only because other parent
  files (docs/scripts) were committed together, carrying the ref along.
[^2]: [id: ATOM-7TBW-T7CP, status: valid, desc: "Any git/scan tool run at the PARENT repo root is blind to submodule contents and reports a confident NOTHING — four separate instances, each read as a real answer.", keywords: "git_log_S_returns_nothing_for_submodule_path cpv_validation_times_out_900s_exit_124 grep_across_repo_finds_nothing_in_rust no_history_exists_for_this_function tool_ran_at_repo_root_and_saw_an_empty_submodule false_clean_from_a_parent_repo_command rust_target_not_in_skip_set 62000_files_work_set", ocd: 2026-08-16, lmd: 2026-08-16] DO NOT accept an empty or clean result from any git/scan command run at the repo root when the subject lives in a submodule (this repo: `rust/`), BECAUSE the parent repo stores only a gitlink, so the tool enters no submodule and answers confidently about a region it never looked at — a FALSE CLEAN, indistinguishable from a real negative. Four instances, one root cause: publish.py's rebuild detection diffed the parent and shipped stale binaries (this atom); shipped-status checks needed the tag's recorded gitlink instead; CPV's `git ls-files` skip-set never saw `rust/target`, so its work set was 62,422 files and validation hit exit 124 at the 900s clamp (the prescribed "pre-warm the uvx cache" recipe is NOT the cause); and `git log -S '<symbol>' -- <path>` from the root returned zero commits for submodule source, which read as "no design history exists". DO re-run the command INSIDE the submodule (`git -C rust log -S …`) or against the gitlink (`git rev-parse <ref>:rust`), and prove the instrument first — run it against something you KNOW is there and confirm it is found — before recording any zero. For the CPV timeout specifically, `publish.py --clean --rust-only` collapses `rust/` from 25,121 files to 93 and validation then passes in seconds.
