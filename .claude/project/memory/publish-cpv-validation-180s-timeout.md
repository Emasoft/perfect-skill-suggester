---
name: publish-cpv-validation-180s-timeout
description: "publish.py release BLOCKED at plugin validation with \"exit code 124\" / \"Timed out after 180s\" or 900s / pre-warming the uvx cache did not help — a CPV gate timeout is a SYMPTOM with several possible causes; read the [cpv-phase] log for which phase stalled, and if the gate follows a local cargo build --release suspect the multi-GB rust/target submodule build artifacts inflating the scanned work set"
ocd: 2026-07-16
lmd: 2026-08-29
metadata:
  node_type: memory
  type: project
  tier: component
publish-globally: false
---

^BKLYIYV7 [desc:"publish.py's CPV remote-validation step has only a 180s internal timeout; a cold uvx cache building the CPV env from GitHub can exceed it, returning exit 124 before any version bump — the tree is left clean, safe to retry.", keywords:"cpv_validation_180s_timeout exit_code_124 cold_uvx_cache clean_tree_safe_retry", type:project, ocd:2026-07-16, lmd:2026-07-16]
`scripts/publish.py` gives the CPV remote-validation step
(`uvx --from git+…/claude-plugins-validation --with pyyaml cpv-remote-validate
plugin .`) only a **180s internal timeout** (`run_validation()`,
publish.py:164; the shared `run()` helper returns `returncode=124` +
`"Timed out after {timeout}s"` on `TimeoutExpired`). On a **cold uvx cache**,
building the CPV tool env from GitHub + running validation exceeds 180s, so the
call returns exit **124** and publish.py fatals at the validation gate.

This happens BEFORE any version bump (order: preflight → lint → tests →
validation → bump), so the working tree is left **clean** — safe to retry, no
partial release state.

^QSTDB1CP [desc:"A CPV gate timeout is a SYMPTOM with more than one cause; a cold uvx cache is only one, and pre-warming is a hypothesis to test, never the diagnosis. Read the phase log for WHICH phase stalled.", keywords:"cpv_timeout_has_more_than_one_cause which_phase_stalled prewarm_is_a_hypothesis_not_a_diagnosis cold_uvx_cache_only_sometimes", type:project, ocd:2026-07-16, lmd:2026-08-15]
**Why:** a timeout says only that something did not finish. On 2026-06-20 the
cause genuinely was a cold uvx cache. On 2026-08-02 it was not: the cache was
warm, pre-warming ran 80+ minutes producing nothing, and the real cause was a
deadlock in CPV's `skillaudit_native` over a 62,422-file work set. Treating the
symptom as if it had one known cause turns a real blocker into "just a network
hiccup" — see [^1].

