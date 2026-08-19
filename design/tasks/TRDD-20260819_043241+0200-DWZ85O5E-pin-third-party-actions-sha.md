---
trdd-id: DWZ85O5E
title: Pin third-party GitHub Actions to full commit SHAs
column: backburner
created: 2026-08-19T04:32:41+0200
updated: 2026-08-19T04:32:41+0200
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

- [ ] Every third-party action in `.github/workflows/` pinned to a full commit SHA with a
      trailing `# vX.Y.Z` comment (pinact-style).
- [ ] First check the live repo's rulesets/Dependabot state (`gh api`) and record the result
      here, so the fix matches reality rather than the local-clone view.
- [ ] CI still green after pinning.

## Approval log
