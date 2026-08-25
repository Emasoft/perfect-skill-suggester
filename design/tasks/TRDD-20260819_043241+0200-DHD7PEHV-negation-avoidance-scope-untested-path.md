---
trdd-id: DHD7PEHV
title: Negation rule 3 (avoidance-verb scope to end of sentence) misfires on "avoid X, use Y" and its only executing path has zero tests
column: complete
created: 2026-08-19T04:32:41+0200
updated: 2026-08-25T18:23:03+0200
implementation-commits: [rust 5be2198]
current-owner: pss-maintainer-session
task-type: bugfix
scope: project
labels: [negation-detector, rust, audit-AX4-1]
---

# Negation rule 3 misfires on "avoid X, use Y" — the executing path is untested

Source: Phase-1 self-audit finding **AX4-1**, CONFIRMED by the adversarial refutation pass
(reports/plugin-self-audit/20260816_190920+0200-refutation.md — gitignored; this TRDD is the
durable record). Hub ledger: ai-maestro repo, design/tasks/TRDD-…-BRRJK57P (§ "perfect-skill-suggester — 10 confirmed").

## The defect (verified)

`rust/negation-detector` — `compute_general_negation_scope` rule 3 extends an avoidance verb's
negation scope to end of sentence. On `"avoid react, use vue for the frontend"` this wrongly
negates "vue" too. Root cause shape: **rule written for pattern A, applies to pattern B, never
tested against B**:

- Every existing avoidance test contains the word "like", so Phase 1's `detect_avoidance_like`
  intercepts them and marks their tokens covered — Phase 2 (the function containing rule 3)
  **never runs** for any tested sentence.
- The "avoid X, use Y" construction (no "like") is the only real input that reaches rule 3,
  and zero tests exercise it.

## Acceptance

- [x] Rule 3 scope stops at a clause boundary (comma + contrastive verb like "use/prefer") or
      an equivalent validated heuristic.
- [x] Tests cover the Phase-2 path directly: at minimum `"avoid react, use vue"` (vue NOT
      negated) and a no-"like" sentence where end-of-sentence scope IS correct.
- [x] `pss-nlp` self-test table gains at least one no-"like" avoidance case.

## Approval log

- 2026-08-25T18:23:03+0200 — COMPLETED under USER delegation (2026-08-25).
  `find_avoidance_boundary()`: comma ends avoidance scope only when followed by a verb (VB*)
  or contrastive imperative; list commas continue. 2 Phase-2 tests + self-test case added;
  22 unit tests + 9/9 self-test green. rust commit 5be2198.
  KNOWN LIMITATION surfaced by the falsified first test run (pre-existing, orthogonal): the
  general Phase-2 path negates only `is_noun` tokens, and LOWERCASE "react"/"angular" POS-tag
  as verb/adjective — so "avoid react, use vue" (all-lowercase) yields NO negations at all via
  Phase 2. Capitalized forms work. If this matters in real prompts, it needs its own card (a
  tech-term noun whitelist at is_noun level, not a scope change).
