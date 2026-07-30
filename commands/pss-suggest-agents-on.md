---
name: pss-suggest-agents-on
description: "Suggest AGENTS on every prompt (default mode); turns skill suggestions off"
effort: low
allowed-tools: ["Bash"]
---

# Suggest agents

Switch PSS to **agent** suggestions. This is the default mode.

Agents are suggested instead of skills because a skill corpus has grown too
large and too specialized for any scorer to pick from reliably, while an agent
declares the skills it needs in its own frontmatter — the harness preloads
them into the agent's context automatically. In practice Claude also acts on a
suggested agent far more often than on a suggested skill.

The two content modes are **mutually exclusive**: turning agents on turns skill
suggestions off. There is one setting, not two toggles.

## Run

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-.}"
PSS_BIN="${PLUGIN_ROOT}/bin/pss-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
[ -x "$PSS_BIN" ] || PSS_BIN="${PLUGIN_ROOT}/rust/target/release/pss"
"$PSS_BIN" suggest-mode --set agents
```

Prints `{"mode":"agents","path":"<state file>"}`. Report the mode to the user in
one line. A non-zero exit means the setting was NOT persisted — surface the
error rather than reporting success, or the user will believe they switched
modes while every later prompt keeps the old behavior.

Takes effect on the next prompt; no restart or reindex needed.

## Related

- `/pss-suggest-agents-off` — silence suggestions entirely
- `/pss-suggest-skills-on` — switch back to skill suggestions
- `/pss-suggest-skills-off` — silence suggestions entirely
