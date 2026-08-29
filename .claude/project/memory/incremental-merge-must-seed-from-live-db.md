---
name: incremental-merge-must-seed-from-live-db
description: "deleted or dropped elements come back after a reindex / a partial merge resurrects entries the DB no longer has / stale suggestions for elements that were uninstalled — the incremental merge seeded its prior state from the months-stale skill-index.json artifact instead of the live CozoDB"
ocd: 2026-08-07
lmd: 2026-08-07
metadata:
  node_type: memory
  type: project
  tier: component
publish-globally: false
---

# incremental-merge-must-seed-from-live-db

Where PSS's incremental index merge is allowed to read its prior state from, and what it does
when that read fails.

**Why:** the corruption is silent and looks like a suggestion bug, not an index bug. An
uninstalled plugin's elements reappear in suggestions with no error anywhere, because the merge
believed a prior state that no longer existed. Falling back on a read error is what makes it
worse than crashing — a degraded seed produces a *plausible* DB.

**How to apply:** for any incremental/differential write, the prior state comes from the live
store, and an unreadable live store is a hard stop. Absence in the seed must mean "really
absent", which is the same constraint as
[[absence-detection-needs-a-coverage-claim]].

## Sibling defects fixed in the same commit

`365bd61` (2026-08-01) came out of a `/code-review high` audit and carried three more silent
failures worth knowing about, each in a different script:

- `pss_hook` compared an unresolved `Path.home()` against a resolved candidate. On any machine
  where `$HOME` is itself a symlink — containers, NixOS, corporate images — that raised on
  **every prompt**, blanking both `transcript_path` and `cwd`. `cwd` no longer takes the
  traversal check at all: this process never opens it, it is passed to the binary as data, and
  blanking it silently disabled project-context scoring for any project outside `$HOME`.
- `pss_reindex` wrote two fixed-name scratch files into a world-writable `$TMPDIR` with a plain
  `open(..., "wb")` — a local user could pre-plant a symlink and have the process truncate the
  target (CWE-59) — and a manual reindex racing the hook's auto-spawned one interleaved both
  outputs. They are PID-suffixed now. The `wait()` on the enrich stage is also bounded: Rust
  ignores SIGPIPE, so when the consumer exited early the write returned EPIPE instead of dying,
  and the hung stage held the `.reindex.pid` lockfile forever, blocking every future
  auto-reindex.
- `pss_cozodb` collapsed an entry reachable under two keys with `:put` but appended
  unconditionally to the aux relations, so the losing row's keywords and intents stayed in the
  lookup tables and matched skills on terms the surviving row no longer had.


^ATOM-5PT8-QYG3 [desc:"Incremental merge seeds prior state from the live CozoDB and fails fast; never from skill-index.json.", keywords: deleted_elements_come_back_after_reindex partial_merge_resurrects_dropped_entries stale_skill-index.json_seed uninstalled_plugin_still_suggested seed_from_live_db fail_fast_on_unreadable_store, type: project, ocd: 2026-08-07, lmd: 2026-08-07]

`pss_merge_queue.py` seeds an INCREMENTAL merge from the live CozoDB and FAILS FAST when that read
errors. It must never fall back to `skill-index.json` — that artifact can be months stale, so
seeding from it lets a partial merge resurrect elements the DB had already dropped. The JSON seed
survives for exactly one case: a first-ever build, where there is nothing to lose. Landed in
`365bd61` (2026-08-01). [^1]


^ATOM-3I5W-V70M [desc:"A successful json.load can still hand you a non-dict; type-check before use.", keywords: json_parses_but_is_not_an_object AttributeError_past_the_except_arm whole_scan_aborted_by_one_file third-party_plugin.json_valid_json_wrong_type, type: project, ocd: 2026-08-07, lmd: 2026-08-07]

`pss_discover` no longer aborts an entire scan when one hand-edited `settings.json` or one
third-party `plugin.json` is valid JSON but not an object. `[]`, `42` and `"x"` all parse cleanly,
then raise `AttributeError` PAST the `except json.JSONDecodeError` arm. Landed in `365bd61`. [^2]

## See also

- [[absence-detection-needs-a-coverage-claim]] — the same "absence must be trustworthy"
  constraint one layer up, in the temporal scanner.

## Governed by

- [[pss-knowledge-hub]]

## Notes and lessons learned

[^1]: [id:ATOM-RODA-LSLD, status:valid, desc:"The stale-JSON fallback made a partial merge produce a plausible-but-wrong DB with no error anywhere.", keywords:"fallback_to_stale_snapshot degraded_seed_produces_plausible_wrong_result silent_data_resurrection fail_fast_instead_of_falling_back authoritative_store_unreadable", ocd:2026-08-07, lmd:2026-08-07] DO NOT fall back to a cached or older snapshot when the authoritative store is unreadable, BECAUSE a degraded seed yields a plausible-but-wrong result that no error surfaces — here elements the DB had dropped reappeared in suggestions with nothing logged — while a hard failure is loud and cheap. DO fail fast and let the caller retry.
[^2]: [id:ATOM-9O6B-66W8, status:valid, desc:"One malformed third-party plugin.json killed the whole discovery scan.", keywords:"json.load_returned_a_list_not_a_dict exception_escapes_the_JSONDecodeError_handler one_bad_file_kills_the_whole_scan validate_parsed_type", ocd:2026-08-07, lmd:2026-08-07] DO NOT assume a successful `json.load` gave you a dict, BECAUSE `[]`, `42` and `"x"` all parse cleanly and then raise `AttributeError` PAST the `except json.JSONDecodeError` arm — so one hand-edited file killed an entire scan and the traceback pointed nowhere near the cause. DO type-check the parsed value before using it, and scope the guard so one bad input skips one input.
