# Archetype anatomy

Exactly what `/pss-make-agent` emits for each kind, field by field. Read this
when you need to hand-edit a generated agent, or to write one from scratch that
matches the shape.

## Table of Contents

- [The three archetypes, side by side](#the-three-archetypes-side-by-side)
- [ALL-IN-ONE: the orchestrator](#all-in-one-the-orchestrator)
- [ONE-FOR-ALL: router, menu skill, micro-agent](#one-for-all-router-menu-skill-micro-agent)
  - [The router](#the-router)
  - [The menu skill](#the-menu-skill)
  - [The micro-agent](#the-micro-agent)
- [PLUGIN-OMNI: menu and inlined verification](#plugin-omni-menu-and-inlined-verification)
- [`pss-agent-deps.json`](#pss-agent-depsjson)
- [Plugin-shipped restrictions](#plugin-shipped-restrictions)

## The three archetypes, side by side

| | ALL-IN-ONE | ONE-FOR-ALL | PLUGIN-OMNI |
|---|---|---|---|
| `skills:` | every step + verification | menu + verification | **exactly one** (the menu) |
| `tools:` | Bash, Read, Write, Edit, Glob, Grep, Skill | Agent, Read, Bash, Skill | Bash, Read, Write, Edit, Glob, Grep, Skill |
| body | numbered procedure | decision tree of subagent launches | broad guidance + inlined verification |
| extra files | — | menu skill, micro-agent | menu skill |

The `tools:` difference is load-bearing. A ONE-FOR-ALL router does not do the work,
so it needs `Agent` and almost nothing else; giving it `Edit` invites it to skip
the subagent and do the step itself, which is the whole thing the archetype exists
to prevent.

## ALL-IN-ONE: the orchestrator

```yaml
---
name: my-agent
description: "One line."
skills:
  - step-one
  - step-two
  - verification-before-completion
tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Skill
---
```

Body: a numbered procedure, one entry per skill, each naming the skill and when
it applies. The body tells the agent the skills are **already loaded** — without
that, an agent will often re-read a skill file it already has in context.

Closing guidance matters more than it looks: *"when two steps could both apply, do
the one whose precondition is already true; when none applies, say so rather than
forcing the closest fit."* Without it an agent treats the list as a script and runs
steps that do not apply.

## ONE-FOR-ALL: router, menu skill, micro-agent

### The router

```yaml
---
name: my-router
description: "One line."
skills:
  - my-router-step-menu
  - verification-before-completion
tools:
  - Agent
  - Read
  - Bash
  - Skill
---
```

Step bodies are deliberately **absent** from `skills:`. The router needs each
step's name, when-to-use, inputs and report path — all of which the menu carries —
not the procedures themselves.

The body states the launch contract explicitly:

> Call the Agent tool with the step's environment, and a prompt of the form:
> *"Load the `<skill>` skill. Do only that step. Write your report to `<path>`.
> Reply with the path and nothing else."*

"Reply with the path and nothing else" is the part that keeps the archetype cheap.
A subagent that returns its report inline spends the router's context on something
it could have read from disk on demand.

### The menu skill

`skills/<name>-step-menu/SKILL.md` — one `##` section per step: the skill name, its
description, the agent that runs it, and its report path. **Names and when-to-use
only, never bodies.** That is what makes the menu cheap enough to preload, and it
is the same reason a skill stays a skill instead of becoming a copy inside an agent.

### The micro-agent

`agents/<name>-micro.md`, emitted **only when some step writes files**:

```yaml
---
name: my-router-micro
description: "Runs one skill and writes its report to the given path."
tools:
  - Bash
  - Read
  - Write
  - Edit
  - Skill
---
```

No `memory:`, no MCP, minimal description, near-empty body — the smallest
footprint that can still edit. One shared micro-agent serves every step; one per
step would multiply the definition without changing behavior.

## PLUGIN-OMNI: menu and inlined verification

```yaml
---
name: my-omni
description: "One line."
skills:
  - some-plugin-the-skills-menu
---
```

**Exactly one** entry. The verification rules are written into the body as prose
rather than pulled in as a second skill, because this archetype is specified to
carry one skill and no more.

That inlining is a deliberate exception to the never-inline rule, and it is the
weaker mechanism: the other two archetypes reference the real
`verification-before-completion` skill, which can be updated once for everybody.
If the one-skill constraint is ever relaxed, this should become a reference too.

The body gives **broad** guidance, not a tree: *"read the situation, pick what
fits… several skills may apply to one request, or none may; say so rather than
forcing one."*

The menu here carries no `run by:` or `report to:` lines — its skills run inline
via the Skill tool, so there is no subagent to write a report and such a line
would be an instruction with nobody to execute it.

## `pss-agent-deps.json`

```json
{
  "agent": "my-agent",
  "archetype": "all-in-one",
  "skills": [
    {"name": "step-one", "source": "/abs/path/to/SKILL.md"}
  ]
}
```

The manifest records where each referenced skill came from, so a generated bundle
can be re-resolved later against a different machine's index. The absolute source
paths live **here** and never in the agent — an agent that named a machine-specific
path would break for everyone else.

## Plugin-shipped restrictions

A plugin-shipped agent may not use `hooks`, `mcpServers` or `permissionMode` —
Claude Code drops them at load, so the same file behaves differently inside a
plugin than it does locally. Check with:

```bash
uv run scripts/pss_validate_agent_md.py agents/foo.md --plugin
```

Plugin agents reference same-plugin skills by **bare name** (verified across eight
installed plugins) — no plugin prefix, no path.
