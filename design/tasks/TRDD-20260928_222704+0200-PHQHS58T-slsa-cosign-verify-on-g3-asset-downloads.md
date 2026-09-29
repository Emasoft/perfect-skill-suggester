---
trdd-id: PHQHS58T
title: SLSA cosign verify on G3 asset downloads
column: dev
status: tasked
created: 2026-09-28T22:27:04+0200
updated: 2026-09-29T02:14:21+0200
current-owner: main-agent@perfect-skill-suggester
created-by: main-agent@perfect-skill-suggester
task-type: security
min-approval-requirement: none
assignee: main-agent@perfect-skill-suggester
mandate: true
mandated-by: none
approved: true
approval-judge: main-agent@perfect-skill-suggester
approval-datetime: 2026-09-28T22:27:04+0200
---

# SLSA cosign verify on G3 asset downloads

## Approval log

- 2026-09-28T22:27:04+0200 — MANDATE issued by main-agent@perfect-skill-suggester (min-approval-requirement: none). Pre-approved: issuer authority >= required approver. No approval request was sent.
SCOPE CORRECTION (review fork 2026-09-28): this card is NOT 'add cosign verify on the G3 download step' — no cosign infrastructure exists, so a verify step on unsigned assets fails forever. The real decision is an END-TO-END asset-signing story: sign at publish time (key custody decision), verify at every consumer (G3, the fetcher). G3 sha-vs-manifest already defeats asset tampering and transit corruption; the marginal win is only the release-pipeline-compromised scenario, and cosign keys held by that same compromised pipeline protect nothing unless keyed externally. Decide key custody first.
- 2026-09-29T01:56:14+0200 — column → dev by main-agent@perfect-skill-suggester. implemented: keyless signing in publish.py + hard verify in G3, committed 54794b3; stays in dev until the release ships it (release-via: publish)
2026-09-29T02:45+0200 — IMPLEMENTED through 4 review rounds: keyless signing in CI (sign-release job in build-binaries.yml, tag-gated, signs the release's own bytes incl. manifest+tarball), bundles as release assets, G3 fail-closed on manifest signed:true, verify pinned refs/tags/<short>. Commits 54794b3→37bf812→2b0deda→28b442e. Round-4 verdict: keep, no fix-before-release items. Stays in dev until the release ships it.
