---
trdd-id: LIFE12FU
title: v3.9 design — per-project enablement history (P-8) + MCP surface (P-9), issue #12
column: design
created: 2026-06-25T19:18:33+0200
updated: 2026-07-02T17:59:47+0200
current-owner: pss-main-session
task-type: feature
release-via: publish
relevant-rules: []
external-refs: ["github.com/Emasoft/perfect-skill-suggester/issues/12"]
parent-trdd: TRDD-LIFEV38X
test-requirements: [unit, integration, lint, typecheck]
impacts: [public-api, migration, config-schema]
migration-direction: forward
---

# TRDD-LIFE12FU — v3.9 design: per-project enablement history (P-8) + MCP surface (P-9)

## ⏵ STATE — READ THIS FIRST ON RESUME (authoritative) — 2026-06-25

**What this is:** the DESIGN doc for GitHub issue #12 (the two parts split out of
#10/v3.8.1). The user chose "Start #12, **design-first**" — so this TRDD is the
plan to be APPROVED before any implementation. **No code has been written.**

**THE finding that reshapes P-8 (verified on this machine):** Claude Code stores
**plugin** enablement (`enabledPlugins`) **GLOBALLY**, not per-project — 184/184
`~/.claude.json` project entries carry **no** `enabledPlugins` key. What varies
per-project is **MCP-server** enablement (`enabledMcpjsonServers` /
`disabledMcpjsonServers`). So "which **plugins** were enabled **in folder X** at
past T" (P-8 as literally worded) has **no observable data source** for plugins.
This is the central open question below — it must be resolved before building P-8.

**NEXT ACTION — APPROVED 2026-06-25 (path: "P-9 now; P-8 = MCP+flag"):** build &
ship the P-9 MCP server first (v3.9.0); then reframe P-8 to record per-project
**MCP-server** enablement history (schema S1 — reuse `scope_path` + an
Enabled/Disabled event_type) and report **plugin** enablement as GLOBAL with an
explicit `enablement_is_global_fallback` flag. Defaults taken: Q2=S1, Q3=Python
stdio wrapper, Q4=P-9 first. **The changelog detour LANDED** (v3.8.2 compat +
v3.8.3 cli_version fix, both shipped+verified). **P-9 build IN PROGRESS** —
delegated to a kraken (TDD) agent: `scripts/pss_mcp_server.py` (FastMCP stdio,
6 read-verb tools shelling to the binary), `tests/unit/test_pss_mcp_server.py`
(real binary, no mocks), `docs/PSS-MCP-SERVER.md` (opt-in `.mcp.json`). Files left
uncommitted for orchestrator review; the **release (v3.9.0) is held for the user's
explicit nod** (new public MCP surface = the one irreversible step).

**UPDATE 2026-07-02 (resume):** P-9 is now COMMITTED locally + reviewed —
`64acde1` (server) + `26c3937` (UTF-8 `_run_pss_json` fix from a `/code-review
xhigh`); 14/14 real-binary tests pass, ruff clean; **still unpushed / v3.9.0 still
held for an explicit "ship".** P-8 DESIGN is now FIRMED to implementation-ready
(section "P-8 — FIRMED design" below): Q1→P-8a+P-8b, Q2→S1, Q3→Python(done),
Q4→P-9-first(done). P-8 IMPLEMENTATION stays gated on (a) P-9 shipped and (b)
consumer confirms Q1/P-8c — do NOT start coding P-8 before both.

## Grounded current state (verified in code this session)

- **Schema** (`temporal.rs` ~L296): `events { event_id => observed_at, scan_id,
  event_type, element_type, element_name, element_id, scope, scope_path, source,
  path, content_hash, file_size, token_count, enabled:Bool=true, override_status,
  diff_json, snapshot_ref }`; `elements_state { element_id => …, enabled:Bool=true,
  override_status, installed_at, last_changed_at, exists }`.
- **`element_id` already embeds scope_path** (`<type>:<name>@<scope>:<scope_path_slug>`,
  `temporal.rs` ~L153). For project/local elements scope_path is the folder; for
  **plugin/marketplace/user elements scope_path is `""`** (global) with a single
  global `enabled`.
- **`pss_discover._load_inactive_plugins`** reads `enabledPlugins` from the **global**
  `~/.claude/settings.json` ONLY. There is no per-project plugin-enablement read.
- **`active-in` clause (c)** ("plugin/marketplace currently enabled") uses the
  **current global** `elements_state.enabled` — not per-project, not historical.
  That is the P-8 gap.
