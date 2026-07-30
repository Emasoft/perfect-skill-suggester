---
name: pss-suggest-skills-on
description: "Suggest SKILLS on every prompt; turns agent suggestions off"
effort: low
allowed-tools: ["Bash"]
---

# Suggest skills

Switch PSS to **skill** suggestions — the pre-v3.11 behavior. Off by default.

The two content modes are **mutually exclusive**: turning skills on turns agent
suggestions off. There is one setting, not two toggles.

Prefer agents unless you specifically want skills: skills have become numerous
and narrowly specialized, which makes algorithmic selection unreliable, whereas
an agent carries its own skill set in frontmatter.

## Run

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-.}"
PSS_BIN="${PLUGIN_ROOT}/bin/pss-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
[ -x "$PSS_BIN" ] || PSS_BIN="${PLUGIN_ROOT}/rust/target/release/pss"
"$PSS_BIN" suggest-mode --set skills
```

Prints `{"mode":"skills","path":"<state file>"}`. A non-zero exit means the
setting was NOT persisted — surface the error instead of reporting success.

Takes effect on the next prompt; no restart or reindex needed.

## Related

- `/pss-suggest-skills-off` — silence suggestions entirely
- `/pss-suggest-agents-on` — switch to agent suggestions (the default)
