---
name: pss-added-since
description: "List PSS index entries installed since a given time. Useful after /cpv-manage to verify new installs got indexed"
argument-hint: "<when> [--limit N] [--json]"
effort: low
allowed-tools: ["Bash"]
---

# PSS Added Since Command

List elements whose `first_indexed_at` timestamp is at or after a given point in time. Wraps the Rust binary's `list-added-since` subcommand (Phase D, v3.0.0+) against the canonical CozoDB store.

Typical use cases:

- "What did I install today?" — `/pss-added-since 1d`
- "What landed in the last week?" — `/pss-added-since 1w`
- "What has PSS indexed since the 10th?" — `/pss-added-since 2026-04-10`
- Verify that `/cpv-manage` or `/pss-add-to-index` actually registered a new plugin's skills.

## Usage

```
/pss-added-since <when>
/pss-added-since <when> --json
/pss-added-since <when> --limit N
```

| Argument | Description |
|----------|-------------|
| `<when>` | RFC 3339 datetime, `YYYY-MM-DD` date (midnight UTC), or a relative shorthand: `1d`, `2w`, `24h`, `30m`, `120s` |
| `--json` | Emit JSON instead of the default human-readable table |
| `--limit N` | Cap the result list at N entries (default: 50) |

## How It Works

The command runs `pss list-added-since <when>` against the CozoDB index. The Rust subcommand parses the `<when>` argument fail-fast (invalid inputs exit non-zero instead of silently falling back to "now"), converts it to an RFC 3339 UTC timestamp, then runs the equivalent of:

```
?[name, type, source, first_indexed_at, description] :=
    *skills{name, skill_type: type, source, first_indexed_at, description},
    first_indexed_at >= <when>
:order first_indexed_at
```

Timestamps are preserved across reindex cycles (see the Phase A timestamp preservation contract in `docs/PSS-ARCHITECTURE.md`), so entries are correctly attributed to their actual first installation — not the most recent reindex run.

## Execution

```bash
if [ -z "${CLAUDE_PLUGIN_ROOT:-}" ]; then
  echo "ERROR: CLAUDE_PLUGIN_ROOT not set." >&2
  exit 1
fi

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT}"
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
case "$ARCH" in
  x86_64) ARCH="x86_64" ;;
  arm64|aarch64) ARCH="arm64" ;;
esac

BIN="${PLUGIN_ROOT}/bin/pss-${OS}-${ARCH}"
if [ ! -x "$BIN" ]; then
  echo "ERROR: PSS binary not found at $BIN" >&2
  exit 1
fi

"$BIN" list-added-since $ARGUMENTS
```

## Examples

```
# Entries added in the last day
/pss-added-since 1d

# Entries added in the last 2 weeks, as JSON
/pss-added-since 2w --json

# Entries added since 2026-04-01
/pss-added-since 2026-04-01

# Entries added in the last 30 minutes, raise cap to 200
/pss-added-since 30m --limit 200
```

## Related Commands

- `/pss-search` — Search by keyword / full-text
- `/pss-status` — Show overall index health and stats (includes newest/oldest install banner)
- `/pss-reindex-skills` — Rebuild the full CozoDB index

## Notes

- The sibling Rust subcommand `pss list-added-between <start> <end>` accepts a closed-interval window when you need a specific day / week boundary. Invoke it directly via `$CLAUDE_PLUGIN_ROOT/bin/pss-<platform>` if the slash command is not enough.
- The sibling `pss list-updated-since <when>` reports entries that were re-enriched (not newly installed) — useful for "what changed in the last reindex?" investigations.
- Fail-fast parsing: `/pss-added-since yesterday` will error because the datetime parser rejects natural-language inputs. Use `1d` instead.
