---
name: absence-detection-needs-a-coverage-claim
description: "removals/deletions never detected · stale rows stay alive forever · 'it only notices when something else survives' · gone-but-still-listed · how to detect that a THING IS ABSENT when the container it lived in also vanished"
ocd: 2026-07-17
lmd: 2026-07-23
metadata:
  node_type: memory
  type: feedback
  tier: component
---

^G5BP6ABP [desc:"Absence-detection-by-diff needs an explicit scanner-produced coverage claim, or it silently degrades to noticing removal only when a nearby item survives.", keywords:"absence_detection_rule coverage_claim_requirement diff_based_removal_check", type:feedback, ocd:2026-07-17, lmd:2026-07-17]
Any code that detects ABSENCE by diffing "what I saw this run" against "what I knew"
must ALSO carry an explicit, produced-by-the-scanner **coverage claim** — otherwise it
silently degrades to "I only notice X is gone when something NEAR X survived".

^H9FK2SMM [desc:"PSS's temporal index derived its removal-check set from surviving elements, so a scope that dropped to zero was never checked; measured 799/10484 gone elements but only 1 detected (0.13%).", keywords:"pss_temporal_index_example zero_element_scope_never_checked 799_zombies_1_detected measured_failure_rate", type:feedback, ocd:2026-07-17, lmd:2026-07-17]
PSS's temporal index (TRDD-1Z8SGQ7N F7, fixed v3.10.6) derived its removal-check set
from the surviving elements themselves. A scope that dropped to ZERO elements was
therefore never checked, and its rows stayed `exists=true` forever. Measured on the
live index: **799 of 10,484 active elements were genuinely gone and it detected 1
(0.13 %)** — not "leaky", inoperative. Nobody noticed because absence detection fails
SILENTLY and looks exactly like "nothing was removed".

^I3OE4V8N [desc:"Enumerating scanned roots instead of results still can't see a root that no longer exists; the fix must be a domain-level coverage claim covering vanished/emptied/renamed containers uniformly.", keywords:"enumerate_roots_insufficient domain_level_claim vanished_container_uncoverable", type:feedback, ocd:2026-07-17, lmd:2026-07-17]
**Why the obvious fix doesn't work:** "enumerate the scanned ROOTS instead of the
results" still can't see a root that no longer exists — you cannot enumerate a deleted
directory. The fix must be a claim about the **DOMAIN** ("I enumerated ALL of scope S"),
which covers the vanished container, the still-present-but-now-empty container, and the
renamed one with one rule.

^IAZ5GTRD [desc:"A coverage claim is asymmetric: a false claim mass-deletes real history while under-claiming only delays a sweep, so every filter, I/O error, or empty result must drop the claim rather than assert it.", keywords:"claim_asymmetry false_claim_mass_deletes under_claim_delays_sweep filtered_scan_drops_claim unreadable_equals_empty_trap", type:feedback, ocd:2026-07-17, lmd:2026-07-17]
**Why the claim is the dangerous half:** a FALSE claim mass-deletes real history, while
under-claiming only delays a sweep to the next run. So the claim is asymmetric by
construction — every filter, every I/O error, and an empty result set each DROP it.
Concretely: a filtered scan must claim nothing; a "found zero items" scan is a broken
scan, not an empty machine; and an unreadable container must never be equal to an empty
one (`os.walk`'s default `onerror` DISCARDS the error and yields nothing — identical to
"empty" — and `Path.iterdir()` is lazy, so `try: return p.iterdir()` leaks the OSError
past the handler; materialize with `list()` INSIDE the try).

^JV9Y4890 [desc:"Test whether an absence check would still work if the whole container vanished; if not, have the scanner emit an explicit domain coverage claim, consume it, shrink it on doubt, and red-test against the unfixed build.", keywords:"how_to_apply_coverage_claim red_test_unfixed_build predict_removal_set", type:feedback, ocd:2026-07-17, lmd:2026-07-17]
**How to apply:** when you build absence/removal/GC detection, ask "if the whole
container vanished, would anything still tell me its contents are gone?" If the answer
comes only from surviving siblings, you have this bug. Emit the coverage claim from the
one component that actually knows (the scanner), consume it explicitly, and make every
uncertainty shrink it. Then prove it on real data: predict the removal SET (not a count)
from inputs alone, and red-test the gate against the UNFIXED build first — see
[[key-migration-carrier-enumeration]] for the enumeration discipline this pairs with.

