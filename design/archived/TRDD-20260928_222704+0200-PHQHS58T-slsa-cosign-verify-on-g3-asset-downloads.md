---
trdd-id: PHQHS58T
title: SLSA cosign verify on G3 asset downloads
column: complete
status: archived
created: 2026-09-28T22:27:04+0200
updated: 2026-09-29T06:40:41+0200
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
- 2026-09-29T06:40:41+0200 — COMPLETE by main-agent@perfect-skill-suggester. release v3.17.0 shipped it: sign-release succeeded (12 sigstore bundles), G3 green end-to-end (cosign verify + fetcher e2e, run 36522369078)..

## Acceptance checklist

- [x] Keyless signing in CI: sign-release job in build-binaries.yml, tag-gated, signs the release's own bytes (12 binaries + manifest + tarball); bundles uploaded as release assets — DONE, retagged v3.17.0 run succeeded, 12 .sigstore.json bundles on the release.
- [x] G3 verifies fail-closed: manifest signed:true requires cosign verification of every bundle, identity pinned to the signing workflow at refs/tags/<tag> — DONE, verify step green on run 36522369078.
- [x] End-to-end proof on a real release: v3.17.0 signed, bundles verified, fetcher e2e green in the same G3 run; carried note — the workflow file AT TAG v3.17.0 still has the pre-phase-3 cache/bin path (no live trigger runs G3 from a tag ref; a future manual --ref v3.17.0 dispatch would replay it; superseded by the next release's tag).
