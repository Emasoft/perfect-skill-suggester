---
name: PSS publish.py mandatory gates are unbypassable
description: publish.py must block any push without lint/test/validate passing 0 issues; pre-push hook uses process ancestry (not env var) to verify publish.py is the caller, and re-runs the full gate unconditionally
ocd: 2026-07-16
lmd: 2026-07-23
metadata:
  node_type: memory
  type: feedback
  tier: component
publish-globally: false
---
^L4H7MOQG [desc:"PSS's release gate must never gain a bypass — every push must pass lint+tests+validation with 0 issues; env-var bypass markers were rejected as trivially spoofable in favor of process-ancestry checking.", keywords:"unbypassable_release_gate no_env_var_bypass process_ancestry_check spoofable_marker_rejected", type:feedback, ocd:2026-07-16, lmd:2026-07-16]
**NEVER add any bypass to the PSS release gate. Every push to GitHub MUST pass lint + tests + validation with 0 issues, enforced via two layers in the pre-push hook.**

**Why:** User explicitly requires an unbypassable release pipeline. Env vars like `PSS_PUBLISH_GATE=1` were rejected because they are trivially spoofable (`PSS_PUBLISH_GATE=1 git push` would bypass). Process ancestry walking via `ps` is the verification mechanism — harder to spoof and not a "trick". Redundant gate execution (in both publish.py and the hook) is intentional — one layer is the gate, the other is the caller check.

**Pre-push hook enforcement (git-hooks/pre-push + .git/hooks/pre-push):**

^PF16EGM1 [desc:"The pre-push hook enforces two layers: Layer 1 walks process ancestry (ps -o ppid=) looking for publish.py in any ancestor to block a direct git push; Layer 2 unconditionally re-runs publish.py --gate even if ancestry passed.", keywords:"pre_push_hook_two_layers process_ancestry_walk gate_rerun_unconditional direct_git_push_blocked", type:feedback, ocd:2026-07-16, lmd:2026-07-16]
Layer 1 — **Ancestry check**: walks `ps -o ppid= -p $pid` up the process tree looking for `publish.py` in any ancestor's command line. If not found, block the push with an ERROR banner. This stops direct `git push` invocations by humans or non-publish.py scripts.

Layer 2 — **Gate re-run**: runs `publish.py --gate` (lint + tests + validation) unconditionally, even if ancestry passed. Redundant with publish.py's own gate execution, but a bypass is not.

^JTRZUEKV [desc:"publish.py rules: no --skip-* flags, fixed pipeline order, every gate uses fatal() never warn() except NIT-level exit code 4, required tools missing is fatal, changelog/gh-release mandatory; forbidden patterns include spoofable env vars, warn-instead-of-fatal, and git push --no-verify.", keywords:"publish_py_no_skip_flags fatal_not_warn_gates nit_level_exception forbidden_bypass_patterns_list", type:feedback, ocd:2026-07-16, lmd:2026-07-16]
**publish.py rules:**
- No `--skip-build`, `--skip-tests`, `--skip-validate`, `--version-only` flags
- Pipeline order fixed: preflight → lint → test → validate → bump → changelog → commit → push → gh release
- Every gate uses `fatal()` on failure, never `warn()`
- Required tools (`uv`, `uvx`, `rustup`, `git-cliff`, `gh`) missing = fatal
- Changelog generation via `git-cliff` = fatal if it fails
- GitHub release via `gh release create` = mandatory step
- NIT-level validation findings (exit code 4) are the ONLY thing allowed to warn-and-continue

**Forbidden bypass patterns (flag and refuse if reintroduced):**
- Env vars like `PSS_PUBLISH_GATE=1` or similar "trusted caller" markers (spoofable)
- `warn(...)` instead of `fatal(...)` for any gate failure
- Marking required tools as "recommended"
- Making changelog/release steps "best-effort"
- Any `--skip-*` flag
- `git push --no-verify` in any script

## See also
- [[cpv-skillaudit-fp-blocks-373]] — a CPV security-gate false-positive incident that cites this page's unbypassable-gate rule.
- [[publish-cpv-validation-180s-timeout]] — a CPV validation-timeout failure at the gate this page governs.
- [[publish-submodule-build-skip-stale-binaries]] — a stale-binary incident at the same publish.py gate.

## Governed by
- [[pss-knowledge-hub]] — entry point to PSS's PROJECT-scope memory corpus.

## Notes and lessons learned
