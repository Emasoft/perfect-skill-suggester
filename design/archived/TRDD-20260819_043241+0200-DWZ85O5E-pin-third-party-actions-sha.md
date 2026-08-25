---
trdd-id: DWZ85O5E
title: Pin third-party GitHub Actions to full commit SHAs
column: complete
created: 2026-08-19T04:32:41+0200
updated: 2026-08-25T18:23:03+0200
current-owner: pss-maintainer-session
task-type: security
scope: project
labels: [github-actions, supply-chain, audit-G5]
severity: major
---

# Unpinned third-party GitHub Actions (tag-rewriting exposure)

Source: Phase-1 self-audit finding **G5** (MAJOR), upheld by the refutation pass
(reports/plugin-self-audit/20260816_190920+0200-refutation.md, gitignored): no
`.github/dependabot.yml` and no in-repo ruleset mitigates it. Residual NOT-VERIFIED: a
GitHub-side ruleset could exist (needs `gh api repos/.../rulesets` — check during dev).

## The defect

Third-party actions (outside `actions/` and `github/`) in `.github/workflows/*.yml` are
referenced by version tag, not full commit SHA. Rule: `~/.claude/rules/gh-actions.md` — pin
third-party actions to a full SHA (e.g. via `pinact run`) to prevent tag-rewriting attacks.

## Acceptance

- [x] Every third-party action in `.github/workflows/` pinned to a full commit SHA with a
      trailing `# vX.Y.Z` comment (pinact-style).
- [x] First check the live repo's rulesets/Dependabot state (`gh api`) and record the result
      here, so the fix matches reality rather than the local-clone view.
- [ ] CI still green after pinning. (Verify on the next push — this ships with the next
      release; check runs by workflow name + sha.)

## Approval log

- 2026-08-25T18:23:03+0200 — COMPLETED under USER delegation (2026-08-25). Live-repo state
  recorded: rulesets `baseline-history-protect` / `baseline-pr-and-checks` /
  `baseline-tag-protect` / `perfect-skill-suggester` all active; `.github/dependabot.yml`
  ABSENT (gh api 404) — so SHA-pinning was the only mitigation and was applied. Pinned:
  `dtolnay/rust-toolchain@4360b525…` (# stable branch, 2026-08-25; ×2 in
  build-binaries.yml) and `astral-sh/setup-uv@c771a70e…` (# v9.0.0 — tag→SHA mapping
  verified via `gh api git/ref/tags/v9.0.0`, matching the pin already proven green in
  build-binaries.yml; validate.yml passes no `with:` inputs, so the v5→v9 move has no
  input-compat surface). Grep proof: zero non-SHA third-party `uses:` remain.
