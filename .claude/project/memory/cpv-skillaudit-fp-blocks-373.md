---
name: cpv-skillaudit-fp-blocks-373
description: "publish.py / CPV gate suddenly fails with CRITICAL security findings (prototype pollution, prompt injection, shell exec) in code that passed before — why is the release blocked, are they real"
ocd: 2026-06-16
lmd: 2026-07-23
metadata:
  node_type: memory
  type: project
  tier: component
---

^KXZW34RQ [desc:"CPV's auto-updated skillaudit scanner flagged 16 findings in PSS that were all false positives in correct, working code; the language/context-blind heuristics fire on token shapes regardless of exploitability.", keywords:"cpv_skillaudit_false_positives auto_update_broke_gate language_blind_heuristics token_shape_match", type:project, ocd:2026-06-16, lmd:2026-07-17]
On 2026-06-16 the CPV validator (publish.py pulls it via `uvx ... latest`)
auto-updated to add a `skillaudit` security scanner. It immediately flagged
PSS with 2 CRITICAL + 9 MAJOR + 5 MINOR that **all turned out to be false
positives** in correct, working code. v3.7.2 had passed the same gate clean
hours earlier — the only diff was a docs edit with none of these findings.
Tell-tale that CPV (not PSS) changed: a new `plugin.json cpv.max_chars no
longer supported (TRDD-021250b5)` advisory appeared.

**Why:** the new skillaudit heuristics are language/context-blind — they fire
on token shapes regardless of whether the pattern is exploitable.

