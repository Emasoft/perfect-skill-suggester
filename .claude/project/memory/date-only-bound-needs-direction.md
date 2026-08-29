---
name: date-only-bound-needs-direction
description: "changed-between / installed-between / as-of returns nothing (or too much) for a bare date · 'what changed today' answers empty against real events · a since/between date filter silently drops a whole day · RFC3339 timestamp comparison misses events at the same second · one date parser serving both start and end bounds"
ocd: 2026-07-17
lmd: 2026-07-23
metadata:
  node_type: memory
  type: project
  tier: component
publish-globally: false
---

^Q8C0PB99 [desc:"A date literal denotes an interval but a query cutoff needs an instant, and which end of the interval to use depends on the bound's direction, so a single shared date parser cannot choose correctly without a direction parameter.", keywords:"date_literal_interval_vs_instant bound_direction_dependency shared_parser_ambiguity", type:project, ocd:2026-07-17, lmd:2026-07-17]
A **date literal denotes an INTERVAL, but a query cutoff needs an INSTANT** — and which
end of the interval you want depends on the bound's **DIRECTION** (a lower/`>=` bound wants
the day's FIRST instant `T00:00:00`, an upper/`<=` bound wants its LAST `T23:59:59.999999999`).
A single shared date parser CANNOT choose correctly from its argument alone, because the
argument (`"2026-07-16"`) is identical for both roles. So the parser must take the direction
as a parameter.

