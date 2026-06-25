---
trdd-id: LIFEV38X
title: v3.8 — Lifeline engine for external time-travel consumers (issue #10)
column: complete
created: 2026-06-25T07:36:06+0200
updated: 2026-06-25T08:10:59+0200
current-owner: pss-main-session
task-type: feature
release-via: publish
publish-target: emasoft-plugins
relevant-rules: []
external-refs: ["github.com/Emasoft/perfect-skill-suggester/issues/10"]
supersedes: []
test-requirements: [unit, lint, typecheck]
impacts: [public-api, install-script]
---

# TRDD-LIFEV38X — v3.8 Lifeline engine for external time-travel consumers (issue #10)

## ⏵ STATE — READ THIS FIRST ON RESUME (authoritative; supersedes the body) — 2026-06-25

**What this is:** PSS GitHub issue #10 is an umbrella of 10 problems (P-1…P-10)
filed by a downstream consumer (AI Maestro's chat-history "context panel") that
needs the temporal/lifeline engine usable from an external time-travel client.
This TRDD tracks the v3.8.0 resolution. Task #43 ("v3.8 roadmap umbrella") is the
backlog entry this fulfills; #43's old label (schema-v3 / DBE / DI-1 waves) was a
broader speculative roadmap — the ACTUAL actionable work is issue #10.

**Current state — SHIPPED as v3.8.1 + VERIFIED (185 Rust tests pass; the rebuilt
binaries answer `--contract-version`/`active-in`/`db-path`/`project-slug`; #10
closed; #12 filed for the deferred P-8/P-9-MCP). v3.8.0 was a broken interim tag
(stale binaries — see lesson [^2]); v3.8.1 is the correct release. Per-P:**

| P | Disposition in v3.8.0 |
|---|---|
| P-1 (BLOCKER) `active-in <abs-path> --as-of <T>` | DONE — new verb; union of (a) local rows whose scope_path == folder slug, (b) all user-scope, (c) currently-enabled plugin/marketplace; same row shape as `as-of`; default UNLIMITED. |
| P-2 `db-path` | DONE — new verb prints canonical resolved DB path (`--format json` too). |
| P-4 first-seen | DONE — `as-of`/`active-in` rows now carry `first_seen` (earliest install event) + `first_seen_is_synthetic` (true when it's the v1→v2 migration placeholder). |
| P-6 `project-slug <abs-path>` | DONE — new verb; byte-for-byte identical to Python `_slugify_project_path` (`<basename>-<first8 sha256>`), parity test. |
| P-7 silent truncation | DONE — `as-of`/`active-in` default UNLIMITED (sentinel 1_000_000) instead of truncating; documented in `--help`. |
| P-9 contract handle | PARTIAL — global `--contract-version` flag prints `{cli_version,schema_version,contract_version}`. MCP-server surface SPLIT to a follow-up issue (out of scope for v3.8). |
| P-3 reindex/history | DOCUMENTED — janitor `pss-reindex-due` cron (or periodic manual `/pss-reindex-skills`) is REQUIRED for lifecycle history to accrue; one scan ⇒ one synthetic install event. |
| P-5 `diff` blobs | DOCUMENTED — `diff` is content-hash-only when `element_blobs` is empty (blob capture is opt-in, storage-heavy). |
| P-10 direct DB read | DOCUMENTED — external consumers MUST shell out to the binary; never read the .db (undocumented fcntl lock; cozo-ce SIGABRT on race). |
| P-8 per-project enablement | SPLIT to follow-up — faithful per-project, per-PAST-T plugin enablement needs a per-(element,project) enablement-event schema change (going-forward data collection). The DI-3 global effective-enabled logic already exists; `active-in`'s `--help` states the fidelity limit honestly. |

**Also in v3.8.0:** task #51 — `publish.py::bump_versions` now syncs the rust crate's
own version inside the WORKSPACE lock `rust/Cargo.lock` (NOT the orphan
`rust/skill-suggester/Cargo.lock`) on EVERY release, anchored on the crate name so
it self-heals prior drift (HEAD lock was stuck at 3.7.3 because 3.7.6 was a no-.rs
release). Verified the regex matches the real workspace lock (count=1, 1 stanza).

**NEXT ACTION:** none — DONE. v3.8.1 shipped + verified; publish.py submodule
build-skip + Cargo.lock-sync (#51) fixes shipped; #10 closed; #12 filed; tasks
#43/#51 completed. Future work (if wanted): #12 (P-8 schema + P-9 MCP).

**SUPERSEDED — do NOT carry forward:**
- ✗ "#43 = CozoDB schema-v3 migration / DBE 48→12MB compaction / DI-1 waves" — that
  was a speculative roadmap label; the real v3.8 deliverable is issue #10's
  external-consumer enablement, above. The compaction/DI-1 ideas are NOT in v3.8.

**Durable artifacts (evidence):**
- `reports/pss-issue10-codemap/20260625_063349+0200-codemap.md` — code surface map.
- `reports/pss-issue10-wave1/…` (P-2/P-6/P-9), `…wave2/…` (P-1/P-4/P-7), `…wave3/…` (docs).

## Files touched (v3.8.0)

- `rust/skill-suggester/src/main.rs` — `DbPath`/`ProjectSlug`/`ActiveIn` clap variants,
  `--contract-version` global flag, dispatch arms, helper fns, tests.
- `rust/skill-suggester/src/temporal.rs` — `build_first_seen_map`/`as_of_rows`/
  `active_in_rows`, `cmd_active_in`, P-4/P-7 wiring, tests.
- `scripts/publish.py` — #51 Cargo.lock self-version sync (workspace lock).
- `docs/pss-cli-reference.md`, `skills/pss-cli-reference/**` — new verbs/fields +
  "External time-travel consumers — known limitations" (P-3/P-5/P-8/P-10).

## Why P-8 and the MCP surface are split, not skipped

Both are genuinely going-forward / larger-surface than a feature add:
- **P-8**: PSS records ONE `enabled` per element (global), not per-(element,project).
  Faithful per-project enablement at a PAST instant requires new enablement events
  keyed by project — a schema/observation change that only accrues fidelity forward.
  Hacking a half-correct per-project flag into the global observation would pollute
  the index. `active-in` ships the structural union now and documents the limit.
- **P-9 MCP**: an MCP server is a new transport surface; `--contract-version` gives
  integrators the stable handle they asked for in the interim. The consumer is
  shelling out to the binary (their stated plan), so the MCP server is not blocking.

## Notes and lessons learned

[^1]: [ocd:2026-06-25 lmd:2026-06-25] The `#51` fix first targeted
  `rust/skill-suggester/Cargo.lock` (a STALE orphan per-crate lock at 2.4.10) — but
  cargo maintains the WORKSPACE lock `rust/Cargo.lock`, which is also the one
  `publish.py::git_commit` stages inside the submodule. Lesson: in a cargo
  workspace the authoritative lockfile is at the workspace root, not beside the
  crate manifest; verify which file the build/commit actually touches before
  patching it.
[^2]: [ocd:2026-06-25 lmd:2026-06-25] v3.8.0 shipped with STALE binaries: the
  lifeline-verb build was silently skipped. Root cause — `publish.py`'s
  `rust_source_changed()`/`nlp_source_changed()` ran `git diff <tag> HEAD --
  rust/.../src` in the PARENT repo, but the `.rs` sources live in the `rust/`
  SUBMODULE, which the parent tracks only as a gitlink (a single commit SHA). The
  diff therefore never saw file-level changes and always reported "no Rust source
  changes" → build skipped → bin/ never recompiled. Detected by VERIFYING the
  shipped binary (`./bin/pss-darwin-arm64 --contract-version` was rejected), not
  by trusting the release's "complete" signal. Fix: diff INSIDE the submodule
  between `git rev-parse <tag>:rust` and the submodule HEAD; v3.8.1 with
  `--force-build` shipped the correct binaries. Lesson: in a submodule
  architecture, EVERY parent-repo `git diff -- <submodule>/...` is blind to file
  changes — diff inside the submodule. And always verify the actual artifact
  (run the shipped binary), never the wrapper exit code or the "done" notification.
