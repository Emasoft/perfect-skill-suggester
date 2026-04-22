# TRDD-46ac514e-3627-44a6-b916-f37a1504b969 — Unify PSS index on CozoDB (drop skill-index.json as canonical)

**TRDD ID:** `46ac514e-3627-44a6-b916-f37a1504b969`
**Filename:** `design/tasks/TRDD-46ac514e-3627-44a6-b916-f37a1504b969-cozodb-unification.md`
**Tracked in:** this repo (design/tasks/ is git-tracked)
**Status:** Done (shipped in v3.0.0 on 2026-04-16)
**Created:** 2026-04-16
**Completed:** 2026-04-16
**Target release:** v3.0.0 (major bump — drops JSON as canonical, adds pycozo[embedded] dependency)

---

## Why this TRDD exists

PSS currently maintains two stores for the element index:

1. `skill-index.json` — canonical source of truth, written by Python
2. `pss-skill-index.db` — CozoDB derived runtime cache, written by Rust from the JSON

I (the architect) spent the earlier part of the session defending this dual-store
design as a textbook canonical-source + derived-index pattern. The user pushed
back; I dug in and rationalised it. Then within the same session a concrete bug
surfaced that was *exactly* the failure mode the dual-store makes possible:

- `scripts/pss_paths.py::get_data_dir()` resolved the data dir via
  `$CLAUDE_PLUGIN_DATA`
- During a `/pss-reindex-skills` call, `$CLAUDE_PLUGIN_DATA` had leaked from a
  different plugin's (`codex-openai-codex`) context
- The reindex wrote a fresh, valid, uncorrupt `skill-index.json` (8,479 entries
  including the just-installed `tailwind-4-docs` skill) to the wrong directory
- `~/.claude/cache/skill-index.json` (the path the hook actually reads) stayed
  stuck at a Mar 20 snapshot with 10,112 stale entries
- PSS silently served stale suggestions with no error, no warning, no corruption
  flag — because no file was corrupt in the byte sense, they were just
  divergent at two paths

This is the whole category of bug the user warned me about and I dismissed.
Atomic `os.replace` protects bytes from tearing. It does not protect against
writing the right bytes to the wrong file. With two independent stores, the
number of places that can silently desync grows with the number of callers.

A single CozoDB at a deterministic path eliminates this category of bug:
there is nothing to desync against. Hook and reindex either agree on the path
or neither works — which is a failure that screams instead of whispering.

v2.9.40 ships an immediate path-resolution patch for the leak (see
scripts/pss_paths.py). This TRDD tracks the proper fix: stop treating JSON as
canonical.

## Scope

### In scope

- **Canonical store**: CozoDB (`pss-skill-index.db`) becomes the single source
  of truth. Schema version-bumped; all row-level writes go through it.
- **Python writers**: `pss_merge_queue.py`, `pss_hook.py` auto-reindex path,
  and any maintenance tooling write via `pycozo[embedded]` directly.
- **Python readers**: `pss_make_plugin.py`, `pss_verify_profile.py`,
  `pss_generate.py` read via pycozo queries instead of full JSON parse.
- **Rust binary**: `run_build_db` is removed. The Rust pass1_batch/enrich
  output goes directly into CozoDB via the same schema; the Rust hook read
  path already uses CozoDB (`load_candidates_from_db`) so no runtime change.
- **Debug export**: new `pss export --json [--path P]` subcommand dumps a
  snapshot of the CozoDB to a JSON file on demand, preserving the
  `git diff skill-index.json` debugging workflow for humans who want it.
- **Migration**: on first launch of the new binary, if a legacy
  `skill-index.json` is present and the CozoDB is older or missing, import
  the JSON into CozoDB once and log a "migrated" message.
- **Documentation**: update `docs/PSS-ARCHITECTURE.md`, `README.md`'s
  "Why PSS Keeps Two Indexes" subsection (rewrite in past tense as a
  migration note), and `CHANGELOG.md`.
- **Version bump**: v2.9.x → v3.0.0. Breaking-change header: "canonical
  store changed from JSON to CozoDB; `skill-index.json` becomes optional
  export only."

### Explicitly out of scope

- **Dropping the Rust scorer**. Rust still owns the hot-path hook scoring
  via `load_candidates_from_db` — this is the kw_lookup pre-filter that
  makes PSS fast. The migration only changes the *source of truth*, not
  the runtime query path.
- **Changing the scoring algorithm** or any other behaviour visible to the
  suggestion output. The migration must be a pure refactor.
- **Removing `~/.claude/cache/` as a fallback**. PSS will still write there
  if `$CLAUDE_PLUGIN_DATA` is not PSS-scoped (per the v2.9.40 patch).
- **Rewriting `pss_discover.py`** — it emits `.pss` staging files that the
  merge step consumes; the emission format doesn't need to change.

## Implementation plan (staged)

The migration is big enough that it should ship in three phases across three
releases, not one. This de-risks the pycozo wheel dependency and lets us
validate each phase in isolation.

### Phase A — v2.10.0: `pss_hook.py` reads from CozoDB via pycozo

