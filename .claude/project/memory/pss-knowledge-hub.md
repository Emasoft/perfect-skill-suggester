---
name: pss-knowledge-hub
description: "where is PSS's hard-won project knowledge · what gotchas bite a new contributor · release keeps failing / binaries are stale / temporal queries answer empty · entry point to the PSS shared memory corpus"
ocd: 2026-07-23
lmd: 2026-08-07
metadata:
  node_type: memory
  type: project
  tier: hub
globs:
  - "scripts/publish.py"
  - "rust/skill-suggester/src/**"
  - "hooks/hooks.json"
  - ".gitignore"
  - "CLAUDE.md"
---

Entry point to PSS's **PROJECT-scope** memory — the machine-agnostic lessons every
contributor inherits with the clone. Two clusters dominate: the **release pipeline**
(what makes a ship fail, and what makes a ship LIE about having succeeded) and the
**temporal index** (a family of bugs that all fail SILENTLY, answering "nothing" instead
of erroring).

Read the cluster that matches your symptom, not the whole corpus. Every page indexes on
the SYMPTOM in its `description:`, so `memgrep recall "<what you are seeing>"` beats
reading this list.

## Applies to

### Release pipeline — `scripts/publish.py`
- [[feedback_publish_mandatory_gates]] — the gate is unbypassable BY DESIGN; never add a
  `--skip-*` flag or an env-var "trusted caller" marker. Start here before touching publish.py.
- [[publish-cpv-validation-180s-timeout]] — release fatals at validation with exit 124 on a
  cold `uvx` cache; pre-warm, then retry (the tree is still clean).
- [[publish-submodule-build-skip-stale-binaries]] — "No Rust source changes, skipping build"
  while you *did* edit `main.rs`: a parent-repo diff cannot see inside the `rust/` submodule.
- [[verify-shipped-status-against-the-tag]] — answer "did this fix already ship?" from git's
  recorded gitlink, never from a STATE note that survived a compaction.
- [[cpv-skillaudit-fp-blocks-373]] — the gate suddenly reports CRITICAL security findings in
  code that passed yesterday: the validator auto-updated, the findings are false positives.

### Repo conventions — `.gitignore`, `CLAUDE.md`
- [[what-this-repo-actually-git-tracks]] — a doc edit that never reaches another clone:
  both `CLAUDE.md` and `.claude/project/memory/` exist on disk but are gitignored. Also
  records why the "CPV forbids tracking `.claude/`" guardrail is now STALE (CPV's check
  went content-aware in its issue #120) — recheck a cross-tool blocker before obeying it.

### Indexing and merge — `scripts/pss_merge_queue.py`, `scripts/pss_discover.py`
- [[incremental-merge-must-seed-from-live-db]] — uninstalled elements reappear in suggestions:
  the incremental merge seeded its prior state from the stale `skill-index.json` artifact. Seed
  from the live DB and fail fast; also covers three sibling silent failures from the same audit.

### Temporal index — `rust/skill-suggester/src/**`
- [[absence-detection-needs-a-coverage-claim]] — removals are never detected because the
  removal-check set is derived from the survivors; the scanner must claim its DOMAIN.
- [[date-only-bound-needs-direction]] — "what changed today" answers empty: a bare date is an
  INTERVAL, and which end you want depends on the bound's direction.
- [[key-migration-carrier-enumeration]] — before re-keying anything, enumerate every carrier
  of the key from LIVE data (including ids embedded inside string values).

### Scoring engine and hook output
- [[benchmark-competition-methodology]] — how the scorer is improved: competing agents in
  worktrees against a gold benchmark, with a held-out test set to catch overfitting.
- [[feedback_hook_output_compact]] — hook suggestions stay skills-only and max 5 lines; the
  hook fires on every user message, so its output is a per-message tax.
- [[e2e-phase-must-pin-suggest-mode]] — the CI Suggestion Accuracy Gate goes red with an empty
  envelope after a default-mode flip; an e2e phase must pin the `suggest-mode` it asserts under.

## Notes and lessons learned

[^1]: [id:ATOM-4D2P-SCOP, status:valid, keywords:"pss_lessons_only_on_one_machine contributor_does_not_inherit_gotchas local_scope_memory_not_pushed promote_project_knowledge", ocd:2026-07-23, lmd:2026-07-23]
  DO NOT leave machine-agnostic PROJECT knowledge (release-pipeline gotchas, engine bugs) in
  LOCAL-scope memory, BECAUSE LOCAL lives outside the repo and is never pushed — so every
  contributor and every future clone re-learns the same trap from scratch, and the lesson's
  cost is paid again. DO apply the scope gate at WRITE time ("would a stranger cloning this
  repo on a different machine find this TRUE and USEFUL?") and route the fact here, keeping
  only the per-machine state LOCAL.
