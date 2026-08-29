---
trdd-id: K3PW7NQ2
title: PSS suggests elements from DISABLED plugins - enablement read at index time from user scope only
column: todo
created: 2026-08-29T16:53:00+0200
updated: 2026-08-29T16:53:00+0200
current-owner: perfect-skill-suggester
task-type: bugfix
min-approval-requirement: none
priority: high
scope: project
labels: [indexing, suggestions, settings-precedence, r17-24]
relevant-rules: []
external-refs: [ai-maestro TRDD-BD8OS8U7, ai-maestro docs/GOVERNANCE-RULES.md R17.24]
---

# PSS suggests elements from DISABLED plugins

PSS suggests agents and skills belonging to plugins the user has **disabled**. The harness does
not load a disabled plugin, so naming one of its elements is unactionable — the same class of
defect as the cross-project leak fixed in v3.14.2, on a different axis.

## Verified facts (first-hand, 2026-08-29)

- `scripts/pss_discover.py:283` `_load_inactive_plugin_ids()` reads
  `get_claude_dir() / "settings.json"` — i.e. **`~/.claude/settings.json` only** (`:84-86`
  confirms `get_claude_dir()` is `~/.claude`). It never reads any
  `.claude/settings.local.json`.
- **It is opt-in and OFF by default.** `pss_reindex.py:172`
  `exclude_inactive_plugins: bool = False`, and `:204` only appends
  `--exclude-inactive-plugins` when true. So a normal reindex indexes disabled plugins.
- **Measured on this machine: 38 of 76 entries in `enabledPlugins` are `false`.**
- **Observed live, in-session:** PSS suggested `agents-quality-security:code-reviewer`,
  `agents-infrastructure-operations:devops-troubleshooter` and
  `agents-language-specialists:rust-expert`. All three plugins read `false` in
  `~/.claude/settings.json`.
- The read happens at **index-build** time, so even a correct read would go stale the moment a
  user toggles a plugin — no reindex, no change in suggestions.

## Not fixed by v3.14.2/3

The cross-project filter keys on an element's **origin project**.
`is_foreign_project_element` returns `false` for any `plugin:` source, by design. Plugin
enablement is an orthogonal axis and is entirely unhandled.

## The AI Maestro half (R17.24) — the stricter requirement

`R17.24` (ai-maestro `docs/GOVERNANCE-RULES.md:699`, a table ROW, which is why a heading
search misses it; that R-series runs to R52 and is NOT the janitor's `~/.claude/rules/` set —
searching the latter for it can only ever return zero) whitelists which plugins an agent may
use. The harness enforces it by writing `"<plugin>": false` into **that agent's own**
`.claude/settings.local.json` at wake — a local `false` overriding the user-scope `true`
for that process alone. It never writes `~/.claude/settings.json`.

A consumer contract appended to that row on 2026-08-28 (ai-maestro TRDD-BD8OS8U7) binds PSS
directly: any tool enumerating the plugins enabled FOR AN AGENT MUST read that agent's
`.claude/settings.local.json` at **USE** time, honouring Claude Code precedence (local beats
user) — never only `~/.claude/settings.json`, never at index-build time alone. The row cites
this by name: "perfect-skill-suggester's index-time filter suggested elements from
R17.24-disabled plugins".

So there are two defects, and the narrow one does not subsume the broad one:
1. **Enablement is ignored by default at all** (the 38 above) — pure PSS bug, bites every user.
2. **Precedence + timing** — local-over-user, read at use time (what R17.24 requires).

## Acceptance criteria

- [ ] An element whose plugin is `false` in the effective settings is never suggested.
- [ ] Effective enablement = Claude Code precedence, **local beats user**: the agent's
      `.claude/settings.local.json` overrides `~/.claude/settings.json` per plugin key.
- [ ] Enablement is evaluated at **USE** time (suggest time), not only at index-build — toggling
      a plugin changes suggestions with **no reindex**.
- [ ] Verified against the live disabled set on this machine: the three agents named above stop
      being suggested, and enabled-plugin agents still are.
- [ ] Absent/unreadable settings degrade like the v3.14.3 `cwd` guard — an undecidable
      GLOBAL basis disables the filter rather than emptying a scope class. (One element's
      unknown may fail closed; a missing basis must not.)
- [ ] A test that actually exercises a disabled-plugin source — note `pss_test_e2e.py`
      fixtures use `source: "test"` and cannot reach this path, so it will not catch it.

## Provenance

Surfaced while closing TRDD-3JYVXDZG. The long-carried "R17.24 suggest-time gap" handoff item
was initially closed as an unresolvable citation on the grounds of a repo-wide grep returning
zero — **wrong grounds**: R17.24 is in ai-maestro's numbering, so the PSS repo could never have
held it. Corrected after asking the ai-maestro session, which supplied the location and warned
that v3.14.2 filters a different axis. That warning is what turned a closed item back into this
card.