**Goal**: prove pycozo[embedded] works on all platforms PSS supports and
that the runtime hook path can read the CozoDB without going through JSON.

- Add `pycozo[embedded] >= 0.x` to `pyproject.toml` under `[project.dependencies]`
  (with a conditional marker if needed for PSS's platform matrix — darwin,
  linux, windows; Apple Silicon RocksDB wheel has historically been flaky).
- `scripts/pss_hook.py:645-667` currently does a 256-byte JSON header
  sanity check on `skill-index.json`. Replace with a pycozo query that
  counts rows in the `skills` table. If the DB is missing/corrupt,
  trigger auto-reindex (existing code path).
- No other Python changes. JSON still canonical. CozoDB still rebuilt from
  JSON on every reindex.
- CI adds pycozo install + smoke test to the validation gate.
- Ship.

### Phase B — v2.11.0: Python writers produce CozoDB directly

**Goal**: invert the canonical/derived relationship. CozoDB becomes canonical;
JSON becomes a derived export.

- `scripts/pss_merge_queue.py::atomic_write_json` deprecated. Replace with
  `atomic_write_cozodb` that opens the target DB under `fcntl.LOCK_EX` and
  does an atomic `:replace` on the `skills` table. `.pss` staging files
  still feed in via the existing merge queue.
- `scripts/pss_reindex.py` calls the new writer. The Rust `run_build_db`
  step is still invoked for backward compat but becomes a no-op that logs
  a deprecation warning.
- Add `rust/skill-suggester/src/main.rs` subcommand: `pss export --json
  [--path P]`. Reads CozoDB via the existing `load_index_from_db` function,
  serialises to JSON, atomic-writes to the requested path. Default path is
  `$CLAUDE_PLUGIN_DATA/skill-index.export.json`. Documents the intent:
  "for debugging and `git diff` workflows only — not read by the runtime."
- `scripts/pss_merge_queue.py` still writes a `skill-index.json` file next
  to the CozoDB, but now it's the *export*, generated after the CozoDB
  write succeeds. The JSON is still valuable for humans, just no longer
  canonical.
- Ship.

### Phase C — v3.0.0: Drop JSON as canonical

**Goal**: JSON is fully demoted to "optional debug export."

- `scripts/pss_make_plugin.py`, `pss_verify_profile.py`, `pss_generate.py`
  all migrate to pycozo queries. Remove their JSON read paths.
