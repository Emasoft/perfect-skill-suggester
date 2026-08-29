---
name: key-migration-carrier-enumeration
description: migration missed a table / re-key left orphans or dangling refs / spec kept needing mid-flight corrections / id embedded inside a string value — how to spec a key migration so the inventory is complete BEFORE dispatching
ocd: 2026-07-17
lmd: 2026-07-23
metadata:
  node_type: memory
  type: feedback
  tier: component
publish-globally: false
---

^FUK1PLIS [desc:"The F4/F5 element_id re-key needed 3 mid-flight spec corrections, each a real data-corruption defect found by a later ground-truth probe: a key-keyed table missing from the spec, ids embedded inside string values invisible to a column-name scan, and a new writer verb dispatched on the unlocked query path.", keywords:"f4_f5_rekey_three_corrections id_embedded_in_string_value column_name_scan_blind unlocked_writer_race", type:feedback, ocd:2026-07-17, lmd:2026-07-17]
During the F4/F5 element_id re-key (TRDD-1Z8SGQ7N, v3.10.5) the implementation spec needed
THREE mid-flight corrections — each a real data-corruption defect, each found by a LATER
ground-truth probe, each costing an agent cold-restart (~600k tokens apiece):
1. `element_descriptions` was element_id-KEYED (9,687 rows) but absent from the spec →
   would have orphaned 1,369 description rows.
2. element_ids were EMBEDDED INSIDE string VALUES (`override_status` =
   "overridden_by:<id>", and inside `diff_json`) → 6 dangling refs + spurious override
   events on the next scan. A column-NAME scan structurally cannot see these.
3. The new writer verb was dispatched on the unlocked query path → the exact
   writer-vs-reader SIGABRT race an earlier fix (F3) had just closed.

^8NP1ZI0K [desc:"The spec inventory built by reading code missed facts only visible in live data or locking topology; before speccing any key migration, run a step-0 ground-truth enumeration (key/value columns, embeddable string/blob columns, indexes, writer paths+locking) and red-test an adversarial validator against an unmigrated DB.", keywords:"ground_truth_enumeration_step_0 live_data_over_code_reading red_test_adversarial_validator key_migration_spec_checklist", type:feedback, ocd:2026-07-17, lmd:2026-07-17]
**Why:** the spec inventory was assembled by reading code; every gap was only visible in the
LIVE DATA (or in the locking topology). Confidence in the transform (a proven bijection) is
worthless if the inventory of what to apply it to is wrong.

**How to apply:** before speccing ANY key/id migration, run a step-0 ground-truth
enumeration and paste it into the spec: (a) every relation with the key as a KEY column,
(b) every relation with it as a VALUE column, (c) every string/blob column whose VALUES can
embed it (grep the live data for the id shape, not the schema), (d) every index over it,
(e) every WRITER path and its locking. Then build an adversarial pre/post validator from
that same enumeration and RED-TEST it (feed it an unmigrated DB — it must fail) before
trusting any PASS. Batch corrections if any emerge: each mid-flight agent message is a
full cold restart.

Pairs with [[absence-detection-needs-a-coverage-claim]] (the coverage-claim discipline
this enumeration pairs with).

## Governed by
- [[pss-knowledge-hub]] — entry point to PSS's PROJECT-scope memory corpus.

## Notes and lessons learned
