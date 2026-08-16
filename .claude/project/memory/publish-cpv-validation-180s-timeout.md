---
name: publish-cpv-validation-180s-timeout
description: "publish.py release fails at plugin validation with \"exit code 124\" / \"Timed out after 180s\" — CPV remote validation timed out, not a real failure; how to fix"
ocd: 2026-07-16
lmd: 2026-07-23
metadata:
  node_type: memory
  type: project
  tier: component
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

^QSTDB1CP [desc:"The 180s timeout is a cold-start/network issue, not a real validation failure (lint+tests already passed, a standalone CPV run exits 0); fix by pre-warming the uvx CPV cache with one standalone cpv-remote-validate run before publish.py.", keywords:"not_a_real_failure cold_start_not_validation_failure prewarm_uvx_cache standalone_cpv_run_first", type:project, ocd:2026-07-16, lmd:2026-07-16]
**Why:** it's a cold-start / network timeout, NOT a real validation failure.
Lint + tests already passed before it; a standalone CPV run exits 0 (clean
pass — CRITICAL/MAJOR/MINOR all 0; the NIT/WARNING/CA findings are non-blocking
demoted items).

**How to apply:** pre-warm the uvx CPV cache with one standalone run first
(no publish.py 180s clamp on it), confirm exit 0, then re-run publish.py — the
warm cache finishes well under 180s:
```bash
uvx --from git+https://github.com/Emasoft/claude-plugins-validation --with pyyaml cpv-remote-validate plugin .   # exit 0 = pass + warms cache
uv run python scripts/publish.py --bump patch
```
Verified 2026-06-20 shipping v3.7.4 (the `anthropic` dep-removal release).

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