- `scripts/pss_hook.py` removes the JSON fallback branch (already read from
  CozoDB in Phase A; now there's no fallback).
- `scripts/pss_merge_queue.py` stops auto-writing the JSON export. Users
  run `pss export --json` on demand.
- Rust binary: `run_build_db` removed entirely. The Rust enrichment pipeline
  writes directly into CozoDB at merge time.
- **BREAKING CHANGE**: `skill-index.json` at `$CLAUDE_PLUGIN_DATA` is no
  longer automatically maintained. Any external tool that reads it must
  either invoke `pss export --json` first or migrate to pycozo.
- Documentation: rewrite the "Why PSS Keeps Two Indexes" README subsection
  as "Why PSS used to keep two indexes — and what changed in v3.0".
- Version bump v2.11.x → v3.0.0.
- Ship.

## Files touched (by phase)

### Phase A
| File | Change |
|------|--------|
| `pyproject.toml` | Add `pycozo[embedded]` dep |
| `scripts/pss_hook.py` | Replace 256-byte JSON check with pycozo table-count query |
| `scripts/pss_cozodb.py` (new) | Thin pycozo wrapper — open_db, count_skills, etc. |
| `tests/test_pss_cozodb_smoke.py` (new) | Smoke test that the binding imports and opens a DB |
| `.github/workflows/validate.yml` | Install pycozo in CI |

### Phase B
| File | Change |
|------|--------|
| `scripts/pss_merge_queue.py` | Add atomic_write_cozodb, deprecate atomic_write_json |
| `scripts/pss_reindex.py` | Deprecate JSON→CozoDB build step |
| `rust/skill-suggester/src/main.rs` | Add `pss export --json` subcommand |
| `scripts/pss_cozodb.py` | Add write/replace helpers |

### Phase C
| File | Change |
|------|--------|
| `scripts/pss_make_plugin.py` | Migrate to pycozo queries |
| `scripts/pss_verify_profile.py` | Migrate to pycozo queries |
| `scripts/pss_generate.py` | Migrate to pycozo queries |
| `scripts/pss_hook.py` | Remove JSON fallback branch |
| `scripts/pss_merge_queue.py` | Stop auto-writing JSON export |
| `rust/skill-suggester/src/main.rs` | Remove `run_build_db` |
| `README.md` | Rewrite "Why PSS Keeps Two Indexes" as historical note |
| `docs/PSS-ARCHITECTURE.md` | Update architecture diagrams |
| `CHANGELOG.md` | Document breaking change |

## Risks

| Risk | Severity | Mitigation |
|------|---------|------------|
| `pycozo[embedded]` native wheel fails on Apple Silicon in CI | Medium | Phase A validates this in isolation. If it fails, add a cargo-based Rust-CLI wrapper that Python calls via subprocess as an alternative. |
| pycozo schema drift between Rust and Python writers | High | Share a single SQL-like schema string. Both Rust and Python read/write the same `:create` statements. A schema-version table enforces compatibility. |
| Losing `git diff skill-index.json` as a debug tool | Low | `pss export --json` preserves it on demand. Document the workflow in DEVELOPMENT.md. |
| Broken migration for existing installs (stale CozoDB) | Medium | First-launch migration step: detect legacy JSON-only state, import JSON into CozoDB, log "migrated". |
| Python scripts that currently parse the full JSON structure (for stats, debugging) | Low | Ship a helper: `pss export --json | jq ...` or `python -m pss_cozodb dump` for ad-hoc inspection. |

## Verification

- **Phase A ship gate**: `pycozo[embedded]` installs on darwin-arm64,
  darwin-x86_64, linux-x86_64, linux-arm64, windows-x86_64; hook health
  check queries the DB without error; existing benchmarks show no
  regression in hook latency (< 30ms p50).
- **Phase B ship gate**: end-to-end reindex produces both a live CozoDB
  and a valid `skill-index.export.json` that contains the same element
  set (diff must show zero material differences).
- **Phase C ship gate**: `uv run python scripts/publish.py --gate` passes;
  a clean-install user can run `/pss-reindex-skills` and receive
  suggestions without any `skill-index.json` existing. All 4 Python
  scripts that used to read JSON now read CozoDB.

## Success criteria

1. A single source of truth for the element index — no dual-store pathology.
2. `$CLAUDE_PLUGIN_DATA` leak from a foreign plugin scope cannot desync the
   index because there is only one store to write to.
3. Python cold-path tools (`pss_make_plugin`, `pss_verify_profile`) no
   longer full-parse 11 MB of JSON to find one element; they use indexed
   pycozo queries with latency < 10 ms.
4. Runtime hook p50 latency unchanged or improved.
5. Power users can still inspect the index via `pss export --json` +
   `git diff` on demand.

## Related commits / evidence

- Commit `0000000` (v2.9.40): ships the path-resolution bandaid that fixes
  the immediate symptom. This TRDD tracks the proper fix.
- Session 2026-04-16: concrete evidence of the bug — reindex wrote to
  `codex-openai-codex/skill-index.json` (8,479 rows with tailwind-4-docs),
  leaving `~/.claude/cache/skill-index.json` frozen at the Mar 20
  snapshot (10,112 stale rows, no tailwind-4-docs). Hook served stale
  suggestions with no error.
- `docs/PSS-ARCHITECTURE.md` currently still documents the dual-store
  design as intentional; update in Phase C.

---

## Completion record (2026-04-16)

All three phases shipped on the same day. Every success criterion verified
against the shipped code at v3.2.9 (this session, 2026-04-22):

| Phase | Version | Commit | Ship date |
|-------|---------|--------|-----------|
| Bandaid + TRDD | v2.9.40 | `4077c1d` | 2026-04-16 |
| Phase A — pycozo query helpers + `indexed_at` | v2.9.41 | `783f169` | 2026-04-16 |
| Phase B — Python canonical writer, JSON derived | v2.10.0 | `f6a3f49` | 2026-04-16 |
| Phase C — JSON demoted to optional export | v3.0.0 | `12d04a0` | 2026-04-16 |

Verified in-code:

- `pyproject.toml` pins `pycozo[embedded]>=0.7.6`; `uv.lock` resolves it.
- `scripts/pss_cozodb.py` is the canonical thin wrapper (open_db,
  count_skills, get_all_entries, atomic_write_cozodb, etc.).
- `scripts/pss_hook.py` no longer has the 256-byte JSON header check;
  only a legacy migration path at line 671 that imports a pre-v3.0 JSON
  into CozoDB once and logs "migrated".
- `scripts/pss_merge_queue.py` writes via `atomic_write_cozodb`; the
  surviving `atomic_write_json` at line 276 is the *debug export*, not
  the canonical write.
- `scripts/pss_make_plugin.py`, `pss_verify_profile.py`, `pss_generate.py`
  all read via `pss_cozodb.get_all_entries()`; `pss_verify_profile.load_index`
  now explicitly ignores the path argument and documents the Phase C
  change in its docstring.
- Rust binary: `cmd_export` implements `pss export --json [--path P]`;
  `run_build_db` removed (three comment markers at rust/.../main.rs:13536,
  13691, 13943 confirm the removal).
- `tests/unit/test_phase_c_cozodb_migration.py` + `test_pss_cozodb_phase_b.py`
  + `test_pss_cozodb_escape.py` lock the invariants via 30+ tests (all
  passing in the 81-test suite as of v3.2.9).
- `README.md` §391 "Why PSS used to keep two indexes — and what changed
  in v3.0" is rewritten in past tense with the migration story.
- `CHANGELOG.md` lists all three phase releases under 2026-04-16.

No follow-up work is owed by this TRDD. Keeping the file as historical
reference — the "why" section documents the real-world bug that motivated
the migration and the architectural reasoning behind the single-store
model.
