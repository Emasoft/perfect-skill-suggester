---
trdd-id: AS90UUQ5
title: Dead create_db_schema in Rust has drifted from the live Python schema — delete it
column: complete
created: 2026-08-19T04:32:41+0200
updated: 2026-08-25T18:23:03+0200
implementation-commits: [rust df365e7]
current-owner: pss-maintainer-session
task-type: refactor
scope: project
labels: [rust, cozodb, dead-code, audit-AX4-3]
---

# Dead `create_db_schema` (Rust) drifted from the live schema — remove it

Source: Phase-1 self-audit finding **AX4-3**, CONFIRMED (with a citation correction) by the
refutation pass (reports/plugin-self-audit/20260816_190920+0200-refutation.md, gitignored).

## The defect (verified)

- `rust/skill-suggester/src/main.rs` `create_db_schema` (~14271) is `#[allow(dead_code)]`,
  zero call sites (grep-verified) — its own doc comment admits "No Rust code path calls this".
- Its schema lacks the `disable_model_invocation` column that the LIVE schema
  (`scripts/pss_cozodb.py`, `disable_model_invocation: Bool` ~line 909) has, and which a LIVE
  Rust query reads (`load_noninvocable_ids`, main.rs ~4368: `*skills{ name, source,
  disable_model_invocation }`). Anyone resurrecting the dead fn would build a DB the live
  reader can't query.

## Acceptance (per the no-legacy-code project rule)

- [x] Delete `create_db_schema` and its doc-comment cross-references (main.rs ~14268, ~14681),
      OR — only if a concrete consumer is identified — sync it to the live schema and wire a
      test that diffs it against `pss_cozodb.py`'s column set. Default: delete.
- [x] `cargo test` green; grep sweep confirms no remaining references.

## Approval log

- 2026-08-25T18:23:03+0200 — COMPLETED under USER delegation (2026-08-25). Deleted (the
  default): no consumer identified. Grep sweep: only 2 deliberately-historical mentions remain
  in the replacement comment. Data helpers `insert_skills_batch`/`insert_domain_registry_batch`
  left in place (out of card scope; no verified drift). Suite 301 passed. rust commit df365e7.