^LXY08ZMQ [desc:"When the CPV gate newly fails on skillaudit findings, don't distort working code: devitalize the genuinely-improvable ones, treat the rest as FPs (with concrete examples), and per the CPV author file an upstream issue and wait.", keywords:"how_to_apply_skillaudit_fp devitalize_genuine_findings file_cpv_issue_and_wait fp_examples_list", type:project, ocd:2026-06-16, lmd:2026-07-17]
**How to apply:** when the CPV/publish gate newly fails on `skillaudit:*`
security findings, do NOT distort working code to dodge them. (1) Fix the
genuinely-improvable ones by *devitalizing* (e.g. `curl|sh`→download-review-run,
`os.environ["X"]=`→`os.environ.update`, inline `python -c` snippet→described
procedure) — committed in PSS `d9336b9`. (2) The rest are FPs: Rust `Vec::extend`
flagged as JS-only "prototype pollution"; a `debug!` log line as "indirect prompt
injection"; PSS's own context-merge as "cross-tool access"; an env-var NAME in an
`eprintln!` help string as "reserved-env poison"; a Rust `regex` crate pattern as
"ReDoS" (the crate is a linear-time DFA, ReDoS-impossible); `Command::new(bin).spawn()`
and list-form `subprocess.Popen` (no `shell=True`) as "shell exec"; documented
commands in `.md` files as "cmd injection". (3) Per the user (CPV's author), file a
CPV issue and WAIT — filed as Emasoft/claude-plugins-validation#124.

^NXNJ1JQ0 [desc:"RESOLVED in PSS v3.7.3: CPV's author fixed the FN-safe heuristics in CPV v2.126.27 over two rounds, needing exact failing multi-line/type-annotation shapes for the second round, plus a PSS-side debug-label reword to clear the protected prompt-injection class.", keywords:"resolution_v373_shipped cpv_v2_126_27_fix two_rounds_needed multiline_discriminator_gap debug_label_reworded", type:project, ocd:2026-06-16, lmd:2026-07-17]
**Resolution (RESOLVED — PSS v3.7.3 SHIPPED):** CPV's author (the user) fixed
the heuristics in CPV `v2.126.27` (FN-safe two-sided: FP clears AND each rule's
malicious sibling still fires). It took TWO rounds — the first cleared the
single-line cases (prototype-pollution, cross-tool); the rest needed a follow-up
with the EXACT failing shapes because the discriminators were **line-local** but
PSS wrote them as **multi-line** constructs (the `eprintln!`/`Regex::new(`/
`Command::new(` token sits on a different physical line than the flagged one) plus
one **type-annotation** match (`subprocess.Popen[bytes]` hints, not calls). Class 2
(prompt-inject, a PROTECTED intent-rule CPV won't auto-clear) was cleared on PSS's
side by rewording the `debug!` label `"…corrected prompt"`→`"…corrected input"`.

**Two non-obvious gotchas burned here (remember):**
^O7GLTZX2 [desc:"CPV's skillaudit scans on-disk files, not just tracked ones, so untracking a file does not clear a LOCAL gate finding — it must actually leave the working tree via safe-delete; a clean clone/CI is unaffected since untracking alone suffices there.", keywords:"cpv_scans_on_disk untracking_insufficient_locally safe_delete_clears_local_gate clean_clone_vs_local_tree", type:project, ocd:2026-06-16, lmd:2026-07-17]
1. **CPV scans ON-DISK files, not just tracked ones.** Untracking (`git rm --cached`)
   + gitignoring a file does NOT remove it from the skillaudit security scan — the
   file is still on disk. To clear a LOCAL publish-gate finding on a stale/transient
   file, it must leave the working tree (janitor `safe-delete` → `.trashcan/`, RULE-0-safe).
   A clean clone / CI wouldn't contain the untracked file, so untracking IS the right
   fix for the shipped/CI state — only the local dev tree needs the on-disk removal.
^OI5CQMO6 [desc:"publish.py's rust_source_changed() diffs *.rs only in the parent repo and is blind to a rust submodule's own .rs edits, so a submodule-only change reports no-rust-changes and skips the build unless --force-build or CI's recursive-submodule checkout rebuilds it.", keywords:"rust_source_changed_submodule_blind parent_repo_diff_misses_submodule force_build_needed ci_recursive_checkout_rebuilds", type:project, ocd:2026-06-16, lmd:2026-07-17]
2. **publish.py `rust_source_changed()` can't see INTO the rust submodule.** It diffs
   `*.rs` in the PARENT repo, which only sees the submodule gitlink change, so a
   submodule-only `.rs` edit reports "No Rust source changes since last tag, skipping
   build" and the shipped binaries lag the source. Cosmetic for a debug-label change
   (CI's `build-binaries.yml` checks out `submodules: recursive` and rebuilds); use
   `--force-build` if a FUNCTIONAL submodule `.rs` change must rebuild binaries at ship.
   **This blindness was FIXED in v3.8.1** (`4c10cf8`): `rust_source_changed()` now diffs
   INSIDE the submodule, so a submodule-only `.rs` edit is detected at ship; `--force-build`
   still forces a rebuild of an already-tagged-but-never-built change. [^3]

^P9I75M86 [desc:"Final shipped commit set for the FP-storm fix (docs, devitalizations, rust rephrase+untrack, release, tag) and the closed upstream issue #124.", keywords:"shipped_commit_set v373_tag issue_124_closed", type:project, ocd:2026-06-16, lmd:2026-07-17]
Shipped: docs `8fb5881`, devitalizations `d9336b9`, rust rephrase+rck-untrack `b666760`,
release `90f1774`, tag `v3.7.3`. #124 closed. See [[feedback_publish_mandatory_gates]].[^1][^2]

## Governed by
- [[pss-knowledge-hub]] — entry point to PSS's PROJECT-scope memory corpus.


^ATOM-L07Z-NF80 [desc:"CPV has two gates; publish.py runs only the structural one, so a security-scan INVALID does not block a release.", keywords: cpv_security_scan_says_INVALID six_critical_but_the_gate_is_green publish_gate_green_but_security_red does_a_red_security_scan_block_the_release cpv_two_subcommands_plugin_vs_security, type: project, ocd: 2026-08-07, lmd: 2026-08-07]

CPV ships TWO independent gates and `publish.py` runs only ONE. `cpv-remote-validate plugin .` is
the structural gate and is the ONLY CPV command `scripts/publish.py` invokes (verified 2026-08-07
by grep: two mentions, both the `plugin` form). `cpv-remote-validate security .` is a SEPARATE
subcommand publish.py never calls — so a red security scan does NOT block a release. Measured
2026-08-07, with both verdicts correct at the same time: structural exit 0,
`CRITICAL=0 MAJOR=0 MINOR=0 NIT=10 WARNING=21`, "All checks passed"; security exit 1,
`CRITICAL:6 MAJOR:8 MINOR:11`, "Verdict: INVALID". All 6 CRITICAL were verified false positives
EXCEPT `RC-164` chmod +x at `scripts/pss_build_all.py:163`, which is load-bearing (it marks built
binaries executable) and which CPV itself says to FLAG, never break. The same run also confirmed
first-hand that the CPV v5 12-MAJOR block is cleared by `"canon": "none"`, and that NO `.claude/`
gitignore finding is raised. Evidence: `reports/cpv-validation/20260807_19*.txt` and
`reports/security/20260807_193009+0200-*.md`. [^4]

## Notes and lessons learned
[^1]: [ocd:2026-06-16 lmd:2026-06-16] WHY untracking didn't clear the local gate:
  CPV's skillaudit scans the on-disk working tree, not `git ls-files`. The user
  (CPV author) said "untrack it" expecting resolution — correct for a clean clone /
  CI (no untracked files there) but NOT for the local dev tree where the file
  physically remains. Root cause: conflating "tracked" with "present on disk." Fix:
  remove from the working tree (safe-delete → `.trashcan/`), which also makes the
  local tree match a clean clone.
[^2]: [ocd:2026-06-16 lmd:2026-06-16] WHY the v3.7.3 binaries lagged the source:
  `publish.py::rust_source_changed()` runs `git diff <tag> -- '*.rs'` in the PARENT
  repo. The `.rs` files live in the `rust/` submodule, so the parent diff sees only
  the 160000 gitlink change, never the individual `.rs` files → it concludes "no
  Rust source changes" and skips the rebuild. Root cause: a parent-repo diff is
  blind to submodule file contents. Mitigation: `--force-build` for functional
  submodule `.rs` changes; CI (`submodules: recursive`) rebuilds regardless. **FIXED
  in v3.8.1** (`4c10cf8`): `rust_source_changed()` now diffs INSIDE the submodule, so
  a submodule-only `.rs` edit is detected at ship — see [[publish-submodule-build-skip-stale-binaries]].
[^3]: [id:ATOM-K3KX-IXJ7, status:valid, desc:"the submodule-blind build-skip 'future fix' shipped in v3.8.1", keywords:"submodule_build_skip_fixed_v3_8_1 pending_memory_todo_already_shipped verify_todo_against_current_publish_py", ocd:2026-07-23, lmd:2026-07-23] DO NOT carry this page's "worth a future publish.py fix" for submodule-blind build detection as still-open, BECAUSE it shipped in v3.8.1 (4c10cf8) — rust_source_changed() now diffs inside the submodule. DO verify a memory's pending-TODO against the current publish.py before acting; the fix's own page is [[publish-submodule-build-skip-stale-binaries]].
[^4]: [id:ATOM-U16R-91XS, status:valid, desc:"A CPV security-scan INVALID read as a release blocker, but the gate never runs that subcommand.", keywords:"security_scan_invalid_but_release_not_blocked which_subcommand_does_the_gate_actually_run two_verdicts_disagree_and_both_are_right verify_the_cited_file_line citation_points_at_text_that_is_absent", ocd:2026-08-07, lmd:2026-08-07] DO NOT read a CPV security-scan "INVALID" as a release blocker, BECAUSE `publish.py` invokes only `cpv-remote-validate plugin .` and the `security` subcommand is a separate command it never calls — so the two verdicts can disagree completely and both be correct (2026-08-07: structural 0/0/0 PASS alongside security 6 CRITICAL INVALID). DO check which CPV subcommand a gate actually runs before treating its verdict as blocking, and verify each CRITICAL against the cited file:line — 5 of 6 were false positives, and one citation named a `REDACTED_SECRET_*` marker that `grep -rn` proves is not in the source at all.