- **`~/.claude.json` projects[*]** carry `enabledMcpjsonServers` / `disabledMcpjsonServers`
  (per-project MCP enablement) but NOT `enabledPlugins`.

## P-8 — the reframe (resolve Q1 before building)

Because per-project PLUGIN enablement isn't observable, P-8 splits into options:

- **P-8a — per-project MCP-server enablement (REAL, observable).** Read each
  project's `enabledMcpjsonServers`/`disabledMcpjsonServers` from `~/.claude.json`;
  emit per-(mcp-element, project) enablement events; `active-in` resolves MCP
  enablement at T from that history. This is genuinely per-project and historical.
- **P-8b — global plugin-enablement HISTORY (already mostly there).** Keep recording
  the global `enabled` flag over time (the existing `enabled` column already does
  this); `active-in` reports plugin enablement as the GLOBAL state at T, flagged
  `enablement_is_global: true`. No per-project fidelity is possible for plugins
  because the data doesn't exist.
- **P-8c — confirm the real consumer need.** AI Maestro's "active in folder X at T"
  may be fully satisfied by v3.8.1's `active-in` union + P-8b's global-history flag;
  the per-project-plugin nuance may be moot. Cheapest correct outcome if so.

**Recommended:** P-8a (MCP per-project, the only genuinely per-project signal) +
P-8b (global plugin history with an honest flag), and confirm via P-8c that this
meets the consumer's need. Do NOT fabricate per-project plugin enablement.

### Schema sub-design (for whatever per-project enablement we DO record)

- **Option S1 — reuse `scope_path`.** Emit enablement events with `scope_path` = the
  project path and a dedicated `event_type` (Enabled/Disabled) so the existing
  temporal machinery (element_id keyed by scope_path, `as-of`) handles per-project
  history for free. Pros: minimal new surface, reuses indexes. Cons: must not
  duplicate CONTENT observations — enablement events carry no content_hash churn.
- **Option S2 — new `enablement_events` table** keyed by `(element_id_global,
  project_slug, enabled, ts)`. Pros: clean separation from content events. Cons:
  new table + a second query path in `active-in`.
- **Recommended:** S1 (reuse scope_path + a distinct event_type) — additive, no new
  table, and `as-of`/`active-in` already understand scope_path.

**Migration:** additive only (new event_type or column default), **forward** —
historical per-project enablement before v3.9 cannot be reconstructed; rows for
projects/instants with no recorded history set `enablement_is_global_fallback:
true`. Existing `events`/`elements_state` rows are untouched.

## P-9 — MCP server surface (unblocked; smaller)

