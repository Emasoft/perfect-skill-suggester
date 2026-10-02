---
trdd-id: K3PW7NQ2
title: PSS suggests elements from DISABLED plugins - enablement read at index time from user scope only
column: complete
created: 2026-08-29T16:53:00+0200
updated: 2026-08-30T01:05:00+0200
implementation-commits: [40499b5, 812f280]
released-in: v3.15.0
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

- [x] An element whose plugin is `false` in the effective settings is never suggested.
- [x] Effective enablement = Claude Code precedence, **local beats user**: the agent's
      `.claude/settings.local.json` overrides `~/.claude/settings.json` per plugin key.
- [x] Enablement is evaluated at **USE** time (suggest time), not only at index-build — toggling
      a plugin changes suggestions with **no reindex**.
- [x] Verified against the live disabled set on this machine: the three agents named above stop
      being suggested, and enabled-plugin agents still are.
- [x] Absent/unreadable settings degrade like the v3.14.3 `cwd` guard — an undecidable
      GLOBAL basis disables the filter rather than emptying a scope class. (One element's
      unknown may fail closed; a missing basis must not.)
- [x] A test that actually exercises a disabled-plugin source — note `pss_test_e2e.py`
      fixtures use `source: "test"` and cannot reach this path, so it will not catch it.

## Implementation (2026-08-29, commit `40499b5` in the `rust` submodule)

Fixed in the Rust suggestion hot path, not in discovery — that is what makes it USE-time.
`candidate_is_invocable_here` gains a fourth exclusion class; `disabled_plugin_keys(cwd)` is
computed once per prompt from the live settings files.

**Measured blast radius before the fix: 432 suggestable entries across 30 disabled plugins.**
(`all-skills@buildwithclaude` 110, `axiom@axiom-marketplace` 91, `agents-specialized-domains`
41, …)

Three findings that changed the design, each verified first-hand against the live index:

1. **The key must be built from `source`, never from the `plugin`/`origin` columns.**
   `plugin` is `None` for a large share of real rows (every `plugin:ai-maestro-plugins/*` bar
   two), and `origin` holds the marketplace's REPO OWNER (`github.com/davepoon`), not its local
   name (`buildwithclaude`). Keying on either yields
   `agents-language-specialists@github.com/davepoon`, which matches nothing — the filter would
   have read as a clean no-op. Only `source` (`plugin:<marketplace>/<plugin-name>`) carries both
   halves, spelled in the opposite order to the settings key `<plugin-name>@<marketplace>`.
2. **Precedence must resolve on the VALUE, not on presence.** ai-maestro confirmed the harness
   writes BOTH polarities (`~/agents/frank/.claude/settings.local.json`: 37 entries, mixed).
   Collecting each layer's `false` keys and unioning them passes a naive test and is still
   wrong — it can never let a higher layer RE-ENABLE what a lower one disabled.
3. **`marketplace:` rows were already dropped** by the first exclusion class, so this is
   entirely about the 1220 installed `plugin:` rows. `project:<slug>/plugin:<name>` is
   deliberately unhandled: a project-local plugin has no marketplace, so no key can exist.

Live verification, no reindex between runs, prompt *"write idiomatic rust code with ownership
and lifetimes, review it for security"*:

| cwd / settings | suggested |
|---|---|
| before the fix | `agents-quality-security:code-reviewer`, `claude-code-settings:pr-reviewer`, `agents-language-specialists:rust-expert` — all three plugins `false` |
| after | only `ai-maestro-janitor:*`, `claude-plugins-validation:*` — both `true` |
| local `ai-maestro-janitor…: false` | janitor agent gone, others stand |
| local `agents-language-specialists…: true` | `rust-expert` returns, overriding the user-scope `false` |
| **project** `agents-language-specialists…: true`, no local file | `rust-expert` returns — the middle layer is live |
| project `…: true` + local `…: false` | `rust-expert` gone — local beats project |
| **isolation run:** new binary, local layer re-enables ALL 76 keys | reproduces the pre-fix output **byte-identically**, same four agents at the same scores (1.00 / 0.87 / 0.51 / 0.60) |

**Attribution, stated precisely.** The plain before/after diff does NOT isolate this edit: the
shipped `bin/pss-darwin-arm64` is v3.14.5, while the submodule HEAD built from already carried
the unreleased `~/.claude`-is-user-scope + canonicalize-before-walk fix, which rewrites
`owning_project_root` and therefore the cross-project filter. Two changes, one diff. What
isolates it is the **settings-only runs against one fixed binary** — and decisively the last
row: with every key re-enabled the new binary is byte-identical to the old, so the entire
observed difference is this filter and nothing else, including no effect on scores.

**Untested wiring, named rather than implied.** `merge_enablement_layers` is tested over layer
TEXTS, and all three layers are exercised live above — but the six lines inside
`disabled_plugin_keys` that ASSEMBLE the three paths in low-to-high order have no unit test of
their own. Same class of boundary the retain call's own comment already admits: literal, low
risk, and still untested.

Four unit tests added (314 pass, was 310), covering key derivation, value-precedence in both
directions, every fail-open shape, and the composed retain predicate on a real `plugin:` source.

**Left alone deliberately:** `pss_discover.py --exclude-inactive-plugins` still exists and still
defaults OFF. It is now redundant for correctness — the hot path decides — but it remains a
legitimate way to shrink the index, and removing it is not this card's scope.

## Consulted

- **ai-maestro session** (SendMessage, 2026-08-29): confirmed the settings.local.json path is
  resolvable from cwd with no registry lookup, that keys are `name@marketplace`, that
  `permissions` / `crossSessionInbound` are unrelated siblings, and ratified fail-open as the
  contract. **Corrected one of my assumptions**: the harness writes `true` as well as `false`,
  which is what forced finding 2 above.
- **Fable advisor: NOT consulted — unavailable.** `agentlenspro model-headroom fable` reported
  the Fable weekly window at 100% (exit 1), so per the advisor rule no verdict was obtained.

## Provenance

Surfaced while closing TRDD-3JYVXDZG. The long-carried "R17.24 suggest-time gap" handoff item
was initially closed as an unresolvable citation on the grounds of a repo-wide grep returning
zero — **wrong grounds**: R17.24 is in ai-maestro's numbering, so the PSS repo could never have
held it. Corrected after asking the ai-maestro session, which supplied the location and warned
that v3.14.2 filters a different axis. That warning is what turned a closed item back into this
card.
