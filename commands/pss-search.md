---
name: pss-search
description: "Search the PSS CozoDB index for skills, agents, commands, rules, MCP or LSP servers by keyword or full-text query"
argument-hint: "<query> [--top N] [--type T] [--domain D] [--language L] [--format json|table]"
effort: low
allowed-tools: ["Bash"]
---

# PSS Search Command

Full-text search across the PSS CozoDB index. Matches against element names, descriptions, and keywords in a single query. Runs entirely through the Rust binary (`pss search`) — no LLM involvement, no Python startup cost — so a query against an 8000+ entry index completes in under 10 ms.

This is the fastest way to answer "is there already a skill for X?" or "what did I install about Y?" without reading any SKILL.md file.

## Usage

```
/pss-search <query>
/pss-search <query> --top N
/pss-search <query> --format table
/pss-search <query> --type skill --language python
```

| Argument | Description |
|----------|-------------|
| `<query>` | Free-form search text. Case-insensitive substring match against names, descriptions, and keywords. |
| `--top N` | Return only the top N matches (default: 20) |
| `--type T` | Restrict to a single element type: `skill`, `agent`, `command`, `rule`, `mcp`, or `lsp` |
| `--domain D` | Filter by domain (e.g. `security`, `ai-ml`, `devops`) |
| `--language L` | Filter by programming language (e.g. `python`, `typescript`, `rust`) |
| `--framework F` | Filter by framework (e.g. `react`, `django`, `flutter`) |
| `--tool T` | Filter by tool (e.g. `docker`, `ffmpeg`, `terraform`) |
| `--category C` | Filter by category |
| `--keyword KW` | Filter by keyword |
| `--platform P` | Filter by target platform (e.g. `ios`, `linux`, `universal`) |
| `--format json\|table` | Output format (default: `json`). Use `table` for a human-readable rendering. |

## How It Works

The slash command invokes the Rust binary's `search` subcommand. The binary opens the CozoDB store at `$CLAUDE_PLUGIN_DATA/pss-skill-index.db` (or `~/.claude/cache/pss-skill-index.db` as fallback) and runs a ranked lookup that joins the `skills`, `skill_keywords`, and description indexes. Results are ordered by match quality.

Because the hook pipeline and this command both read from the same CozoDB store, search results reflect the exact state the hook will use when suggesting skills — no drift between "what PSS shows me" and "what I can search directly".

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

"$BIN" search $ARGUMENTS
```

## Examples

```
# Find a skill for docker
/pss-search docker

# Find skills about tailwind, rendered as a human-readable table
/pss-search tailwind --format table

# Only MCP entries matching the query
/pss-search filesystem --type mcp

# Python skills mentioning testing
/pss-search testing --language python

# Top 10 matches for rust cargo
/pss-search "rust cargo" --top 10
```

## Related Commands

- `/pss-status` — Show PSS index health and element counts
- `/pss-added-since` — List entries installed after a given time
- `/pss-get-description <name>` — Get metadata for a specific element
- `/pss-reindex-skills` — Rebuild the CozoDB index from scratch

## Notes

- Results are read-only; the command never writes to the DB.
- If you need structured filtering, call the Rust binary directly: `pss list --type skill`, `pss find-by-domain devops`, `pss find-by-keyword docker`, `pss find-by-language python`.
- When the index is empty, the command exits with status 1 and prints an error. Run `/pss-reindex-skills` to populate it.