A thin **stdio MCP server** exposing the read-only lifeline/temporal verbs
(`active-in`, `as-of`, `timeline`, `db-path`, `project-slug`) as MCP tools, each
shelling to the `pss` binary (the consumer's existing integration path) so there's
ONE source of truth and zero hot-path change. Tool schemas are versioned against
`--contract-version`. Registration is opt-in in `.mcp.json`.

- **Q3 — language:** a thin **Python** wrapper (fastmcp/stdio) calling the binary
  is fastest to ship and matches the existing Python tooling; a Rust MCP server
  would be self-contained but more surface. Recommended: Python wrapper.

## Open design questions (need user/consumer decision before building)

- **Q1 — P-8 scope:** P-8a (MCP per-project) + P-8b (global plugin history, flagged)?
  Or confirm P-8c (v3.8.1 already suffices) and drop the schema change? **(blocks P-8)**
- **Q2 — schema:** S1 (reuse scope_path + event_type) vs S2 (new table)? Recommend S1.
- **Q3 — MCP language:** Python stdio wrapper (recommended) vs Rust server?
- **Q4 — order:** ship P-9 MCP first (unblocked) while Q1 is confirmed with the
  consumer? Recommended yes.

## Phased plan (after approval)

1. **P-9 MCP** (unblocked): Python stdio server + tool schemas + tests + opt-in
   `.mcp.json` doc. Ship in a v3.9.0.
2. **P-8 (pending Q1):** if P-8a — extend `pss_discover` to read per-project
   `enabledMcpjsonServers`; add the Enabled/Disabled event emission (S1);
   `active-in` resolves MCP enablement at T; add the `enablement_is_global_fallback`
   flag for plugins. Tests + docs. Ship in a later v3.9.x.

## Acceptance criteria (from #12, adjusted by the finding)

- [ ] P-9: MCP server exposes the read verbs; schemas versioned vs contract_version;
  opt-in; hot path unchanged; tested.
- [ ] P-8 (if approved): per-project MCP enablement recorded going forward;
  `active-in --as-of T` resolves MCP enablement from that history; plugin enablement
  reported as global with an explicit fallback flag; additive forward migration;
  existing rows untouched; tested.
- [ ] Honest docs: `active-in --help` + cli-reference state exactly what is
  per-project (MCP) vs global (plugins).

## P-8 — FIRMED design (implementation-ready) — 2026-07-02

Decisions (supersede the Q1-Q4 recommendations above): **Q1 = P-8a + P-8b**
(record per-project MCP-server enablement history + report plugin enablement as
GLOBAL with an honest flag; **P-8c** = confirm with the AI-Maestro consumer that
this meets the "active in folder X at T" need — a NON-blocking follow-up, not a
design gate). **Q2 = S1** (reuse `scope_path` + a distinct `event_type`). **Q3 =
Python** (already realized by P-9). **Q4 = P-9 first** (done).

**Implementation spec (do NOT code until P-9 ships + P-8c confirmed):**

1. **Read per-project MCP enablement** — `scripts/pss_discover.py`. Add
   `_load_project_mcp_enablement() -> dict[str, dict[str, bool]]` beside the
   existing `_load_inactive_plugin_ids()` (L204) and `_extract_servers()` (L945):
   parse `~/.claude.json` `projects[<path>].enabledMcpjsonServers` (list) and
   `disabledMcpjsonServers` (list) → `{project_path: {mcp_server_name: enabled}}`.
   Absence of both keys ⇒ no per-project override recorded (fall to global).
2. **Emit enablement events (S1)** — merge/discover stage. For each
   (mcp-element, project) with a recorded override, emit an event with
   `event_type` ∈ {`EnabledInProject`, `DisabledInProject`}, `scope_path` = the
   project path, `element_type = mcp`, and NO `content_hash` churn (enablement is
   not a content observation — keep it out of the diff/size/token columns). The
   existing `element_id` scheme (`mcp:<name>@project:<slug>`) already keys these
   per-project, so `as-of` resolves them for free.
3. **`active-in` resolves MCP enablement at T** — `rust/skill-suggester/src/temporal.rs`,
   the `active-in` clause (c). For MCP elements, replace the "current global
   `elements_state.enabled`" read with the latest `EnabledInProject/DisabledInProject`
   event for that (element, project) with `observed_at <= T`; if none, fall back to
   the element's global `enabled` at T and set the row's
   `enablement_is_global_fallback: true`.
4. **Plugin fallback flag** — plugins have no per-project signal, so their
   `active-in` rows ALWAYS carry `enablement_is_global_fallback: true`. Add the
   field to the `active-in` row struct + JSON output (additive; the P-9 MCP
   `pss_active_in` tool passes it through unchanged — no server edit needed).
5. **Migration** — additive/forward only: new `event_type` values + one new
   output field with a default; existing `events`/`elements_state` rows untouched.
   Pre-v3.9 per-project MCP history is unreconstructable ⇒ those rows read
   `enablement_is_global_fallback: true` until new events accrue.

**Tests (real, no mocks):** unit — `_load_project_mcp_enablement` parses
enabled/disabled/absent from a fixture `~/.claude.json`; unit — event emission
carries `scope_path` + the new `event_type` and no content churn; integration —
`active-in <proj> --as-of T` flips an MCP server's enabled state across a recorded
Disabled event, and a plugin row always shows the global-fallback flag; `--help`
+ cli-reference state exactly what is per-project (MCP) vs global (plugins).

**Ships:** a later **v3.9.x** (after v3.9.0/P-9). Column stays `design` — design
is complete but implementation is gated; promote to `dispatch` only once P-9 has
shipped and P-8c is confirmed.

## Notes and lessons learned

[^1]: [ocd:2026-06-25 lmd:2026-06-25] Designing P-8 surfaced that "per-project
  plugin enablement" has NO data source in Claude Code (plugin enablement is
  global; only MCP-server enablement is per-project — 184/184 projects confirmed).
  Lesson: before building a feature to "record X per-project over time", VERIFY the
  upstream actually exposes X per-project — here the literal ask was infeasible and
  the real signal (MCP enablement) is a different element type. This is exactly why
  the user's "design-first" choice was correct.
