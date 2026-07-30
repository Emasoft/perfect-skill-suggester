---
trdd-id: XUD7YUZH
title: Modularize main.rs — function-module split (steps M1-M14, deferred remainder)
column: backburner
created: 2026-07-24T16:13:50+0200
updated: 2026-07-24T16:13:50+0200
current-owner: perfect-skill-suggester
task-type: refactor
scope: project
---

## ⏵ STATE — READ THIS FIRST ON RESUME (authoritative; supersedes the body) — 2026-07-24

**What this is:** split the 23k-line `rust/skill-suggester/src/main.rs` into per-concern
modules. The full 18-step plan (banner-to-banner cuts + root-glob re-export mechanism +
per-step green gate) is the committed report:
`reports/pss-improve-mainrs-plan/20260723_141326+0200-mainrs-modularization-plan.md` — READ IT.

**DONE (do NOT redo):**
- The **static-data extraction landed and is GREEN** — `rust/skill-suggester/src/data.rs`
  (1,186 LOC) holds TYPO_CORRECTIONS / ABBREVIATIONS / DOMAIN_TAXONOMY / TASK_SEPARATORS /
  synonym regexes / ActivityDef+ACTIVITY_REGISTRY as `pub(crate)`, wired via
  `mod data; pub(crate) use data::*;` in main.rs.
- Gate at time of writing: `cargo check -p perfect-skill-suggester --all-targets` = 0 own-crate
  warnings; `cargo test -p perfect-skill-suggester` = **223 passed**. main.rs 23,102 → 21,971.
- **⚠ This increment is UNCOMMITTED in the `rust/` submodule** (as of 2026-07-24). It must be
  committed FIRST (it is the revert substrate) — but commits in this project go through
  `publish.py` / require the owner's go (never raw `git commit`; see the release rule).

**DEVIATION from the plan:** the executed step bundled ALL static data into ONE `data.rs`, NOT
the plan's granular per-concern files (taxonomy.rs / abbreviations.rs / activities.rs / text.rs
statics) and did NOT move `tests` first. So plan step numbers 1-4 are effectively collapsed into
"data.rs done"; the plan's absolute LINE NUMBERS are now STALE — but every cut is
**banner-anchored**, so re-locate ranges by banner text, not line number, at resume.

**NEXT ACTION (the remaining work):** extract the FUNCTION modules — cli.rs, consts.rs/types.rs,
project_scan.rs, text.rs, synonyms.rs (2,445 LOC), domain_gates.rs, matching.rs, loading.rs,
agent_profile.rs, enrich.rs, db.rs, query.rs, datetime.rs/admin_cmds.rs, hook.rs, and the tests
module. Plan flags steps 11/16/17/18 as HIGH-RISK (>1,800-line cuts).

**HOW to resume (advisor-ratified execution, Fable 5, 2026-07-24):**
1. Commit `data.rs` first (submodule) as the per-step revert substrate.
2. SEQUENTIAL `sonnet[1m]` lean-workers, one module per turn; each worker Reads ONLY its
   banner-anchored range (offset/limit) — **NEVER the whole main.rs** (that was the prior
   attempt's window-burn cause: whole-file into every agent context).
3. Per step: create module + `mod x; pub(crate) use x::*;` + delete range → GREEN GATE
   (0 own warnings, 223 tests) → **commit the step** → next. Red step → revert THAT step only.
4. Re-verify baseline (test count + banner map) before starting — drift is expected.

**SUPERSEDED — do NOT carry forward:**
- The Opus fan-out ultracode workflow approach (read whole main.rs into every subagent) — it
  drove the 5h token window to 86% at 10% elapsed and was killed. Do NOT relaunch it.
- The plan's exact line numbers (stale post-data.rs). Banners are the anchors.

**Non-goals (from the plan, still binding):** behavior-neutral only — no symbol renames, no
signature changes, no `expand_synonyms` if-chain→table conversion, no `temporal.rs` edits (the
re-export design exists so it needs zero edits), no VERSION/Cargo/plugin.json/pyproject bump.

## Why deferred (advisor verdict B, 2026-07-24)

The refactor is **navigability-only** — plan §9 concedes the coupling graph does not improve
until a later de-globbing pass, so it ships zero user value. The remaining cuts include four
>1,800-line high-risk steps and one prior blown attempt. Meanwhile commit `fb73c4a` (publish-gate
fix, agent slimming, CPV cleanup, CI accuracy gate, +206 tests) — real user value — sits unpushed.
Shipping wins on any priority calculus; the split is parked here as a tracked, resumable card so
"later never comes" cannot silently happen. Early pull-forward signal: the next real bugfix inside
main.rs is measurably slowed by the file's size.

## Links
- Plan (committed): `reports/pss-improve-mainrs-plan/20260723_141326+0200-mainrs-modularization-plan.md`
- Proven-green increment: `rust/skill-suggester/src/data.rs` + main.rs `mod data;` re-export.
