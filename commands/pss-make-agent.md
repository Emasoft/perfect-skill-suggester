---
name: pss-make-agent
description: "Generate an ALL-IN-ONE, ONE-FOR-ALL or PLUGIN-OMNI agent"
argument-hint: "<all-in-one|one-for-all|plugin-omni> --name N [--skills a,b | --plugin P] [flags…]"
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

```bash
pss make-agent --kind all-in-one  --name my-agent --skills tdd,python-testing --output ./out
pss make-agent --kind one-for-all --name my-router --skills a,b,c --output ./out
pss make-agent --kind plugin-omni --name my-omni --plugin some-plugin --output ./out
```

| flag | meaning |
|---|---|
| `--kind` | `all-in-one` \| `one-for-all` \| `plugin-omni` (aliases: `aio`, `ofa`, `omni`) |
| `--name` | agent name; also the filename stem |
| `--skills a,b,c` | reference these skills by name |
| `--plugin P` | reference every skill in plugin `P` (the usual `plugin-omni` input) |
| `--description` | one-line agent description |
| `--model` | optional `model:` pin |
| `--output DIR` | output root (default `.`) |
| `--dry-run` | print what would be written, touch nothing |
| `--explore` | route read-only `one-for-all` steps through the built-in `Explore` |
| `--format json` | machine-readable result |

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
