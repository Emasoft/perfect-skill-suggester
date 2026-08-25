---
trdd-id: AXZAXMDQ
title: pss-nlp subprocess call has no timeout despite the "500ms max" comment
column: complete
created: 2026-08-19T04:32:41+0200
updated: 2026-08-25T18:23:03+0200
implementation-commits: [rust df365e7]
current-owner: pss-maintainer-session
task-type: bugfix
scope: project
labels: [rust, hot-path, audit-AX4-2]
---

# pss-nlp subprocess has no timeout — a hung child hangs the prompt hook

Source: Phase-1 self-audit finding **AX4-2**, CONFIRMED by the refutation pass
(reports/plugin-self-audit/20260816_190920+0200-refutation.md, gitignored).

## The defect (verified)

`rust/skill-suggester/src/main.rs` `detect_prompt_negations()` (~7924-7994 at audit time):
`child.spawn()` → write stdin → `child.wait_with_output()`. No `wait_timeout` crate in
Cargo.toml (grepped, zero hits), no deadline/poll loop anywhere in the function or callers.
The comment claims "500ms max"; no implementation backs it. A wedged `pss-nlp` child would
block the UserPromptSubmit hook indefinitely — this runs on every user prompt.

## Acceptance

- [x] A real deadline (~500ms) on the pss-nlp call: on expiry, kill the child and proceed with
      negation detection silently skipped (the existing graceful-fallback semantics).
- [x] The comment matches the implementation.
- [x] A test proving a stalled child does not stall the caller (e.g. a fake pss-nlp that sleeps).

## Approval log

- 2026-08-25T18:23:03+0200 — COMPLETED under USER delegation ("complete all pending tasks and
  TRDDs", 2026-08-25). `wait_child_with_deadline()` (try_wait poll loop, kill+reap on 500ms
  expiry) wired into `detect_prompt_negations`; 2 real-subprocess tests (stalled `/bin/sleep 10`
  killed at deadline; fast child's output returned). Suite 301 passed. rust commit df365e7.
