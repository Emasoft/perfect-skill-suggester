---
trdd-id: LIFE12FU
title: v3.9 design — per-project enablement history (P-8) + MCP surface (P-9), issue #12
column: design
created: 2026-06-25T19:18:33+0200
updated: 2026-06-25T19:18:33+0200
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

**NEXT ACTION:** get user decisions on the **Open design questions** (Q1–Q4),
then implement the approved subset (likely P-9 MCP first — it's unblocked — and a
reframed P-8 keyed to whatever per-project signal is real).

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

## Notes and lessons learned

[^1]: [ocd:2026-06-25 lmd:2026-06-25] Designing P-8 surfaced that "per-project
  plugin enablement" has NO data source in Claude Code (plugin enablement is
  global; only MCP-server enablement is per-project — 184/184 projects confirmed).
  Lesson: before building a feature to "record X per-project over time", VERIFY the
  upstream actually exposes X per-project — here the literal ask was infeasible and
  the real signal (MCP enablement) is a different element type. This is exactly why
  the user's "design-first" choice was correct.