^R4FT3MEM [desc:"PSS's single unified parse_date mapped every date-only input to end-of-day, correct for as-of but silently wrong for lower bounds, so 'changed-between D D' returned zero rows against 10,123 real events until fixed in v3.10.8 with a direction-aware parse_date_bound.", keywords:"parse_date_unified_bug end_of_day_wrong_for_lower_bound changed_between_zero_rows v3_10_8_fix parse_date_bound_direction_param", type:project, ocd:2026-07-17, lmd:2026-07-17]
**Why:** PSS had one `parse_date` (unified across every subcommand by COR-7) that mapped
every date-only input to **end-of-day**. Correct for `as-of <date>` (an upper bound = "everything
that day"), but silently wrong for every LOWER bound it was later reused for. Result: a date-only
start meant `>= T23:59:59Z`, so `changed-between 2026-07-16 2026-07-16` ("what changed today?")
returned **(no results)** against **10,123 real events** — the most natural query a user can type,
structurally always answering nothing. Shipped live in v3.10.7; fixed in v3.10.8 by
`parse_date_bound(arg, Bound::Start|End)` returning a `DateTime<Utc>` instead of a formatted
string, with each of ~19 call sites assigned Start/End from **the comparison operator it feeds**
(`>=`/`>` → Start, `<=`/`<` → End), read from the query — never guessed from the command name.

**Two compounding traps, both proven in the live engine, both about STRING-comparing RFC3339:**
^SYRXO3NF [desc:"CozoDB string-compares RFC3339 timestamps, so a Z-form cutoff sorts after every fractional value of its own second and silently excludes real in-window events stored in offset-form+fractional; the fix is to return the parsed instant and let each storage family format for itself, never a pre-formatted string.", keywords:"rfc3339_string_compare z_form_vs_offset_form same_second_exclusion cozodb_lexical_sort return_instant_not_string", type:project, ocd:2026-07-17, lmd:2026-07-17]
1. **Format must match storage, or same-second comparisons break.** CozoDB compares timestamps
   as strings. At index 19, `'+'`(0x2B) < `'.'`(0x2E) < digits < `'Z'`(0x5A). So a Z-form cutoff
   (`…12Z`) sorts AFTER every fractional value of its own second (`…12.46+00:00`), and
   `observed_at >= "…12Z"` silently EXCLUDES a real event at `…12.46`. The temporal tables store
   offset-form+fractional; the parser emitted Z-form → boundary events lost. Fix: don't return a
   pre-formatted string from the parser — return the instant and let **each storage family format
   for itself** (legacy Z-form via `to_rfc3339_opts(Secs,true)`, temporal offset-form via
   `to_rfc3339()`). That is why returning a `DateTime` (not a `String`) is the load-bearing choice.
^V8QH8A7O [desc:"Never rewrite stored append-only history to match a cutoff-format mismatch — 19,258 offset-form rows were correct as stored; rewriting them to Z-form would destroy real sub-second precision, so the fix belongs on the query/cutoff side only.", keywords:"never_migrate_append_only_history storage_was_correct_fix_the_query destroy_subsecond_precision_risk", type:project, ocd:2026-07-17, lmd:2026-07-17]
2. **Never migrate append-only history to "fix" a format mismatch.** 19,258 stored rows were
   offset-form; rewriting them to Z-form would destroy legitimate sub-second precision AND rewrite
   precious history. Storage was correct — only the CUTOFF format was wrong. Change the query side.

^VQ1AKJLM [desc:"When a date/time argument feeds a range query, resolve it to the matching end of its day per bound direction rather than one default; when timestamps are string-compared, prove the cutoff format matches storage at the same second including fractions, and add a bare-date test case since existing tests only used relative/explicit-instant inputs.", keywords:"how_to_apply_direction_aware_date_bound bare_date_test_case_missing string_compare_format_must_match_storage", type:project, ocd:2026-07-17, lmd:2026-07-17]
**How to apply:** whenever a date/time argument feeds a range query, ask FIRST "is this a lower
or an upper bound?" and resolve a bare date to the matching END of its day. When one parser serves
many subcommands, make it direction-aware rather than picking one default that happens to suit the
first caller. And when timestamps are string-compared (CozoDB, lexical indexes, sorted logs),
prove the cutoff's byte-format matches what is STORED, at the same second, with fractions present —
a passing test on `2026-07-15`-style whole-day inputs will not catch it. Both bugs survived every
existing test because the dev-facing smoke tests only ever used relative (`1d`) or explicit-instant
RFC3339 inputs — never a bare date — so **add a bare-date boundary case to any date-filter test**.

Pairs with [[absence-detection-needs-a-coverage-claim]] (same TRDD-1Z8SGQ7N temporal-index sweep)
and [[verify-shipped-status-against-the-tag]] (both bugs were proven dead by running the freshly
shipped binary against a live-DB copy, not by trusting the pipeline's success exit).

## Governed by
- [[pss-knowledge-hub]] — entry point to PSS's PROJECT-scope memory corpus.

## Notes and lessons learned

[^1]: [id:ATOM-D8B2-DIR3, status:valid, keywords:"date_only_lower_bound end_of_day shared_date_parser what_changed_today empty_result direction_aware_bound", ocd:2026-07-17, lmd:2026-07-17]
  DO NOT reuse one date parser for both a lower and an upper bound when it resolves a bare date to
  ONE end of the day, BECAUSE the bare date is identical for both roles so the wrong end silently
  skips (or over-includes) a whole day — `changed-between D D` returned 0 rows against 10,123 real
  events. DO make the parser direction-aware (`Bound::Start`→`T00:00:00`, `Bound::End`→
  `T23:59:59.999999999`), assigning each call site from the comparison operator it feeds.

[^2]: [id:ATOM-9F1C-RFCZ, status:valid, keywords:"rfc3339 string comparison same second Z_form offset_form fractional_seconds boundary_event_lost cozodb", ocd:2026-07-17, lmd:2026-07-17]
  DO NOT emit a Z-form (`…12Z`) cutoff to string-compare against offset-form+fractional stored
  timestamps (`…12.46+00:00`), BECAUSE `'.'`(0x2E) < `'Z'`(0x5A) so the Z cutoff sorts after every
  fraction of its own second and `>= cutoff` drops real in-window events. DO return the parsed
  INSTANT and let each storage family format for its own on-disk shape; never migrate append-only
  history to paper over the mismatch.