**How to apply:** read the validator's own `[cpv-phase]` log FIRST and name the
phase that stalled; every healthy phase completes in ~0.0s, so the stall is
unmistakable. Then match the remedy to that phase:
- an oversized work set (submodule-build plugins: `rust/target` is invisible to
  CPV's `git ls-files` skip-set) → `uv run python scripts/publish.py --clean --rust-only`
- a genuinely cold cache → one standalone run to warm it:
```bash
uvx --from git+https://github.com/Emasoft/claude-plugins-validation --with pyyaml cpv-remote-validate plugin .
uv run python scripts/publish.py --bump patch
```
Either way the tree is left CLEAN and no version is burned — the gate fails
BEFORE the bump, so a retry is always safe.

**Do NOT** conclude from a timeout that validation would otherwise pass. When it
finally ran to completion on 2026-08-02 it reported **12 MAJOR**. [^1] [^2]

^S4JRUSRZ [desc:"Upstream tracking: CPV #114 (closed, v2.127.0) added CI UV-cache for canonical templates only; CPV #137 (open) would publish CPV to PyPI as a wheel so uvx resolves prebuilt instead of building from --from git+... source, which PSS's publish.py currently forces.", keywords:"cpv_114_closed_ci_cache cpv_137_open_pypi_wheel from_git_forces_slow_build upstream_fix_tracking", type:project, ocd:2026-07-16, lmd:2026-07-16]
**Upstream:** the permanent fix is tracked on CPV — #114 (closed, v2.127.0)
added a CI UV-cache + 25-min ceiling for the canonical *templates* (doesn't
help a local `publish.py` run), and **CPV #137** (open) requests the deep fix:
publish CPV to PyPI as a wheel so `uvx cpv-remote-validate` resolves a prebuilt
wheel instead of `--from git+…` building from source. When #137 ships, PSS's
publish.py can drop the `--from git+…` form + the pre-warm step. Note: PSS's
publish.py uses `--from git+https://github.com/Emasoft/claude-plugins-validation`,
which FORCES the slow git-build path regardless of any PyPI wheel.
Related: [[feedback_publish_mandatory_gates]], [[publish-submodule-build-skip-stale-binaries]] (also a publish.py-gate incident, cites this page's cache pre-warm fix).

## Governed by
- [[pss-knowledge-hub]] — entry point to PSS's PROJECT-scope memory corpus.

## Notes and lessons learned

(No corrections yet — the core fact above is verified, not superseded. The
2026-06-20 edit was purely additive: it appended the upstream-tracking context
[CPV #114 closed / #137 open], it did not rewrite a wrong fact.)
[^1]: [id:ATOM-JMOK-TYGS, status:valid, supersedes:QSTDB1CP, desc:"A CPV gate timeout is a symptom, not a diagnosis — pre-warming fixed nothing and the real failure was 12 MAJOR.", keywords:"cpv_validation_timeout_is_not_always_cold_cache prewarm_did_not_help_uvx_was_already_warm exit_124_at_the_validation_gate timeout_is_a_symptom_not_a_diagnosis which_phase_stalled skillaudit_native_hangs_on_submodule_build_output", ocd:2026-08-15, lmd:2026-08-15] DO NOT treat a CPV validation timeout at the publish gate as "a cold-start artifact, not a real failure" and reach for the pre-warm-then-retry recipe, BECAUSE a timeout says only that something did not finish: on 2026-08-02 the uvx cache was already warm, pre-warming ran 80+ minutes producing nothing, and the real cause was a deadlock in CPV's skillaudit_native over a 62,422-file work set — when the run finally completed it reported 12 MAJOR. DO read the validator's own [cpv-phase] log FIRST and name the phase that stalled (every healthy phase completes in ~0.0s), then match the remedy to that phase. SUPERSEDED BODY: **Why:** it's a cold-start / network timeout, NOT a real validation failure. Lint + tests already passed before it; a standalone CPV run exits 0 (clean pass — CRITICAL/MAJOR/MINOR all 0; the NIT/WARNING/CA findings are non-blocking demoted items). **How to apply:** pre-warm the uvx CPV cache with one standalone run first (no publish.py 180s clamp on it), confirm exit 0, then re-run publish.py — the warm cache finishes well under 180s: ```bash uvx --from git+https://github.com/Emasoft/claude-plugins-validation --with pyyaml cpv-remote-validate plugin . # exit 0 = pass + warms cache uv run python scripts/publish.py --bump patch ``` Verified 2026-06-20 shipping v3.7.4 (the `anthropic` dep-removal release).
[^2]: [id: ATOM-E56U-KRW2, status: valid, desc: "the cause when the timeout follows a local release build", keywords: "CPV_validation_timed_out_after_900s plugin_validation_failed_with_unexpected_exit_code_124 gate_blocked_after_I_built_the_binary pre-warming_the_uvx_cache_did_not_help why_is_cpv-remote-validate_so_slow cargo_build_--release_then_publish.py_--gate_fails rust/target_is_11GB submodule_build_artifacts_inflate_the_scanned_work_set publish.py_--clean_--rust-only PSS_CPV_TIMEOUT_raising_the_timeout_is_the_wrong_fix which_cpv-phase_stalled_file-scan BLOCKED_Fix_issues_before_pushing", ocd: 2026-08-29, lmd: 2026-08-29] DO NOT reach for the cold-uvx-cache explanation (or a PSS_CPV_TIMEOUT bump) when the CPV gate returns exit 124 after a LOCAL RELEASE BUILD, BECAUSE `cargo build --release` leaves ~11 GB in `rust/target` INSIDE the rust/ submodule, and CPV`s file-scan phase walks it — measured 2026-08-29: two consecutive 900s timeouts, then `publish.py --clean --rust-only` freed 11.2 GB and the same tree validated. DO read publish.py`s own error text first: it already names rust/target as the usual cause and prints the exact clean command, ahead of the pre-warm advice.
