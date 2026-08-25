---
trdd-id: F12XB4AS
title: pss-nlp stdin write can block outside the deadline — cap request size
column: complete
created: 2026-08-25T18:32:52+0200
updated: 2026-08-25T18:32:52+0200
current-owner: perfect-skill-suggester-6a
task-type: bugfix
scope: project
project-id: perfect-skill-suggester
parent-trdd: AXZAXMDQ
min-approval-requirement: none
implementation-commits: [4740640 (rust submodule), 96eb932]
---

# pss-nlp stdin write can block outside the deadline — cap request size

## Problem (residual of TRDD-AXZAXMDQ, found by adversarial review 2026-08-25)

TRDD-AXZAXMDQ added `wait_child_with_deadline` (500ms) and closed with the
claim "a wedged pss-nlp child can never hang the hook". Overbroad: the
deadline guards only the WAIT. `detect_prompt_negations` performed an
unguarded synchronous `writeln!(stdin, ...)` of the WHOLE prompt BEFORE the
deadline wait. The OS pipe buffer is ~64 KiB; a request larger than that,
written to a child wedged before reading stdin, blocks the parent IN THE
WRITE — the exact hang the parent card claimed closed.

Verified empirically: a 200 KB write to a non-reading child blocked for the
full child lifetime (10.0 s) before returning EPIPE.

## Fix

`cap_nlp_text()` truncates the text sent to pss-nlp at a char boundary,
capped at `PSS_NLP_MAX_TEXT_BYTES` (8 KiB) — far below the pipe buffer, so
the write always fits in the buffer and returns immediately regardless of
child state. Negation phrases live in normal-length prompts; a 100 KB paste
gains nothing from full coverage.

## Verification

- `test_cap_nlp_text_keeps_request_under_pipe_buffer` — 200 KB multibyte
  prompt → serialized JSON request < 60 KiB; short prompts pass untouched.
- Full suite: 302 passed, 0 failed (2026-08-25).

## Approval log

- 2026-08-25T18:32:52+0200 — Tier 0 (derived bugfix of TRDD-AXZAXMDQ, in
  scope, reversible, local). Authored directly as complete with the fix.
