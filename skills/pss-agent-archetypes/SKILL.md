---
name: pss-agent-archetypes
description: "Use when creating an agent that orchestrates several skills, choosing between ALL-IN-ONE, ONE-FOR-ALL and PLUGIN-OMNI, or deciding whether to preload skills into an agent's frontmatter. Covers the preload-vs-access distinction and the `fork` terminology trap. Trigger with /pss-make-agent."
allowed-tools: ["Bash", "Read", "Write", "Glob", "Grep"]
---

# PSS Agent Archetypes

Three shapes for an agent that orchestrates several skills. They differ in one
axis only: **where a skill actually executes.**

| kind | frontmatter `skills:` | a skill runs… | pick it when |
|---|---|---|---|
| **ALL-IN-ONE** | every step + `verification-before-completion` | inline, same agent | few steps that share state |
| **ONE-FOR-ALL** | the step MENU + verification | one skill per subagent | independent steps, each wanting a fresh context |
| **PLUGIN-OMNI** | exactly one — the plugin's skills menu | via the Skill tool, on demand | no fixed procedure; a body of skills to choose among |

Generate any of them with `/pss-make-agent`.

## The rule that governs all three: never inline a skill

An agent references a skill **by bare name**. It never contains a copy of the
skill's text. This is not a style preference — an inlined skill is a fork that
stops receiving updates, and every agent that inlined it has to be found and
edited by hand when the skill changes.

Copying a skill *file* into a generated plugin for portability is fine: the skill
is still a skill, still standalone, still updated in one place.

## Preloading is not access

`skills:` in agent frontmatter **preloads the full skill body at startup**. This
is easy to get backwards, so it is worth stating plainly:

- An agent can invoke **any** skill with the Skill tool **without** listing it.
  `skills:` does not grant access; it decides what is *already in context* on
  turn one.
- Preloading N skills costs N full bodies on **every** turn of that agent.

Verified empirically: a subagent that preloads two skills was asked a question
under a zero-tool-call constraint. It quoted one skill's `## Critical Rules`
section byte-for-byte with `tool_uses: 0`. A four-line answer with no tool calls
cost 132k tokens.

So: preload when the skills run in **that** context (ALL-IN-ONE). Do not preload
step bodies into a router (ONE-FOR-ALL) — they would be paid on every router turn
*and* again inside the subagent that actually runs them, making the "cheaper"
archetype the more expensive one.

## What cannot be preloaded

- A skill with `disable-model-invocation: true` (user-only).
- The bundled user-only skills (`/verify`, `/code-review`).
- Anything whose name does not resolve.

**A missing preloaded skill is skipped SILENTLY** — only a debug-log line marks
it. That is why `/pss-make-agent` gates every name up front and reports a
warning: the alternative is an agent that quietly lost a capability.

Confirm what actually loaded with `/context` (it shows each preloaded skill and
its source) and `/skills` (a "user-only" badge means it can never be preloaded).

## The `fork` trap

`fork` means two different things one word apart:

| where | what it does |
|---|---|
| **agent**-level "fork the conversation" | the subagent **inherits** the parent's full conversation |
| **skill**-level `context: fork` | runs isolated, **no** conversation history |

Reaching for an agent-level fork to "keep it small" does the opposite. If you
want a small subagent, launch a fresh one and pass what it needs in the prompt.

## Choosing the step environment (ONE-FOR-ALL)

Every step runs in one shared minimal micro-agent by default. `--explore` routes
read-only steps through the built-in `Explore` instead. Measured — two probes,
same model, same prompt, zero tool calls each:

| environment | project CLAUDE.md | `~/.claude/rules/*` | tokens |
|---|---|---|---|
| built-in `Explore` | absent | loaded | 66,954 |
| a custom minimal agent | loaded | loaded | 68,563 |

Explore saves **~1.6k, not ~54k**: it skips only the *project* CLAUDE.md, while
the rules files — the bulk of that number — load in both. It also cannot write
files at all (its system prompt forbids creating them, including under `/tmp`;
that is not a tool gap a launching prompt can override). One environment for
every step is simpler and within noise.

When quoting any subagent's context cost, measure the **differential between the
candidates at equal tool counts**. Do not subtract a hierarchy size you have not
confirmed is skipped.

## Verify what you generated

```bash
uv run scripts/pss_validate_agent_md.py <out>/agents/<name>.md --check-index
```

Then **read the generated file**. For a generator, a green test suite is not
evidence: two real bugs shipped past a full green suite here — a literal `{}`
placeholder that told a router to consult a nonexistent skill, and report-path
instructions emitted for skills that run inline with no subagent to carry them
out. Both were found only by opening the output.

## Checklist

Copy this and track your progress:

- [ ] Pick the archetype from where the skills must execute (inline / per-subagent / on demand)
- [ ] List the skills; confirm none is user-only (`disable-model-invocation: true`)
- [ ] Generate with `/pss-make-agent`
- [ ] Read the warnings — a rejected skill was left out on purpose
- [ ] Validate: `uv run scripts/pss_validate_agent_md.py <out>/agents/<name>.md --check-index`
- [ ] **Open and read the generated files**, not just the test result
- [ ] Confirm `/context` in a live session matches the printed cost table

## Reference

- [archetype-anatomy.md](references/archetype-anatomy.md) — the emitted files and
  frontmatter of each archetype, field by field.
  - The three archetypes, side by side
  - ALL-IN-ONE: the orchestrator
  - ONE-FOR-ALL: router, menu skill, micro-agent
  - PLUGIN-OMNI: menu and inlined verification
  - `pss-agent-deps.json`
  - Plugin-shipped restrictions