Pairs with [[date-only-bound-needs-direction]] (same TRDD-1Z8SGQ7N temporal-index sweep).

## Governed by
- [[pss-knowledge-hub]] — entry point to PSS's PROJECT-scope memory corpus.

## See also

- [[incremental-merge-must-seed-from-live-db]] — the same constraint one layer down: absence in
  the merge's seed only means "really absent" if the seed came from the live store, so a stale
  seed resurrects exactly what a coverage claim is meant to retire.

## Governed by

- [[pss-knowledge-hub]]

## Notes and lessons learned

[^1]: [id:ATOM-7K2M-C0VR, status:valid, keywords:"removal_not_detected absence_detection stale_rows_never_swept gone_but_still_listed coverage_claim", ocd:2026-07-17, lmd:2026-07-17]
  DO NOT derive an absence check's scope from the surviving items, BECAUSE a container
  that lost ALL its items is then never examined and its rows live forever (799 zombies,
  1 detected). DO have the scanner emit an explicit domain coverage claim and sweep
  against that instead.

[^2]: [id:ATOM-Q4XW-9F1D, status:valid, keywords:"under_claim over_claim fail_safe_direction coverage_claim_asymmetric filtered_scan empty_scan", ocd:2026-07-17, lmd:2026-07-17]
  DO NOT let a coverage claim survive a filter, an I/O error, or an empty result,
  BECAUSE the two errors are NOT symmetric — under-claiming just delays a sweep, while
  over-claiming DELETES real history. DO drop the claim on every doubt, and treat
  "found zero" as a broken scan rather than an empty machine.

[^3]: [id:ATOM-M8VJ-2T7B, status:valid, keywords:"unreadable_directory looks_empty os_walk_onerror silent iterdir_lazy permission_error", ocd:2026-07-17, lmd:2026-07-17]
  DO NOT treat an unreadable container as an empty one, BECAUSE `os.walk`'s default
  `onerror` discards the error and yields nothing — byte-identical to "empty" — which is
  what authorizes wiping a whole scope. DO pass `onerror=`, and materialize
  `list(p.iterdir())` INSIDE the try (iterdir is lazy, so the OSError escapes an outer
  `try: return p.iterdir()`). Verified: an unreadable dir reports `exists()`/`is_dir()`
  **True**, then raises on read — so the read is the only honest probe.

[^4]: [id:ATOM-5RN3-8HQZ, status:valid, keywords:"spec_wrong_control_flow flag_inert derived_variable enumerate_flag_behavior_mapping", ocd:2026-07-17, lmd:2026-07-17]
  DO NOT spec a guard against a CLI flag without reading what the flag actually does,
  BECAUSE `--all-projects` was silently INERT under `--project-only` (`scan_all_projects
  = all_projects and not (project_only or user_only)`), so the specced guard would have
  claimed full coverage of a single-project scan and removed every other project's
  elements. DO enumerate the flag→behavior mapping, not just the flag list — the
  carrier-enumeration discipline applies to CONTROL flow, not only to data.

[^5]: [id:ATOM-B6YD-1WPK, status:valid, keywords:"idempotency_check found_unrelated_bug rerun_emits_events gate_as_detector", ocd:2026-07-17, lmd:2026-07-17]
  DO NOT treat a gate's idempotency check as mere safety ceremony, BECAUSE re-running an
  IDENTICAL input and asserting "zero further effects" is a BUG DETECTOR: it surfaced 51
  spurious events per scan from 64 same-scope records collapsing onto one key — a defect
  nobody was looking for. DO add "run it twice, expect nothing" to every write pipeline's
  gate.

[^6]: [id:ATOM-XR9F-4WNE, status:valid, keywords:"under_claim_not_always_benign permanent_failure_condition claim_never_recovers corrupt_third_party_file removal_detection_stuck_off transient_vs_permanent", ocd:2026-07-17, lmd:2026-07-17]
  DO NOT let a PERMANENT failure condition shrink the coverage claim, BECAUSE
  under-claiming is only benign for TRANSIENT failures ("delays a sweep to the next run") —
  a condition that never heals (a BOM'd/non-UTF-8 third-party file the scanner re-hits
  every scan) keeps the claim off FOREVER, recreating the very outage the claim was built
  to fix. DO ask of each wired failure site "does this condition ever go away by itself?";
  if not, probe whether anything was actually droppable (e.g. key-substring check on the
  raw text) or accept the silent skip when a never-emitted item causes zero churn anyway
  (it was never Installed, so it is never swept).
