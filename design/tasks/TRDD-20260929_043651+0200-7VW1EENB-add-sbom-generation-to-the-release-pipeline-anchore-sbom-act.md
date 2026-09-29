---
trdd-id: 7VW1EENB
title: Add SBOM generation to the release pipeline (anchore/sbom-action or syft, attached as a release asset)
column: backburner
status: tasked
created: 2026-09-29T04:36:51+0200
updated: 2026-09-29T13:24:03+0200
current-owner: main-agent@perfect-skill-suggester
created-by: main-agent@perfect-skill-suggester
task-type: security
min-approval-requirement: none
assignee: main-agent@perfect-skill-suggester
mandate: true
mandated-by: none
approved: true
approval-judge: main-agent@perfect-skill-suggester
approval-datetime: 2026-09-29T04:36:51+0200
review-after: 2026-10-13
---

# Add SBOM generation to the release pipeline (anchore/sbom-action or syft, attached as a release asset)

## Approval log

- 2026-09-29T04:36:51+0200 — MANDATE issued by main-agent@perfect-skill-suggester (min-approval-requirement: none). Pre-approved: issuer authority >= required approver. No approval request was sent.
- 2026-09-29T04:37:03+0200 — column → backburner by main-agent@perfect-skill-suggester. legit gap from janitor drift; new scope (SBOM tool choice + attach point) — parked, not auto-added to a freshly reviewed workflow
2026-09-29 review: park deemed sound (SBOM of a static musl binary is thin — mostly the runner env; tool choice is a real decision). review-after set so the park self-expires.
2026-09-29 — goal-driven unpark assessment: SBOM of a static musl binary remains thin (the artifact is native code, not a dependency tree); the SLSA cosign chain (PHQHS58T, shipped in v3.17.0) already covers the provenance gap the janitor drift named. Stays on backburner pending a USER decision on tool choice (anchore/sbom-action vs syft) — it is a real new workflow surface, not auto-addable during the current release.
