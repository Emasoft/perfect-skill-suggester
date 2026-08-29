---
name: e2e-phase-must-pin-suggest-mode
description: "Suggestion Accuracy Gate red on main / e2e phase got an empty {'hookSpecificOutput':{'hookEventName':'UserPromptSubmit'}} envelope / expected a skill in the output and got nothing / looks like a scoring regression but the product is correct — the phase depended on the ambient default suggestion mode instead of pinning it"
ocd: 2026-08-07
lmd: 2026-08-07
metadata:
  node_type: memory
  type: project
  tier: component
publish-globally: false
---

# e2e-phase-must-pin-suggest-mode

How PSS's end-to-end suggestion phases must handle the `suggest-mode` setting they run under.

**Why:** the failure is indistinguishable from a scoring regression. Phase 5 seeds three skills
and asserts one is suggested back; after the v3.11.0 default flip it failed with

```
Expected test-python-linter in output, got:
{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit"}}
```

The product behaviour was right. The test was depending on an ambient default it never
asserted — so the default flip, not the scorer, turned the gate red.

**How to apply:** a phase that verifies skill suggestion says so explicitly, and a phase that
verifies agent suggestion pins `agents`. Then a future default flip changes nothing in the
suite. Mode state is one line in `<data-dir>/pss-suggest-mode`; the gate is enforced in Rust
(`suggest_mode.rs`) at the hook type-filter, so a Python-side toggle is never consulted on the
hot path.

This gate lives only in CI — `publish.py --gate` does **not** run `pss_test_e2e.py`, so a green
local gate can never catch it. Verify CI by workflow name and sha, not by the local gate and not
by `gh run list --limit 1`.


^ATOM-3A39-FI72 [desc:"Any e2e phase asserting a skill comes back must pin suggest-mode to skills; the default is agents.", keywords: suggestion_accuracy_gate_red empty_hookSpecificOutput_envelope expected_skill_in_output_got_nothing suggest-mode_default_agents pin_the_mode_in_the_phase e2e_phase_5, type: project, ocd: 2026-08-07, lmd: 2026-08-07]

Any `pss_test_e2e.py` phase that asserts a SKILL comes back from the hook must pin `suggest-mode`
to `skills` for that phase. Since v3.11.0 the default mode is `agents`, under which the hook
correctly filters skills out and emits an envelope with no `additionalContext` at all. Fixed in
`6a560fc` (2026-07-30), shipped v3.12.0. [^1]

## Governed by

- [[pss-knowledge-hub]]

## Notes and lessons learned

[^1]: [id:ATOM-F8K5-UX76, status:valid, desc:"The v3.11.0 default flip turned the accuracy gate red; the failure read as a scoring regression.", keywords:"test_depends_on_ambient_default default_flip_broke_the_test failure_looks_like_a_regression_in_the_feature_under_test assert_the_setting_you_rely_on", ocd:2026-08-07, lmd:2026-08-07] DO NOT let a test depend on a product default it does not assert, BECAUSE the day that default flips the test fails in the voice of the feature under test — here a mode mismatch read as a scoring regression, and the first instinct was to go looking at the scorer. DO pin every ambient setting the assertion actually relies on, inside the phase that relies on it.
