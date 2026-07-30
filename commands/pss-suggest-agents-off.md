---
name: pss-suggest-agents-off
description: "Stop suggesting agents — silences PSS prompt suggestions"
effort: low
allowed-tools: ["Bash"]
---

# Stop suggesting agents

Turn **off** agent suggestions. PSS then suggests nothing on each prompt.

`-off` means OFF, not "switch to the other mode": if you want skills instead,
run `/pss-suggest-skills-on`. Silencing is a real, supported state — the hook
still runs but emits no suggestion block.

## Run

```bash
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-.}"
PSS_BIN="${PLUGIN_ROOT}/bin/pss-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)"
[ -x "$PSS_BIN" ] || PSS_BIN="${PLUGIN_ROOT}/rust/target/release/pss"
"$PSS_BIN" suggest-mode --set none
```

Prints `{"mode":"none","path":"<state file>"}`. A non-zero exit means the
setting was NOT persisted — surface the error instead of reporting success.

Takes effect on the next prompt.

## Related

- `/pss-suggest-agents-on` — resume agent suggestions (the default)
- `/pss-suggest-skills-on` — suggest skills instead
