---
name: pss-make-agent
description: "Generate an ALL-IN-ONE, ONE-FOR-ALL or PLUGIN-OMNI agent"
argument-hint: "\"<specialization>\" --type=<normal|allin1|1xall|omni> [--no-mcp] [--model M] [--effort E]"
effort: medium
allowed-tools: ["Bash", "Read", "Write", "Glob", "Grep"]
---

# PSS Make Agent Command

Generate a Claude Code subagent of one of three archetypes. Skills are referenced
**by bare name and stay standalone files** — nothing is ever copied into the agent,
so a skill can still be shared, edited and updated in one place.

## The three archetypes

| kind | frontmatter `skills:` | where a skill executes |
|---|---|---|
| `all-in-one` | every step skill + `verification-before-completion` | inline, in this same agent |
| `one-for-all` | the generated step MENU + verification | one skill per subagent |
| `plugin-omni` | exactly one — the plugin's skills menu | via the Skill tool, on demand |

Pick `all-in-one` when the steps are few and share state. Pick `one-for-all` when
the steps are independent and you want each to run in a fresh context. Pick
`plugin-omni` when there is no fixed procedure at all — just a body of skills the
agent should choose among.

## Usage

Describe the specialization and PSS picks the skills:

```bash
pss make-agent "audit Rust for memory safety and unsafe blocks" --type=normal --no-mcp
pss make-agent ./agent-spec.md --type=allin1 --model=opus --effort=high
pss make-agent "review React components" --type=1xall --top 6 --output ./out
pss make-agent "orchestrate everything" --type=omni --plugin some-plugin --output ./out
```

The description may be prose **or a path to a `.md` file** (the plugin
generator's format — a `name:` in its frontmatter becomes the agent's name).
`plugin-omni` ignores it for selection and takes every skill of `--plugin`.

| flag | meaning |
|---|---|
| *(positional)* | the specialization — free text or a path to a `.md` file |
| `--type` / `--kind` | `normal` \| `all-in-one` \| `one-for-all` \| `plugin-omni` (aliases `allin1`, `1xall`, `omni`, `aio`, `ofa`) |
| `--name` | agent name; derived from the description if omitted |
| `--skills a,b,c` | pick these explicitly, overriding description-based selection |
| `--plugin P` | every skill in plugin `P` (the usual `plugin-omni` input) |
| `--top N` | ceiling on description-selected skills (default 8) |
| `--no-mcp` | give the agent no MCP servers |
| `--no-skill` | give the agent no skills |
| `--no-agent` | do not point it at complementary agents |
| `--model` / `--effort` | `model:` and `effort:` pins |
| `--summary` | explicit one-line `description:` (alias `--description`) |
| `--output DIR` | output root (default `.`) |
| `--dry-run` | print what would be written, touch nothing |
| `--explore` | route read-only `one-for-all` steps through the built-in `Explore` |
| `--format json` | machine-readable result |

### `normal` — the fourth type

A plain subagent: skills preloaded, no menu, no router, no micro-agent. Use it
when the work does not need an orchestration shape and you just want the right
skills on a well-described agent.

### What `--no-mcp` actually does

Every emitted agent carries an explicit `tools:` list, and that **allowlist** is
what keeps MCP tool schemas out of its context — measured, a custom agent with
four tools costs ~68.5k against the built-in Explore's ~67k *with* ~90 MCP tools
loaded. `--no-mcp` additionally suppresses the `mcpServers:` declaration, so the
agent is guaranteed no MCP surface at all. (A plugin-shipped agent may not
declare `mcpServers` regardless — `pss_validate_agent_md.py --plugin` enforces
that.)

### Review what it picked

Selection reuses PSS's own scorer — the same one the suggestion hook runs, so
there is one implementation of "which skills match this text". It inherits that
scorer's precision: on a benchmarked sample, 39–47% of hook suggestions were
rated irrelevant, and word collisions do get through (a "Rust **memory** safety"
description will surface a long-term-`memory` skill). Duplicates are removed and
low-confidence matches dropped, but **read the emitted `skills:` list and prune
it**, or pass `--skills` when you already know what you want.

## What it writes

```
<out>/agents/<name>.md                            the orchestrator
<out>/agents/<name>-micro.md                      one-for-all, when any step writes files
<out>/skills/<name>-step-menu/SKILL.md            one-for-all
<out>/skills/<plugin>-the-skills-menu/SKILL.md    plugin-omni
<out>/pss-agent-deps.json                         every referenced skill + its source path
```

Every file is written atomically, and the whole set is checked for collisions
before any of it lands — a half-written bundle would look valid while naming a
skill that was never emitted.

## Preloading is not access

`skills:` in agent frontmatter **preloads the full skill body at startup**. That is
the point for `all-in-one` (those skills run in that same context) and wrong for
`one-for-all`, where a preloaded step body would be paid on every router turn *and*
again inside the subagent that runs it. An agent can always invoke any skill with
the Skill tool without preloading it.

A skill that cannot be preloaded — `disable-model-invocation: true`, or a bundled
user-only skill — is reported as a warning and left out. Claude Code itself skips a
missing preloaded skill **silently**, with only a debug-log line, so the gate exists
to make that failure visible.

## `--explore` is off by default, and the reason is measured

Two probes, same model, same prompt, zero tool calls each:

| environment | project CLAUDE.md | `~/.claude/rules/*` | tokens |
|---|---|---|---|
| built-in `Explore` | absent | loaded | 66,954 |
| a custom minimal agent | loaded | loaded | 68,563 |

Explore saves ~1.6k, not the ~54k the CLAUDE.md hierarchy suggests — it skips only
the *project* CLAUDE.md, while the rules files load in both. Against 2%, a second
environment is not worth reasoning about, and `Explore` cannot write files at all.
So every step goes to one shared micro-agent unless you pass `--explore`.

The printed cost table shows this per step.

## Verify the result

```bash
uv run scripts/pss_validate_agent_md.py <out>/agents/<name>.md --check-index
```

Then, in a session where the agent is installed, `/context` shows which skills
actually preloaded and from which source — the ground truth the cost table predicts.

## See also

- `skills/pss-agent-archetypes/SKILL.md` — choosing between the three, and the
  `fork` terminology trap.
- `/pss-setup-agent` — profile an existing agent into `.agent.toml` instead.
- `/pss-make-plugin-from-profile` — turn a profile into an installable plugin.
