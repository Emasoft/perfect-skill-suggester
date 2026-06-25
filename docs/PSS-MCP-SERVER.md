# PSS MCP Server

A thin **stdio MCP server** that exposes PSS's read-only temporal / lifeline
verbs as MCP tools, for external "time-travel" consumers (e.g. AI Maestro's
context panel). It is **opt-in** — you register it in an `.mcp.json`; it is
**not** loaded by the plugin's live hooks, and it does not touch the
`UserPromptSubmit` hot path.

Source: [`scripts/pss_mcp_server.py`](../scripts/pss_mcp_server.py)
(issue [#12](https://github.com/Emasoft/perfect-skill-suggester/issues/12), P-9).

## What it is (and isn't)

- **Is:** a ~150-line Python wrapper built on the official MCP SDK
  (`from mcp.server.fastmcp import FastMCP`). Each tool shells out to the
  resolved `pss` native binary with `--format json` where the verb supports
  it, parses the binary's JSON, and returns it. There is **one source of
  truth** — the binary — so query logic is never reimplemented here.
- **Isn't:** a second index, a cache, or a direct CozoDB reader. It never
  opens the `.db` file. It adds nothing to PSS's runtime dependencies — `mcp`
  is supplied at launch by `uv run --with "mcp[cli]"`, not pinned in
  `pyproject.toml`.

## Run it

```bash
uv run --with "mcp[cli]" scripts/pss_mcp_server.py
```

The binary is resolved exactly like the hot-path shell dispatch
(`bin/pss-hook-dispatch.sh`): it honors `$CLAUDE_PLUGIN_ROOT/bin/<platform-binary>`,
falling back to the repo's `bin/` for local development. A missing binary is a
fail-fast error (the tool raises `FileNotFoundError`), never a silent no-op.

## Opt-in registration (`.mcp.json`)

Add this to your project's or user's `.mcp.json`. Replace the path placeholder
with `${CLAUDE_PLUGIN_ROOT}/scripts/pss_mcp_server.py` (when registering inside
the plugin context) or an absolute path to the script:

```json
{
  "mcpServers": {
    "pss": {
      "command": "uv",
      "args": ["run", "--with", "mcp[cli]", "<abs-or-plugin-root>/scripts/pss_mcp_server.py"]
    }
  }
}
```

The first launch resolves and caches the `mcp[cli]` dependency via `uv`
(~1–2 s cold); subsequent launches reuse the cache.

## Tools

All six are read-only. Each returns the named binary verb's JSON, parsed to a
Python `dict` / `list[dict]`.

| Tool | Params | Returns | Backing verb |
|------|--------|---------|--------------|
| `pss_active_in` | `project_path: str`, `as_of: str \| None` | list of active-element rows in a folder (optionally at a past date) | `active-in <path> [--as-of D] --format json` |
| `pss_as_of` | `date: str` | list of every element installed & active at `date` | `as-of <date>` |
| `pss_timeline` | `element_id: str` | list of lifecycle events for one element | `timeline <id> --format json` |
| `pss_db_path` | — | `{"db_path": "<abs>"}` | `db-path --format json` |
| `pss_project_slug` | `project_path: str` | `{"abs_path": ..., "slug": "<basename>-<8hex>"}` | `project-slug <path> --format json` |
| `pss_contract_version` | — | `{"cli_version", "schema_version", "contract_version"}` | `--contract-version` |

`as_of` / `date` accept an RFC3339 date or shorthand (`"2026-03-14"`,
`"2026-03-14T12:00:00Z"`, `"now"`, `"yesterday"`). `element_id` is the temporal
id `<type>:<name>@<scope>:<scope_path_slug>` (e.g.
`agent:0-preflight@marketplace:trailofbits`); reconstruct its `scope_path_slug`
from a folder with `pss_project_slug`.

> Note: `pss_as_of` calls the binary **bare** — the `as-of` verb emits a JSON
> array by default and *rejects* `--format json` (exit 2), unlike the other
> verbs. The wrapper handles this difference for you.

## Version-gate with the contract handle

Before relying on any tool's output shape, call `pss_contract_version` and
gate on it. It is a stable handle across PSS upgrades — like `--version`, but
it also carries the temporal `schema_version` and the `contract_version`:

```json
{"cli_version": "3.8.3", "schema_version": "2", "contract_version": "1"}
```

`cli_version` always equals the binary's `--version`; `schema_version` bumps
when the temporal table layout changes; `contract_version` bumps when this
tool surface's contract changes. A consumer that pins `contract_version` will
not silently break when PSS adds verbs.

## Consumers shell out — never read the `.db` directly

These tools exist precisely so consumers do **not** reverse-engineer PSS's
storage. The CozoDB store is guarded by an `fcntl` advisory-lock protocol
(`LOCK_SH` readers / `LOCK_EX` atomic-rename writer), and the underlying
cozo-ce engine **SIGABRTs on a read/write race** rather than blocking. The
native `pss` binary — which every tool here shells out to — is the only
sanctioned reader. Use `pss_db_path` to *locate* the store for backup or a
health probe, but read its CONTENTS only through the binary.

See the CLI reference for the full verb set and the external-consumer
constraints (P-3 reindex cadence, P-5 blob capture, P-8 per-project
enablement, P-10 never-read-the-db):
[**PSS CLI Reference** → External time-travel consumers](./pss-cli-reference.md#external-time-travel-consumers--known-limitations).

## Tests

[`tests/unit/test_pss_mcp_server.py`](../tests/unit/test_pss_mcp_server.py)
drives the **real** binary against the **real** index — no mocks. Run:

```bash
uv run --with "mcp[cli]" --with pytest pytest tests/unit/test_pss_mcp_server.py -q
```
