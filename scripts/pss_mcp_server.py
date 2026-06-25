#!/usr/bin/env python3
"""PSS MCP server — a stdio MCP surface for PSS's read-only temporal verbs.

Issue #12 P-9. A THIN wrapper: every tool shells out to the resolved ``pss``
native binary (the ONE source of truth for query logic) with ``--format json``
where the verb supports it, parses the binary's JSON, and returns it. There is
no query logic here and the hot ``UserPromptSubmit`` path is untouched.

Opt-in only — it is NOT registered in the plugin's live hooks. Run it via::

    uv run --with "mcp[cli]" scripts/pss_mcp_server.py

so PSS's core dependencies stay lean (``mcp`` is not a hard dependency). The
binary is resolved exactly like the hot-path shell dispatch
(``bin/pss-hook-dispatch.sh``): honor ``$CLAUDE_PLUGIN_ROOT/bin``, else fall
back to the repo's ``bin/``. Consumers should call these tools and NEVER open
the CozoDB ``.db`` file directly. Version-gate against ``pss_contract_version``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# pss_paths is a sibling module; make it importable whether this file is run
# directly (uv run scripts/pss_mcp_server.py) or loaded by the test suite.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pss_paths import resolve_pss_binary  # noqa: E402  (after sys.path injection)

mcp = FastMCP("pss")

# Temporal/lifeline queries are single-digit-ms; 30 s is a generous ceiling that
# still fails fast if the binary hangs instead of blocking the MCP client.
_TIMEOUT_SECONDS = 30


def _run_pss_json(args: list[str]) -> Any:
    """Run ``pss <args>``, return its parsed JSON stdout; raise on any failure.

    Fail-fast (no fallback): a missing binary, a non-zero exit, or non-JSON
    output each raise a clear error the MCP client surfaces to the caller.
    """
    binary = resolve_pss_binary()  # FileNotFoundError if the binary is absent
    proc = subprocess.run(
        [str(binary), *args],
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise RuntimeError(
            f"pss {' '.join(args)} failed (exit {proc.returncode}): {detail}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"pss {' '.join(args)} returned non-JSON output: {proc.stdout[:200]!r}"
        ) from exc


@mcp.tool()
def pss_active_in(project_path: str, as_of: str | None = None) -> list[dict[str, Any]]:
    """List every element ACTIVE in a project folder, optionally at a past date.

    Returns the UNION of (a) project/local elements whose scope_path matches the
    folder's slug, (b) all global user-scope elements, and (c) plugin/marketplace
    elements currently enabled — one row dict each (element_id, element_type,
    element_name, scope, enabled, first_seen, ...). ``project_path`` is an
    absolute folder path; ``as_of`` accepts an RFC3339 date or shorthand
    ("2026-03-14", "now", "yesterday") — omit it for the present moment. (Note:
    per-project plugin enablement at a PAST instant is not yet recorded, so (c)
    reflects current/global enablement; (a)/(b) ARE resolved as-of the date.)
    """
    args = ["active-in", project_path, "--format", "json"]
    if as_of is not None:
        args += ["--as-of", as_of]
    return _run_pss_json(args)


@mcp.tool()
def pss_as_of(date: str) -> list[dict[str, Any]]:
    """Snapshot of every element installed and active at a given date.

    ``date`` accepts RFC3339 or shorthand ("2026-03-14", "2026-03-14T12:00:00Z",
    "yesterday", "now"). Each row carries ``first_seen`` (the install instant)
    and ``first_seen_is_synthetic`` (true iff it is the v1→v2 migration
    placeholder rather than a real observed install).
    """
    # `as-of` emits a JSON array by DEFAULT and REJECTS --format json (exit 2),
    # unlike the other verbs — so it is called bare.
    return _run_pss_json(["as-of", date])


@mcp.tool()
def pss_timeline(element_id: str) -> list[dict[str, Any]]:
    """Full lifecycle event history for ONE element.

    ``element_id`` is the temporal id, e.g. ``skill:my-skill@user:`` or
    ``agent:0-preflight@marketplace:trailofbits``. Returns one row per event
    (event_type, observed_at, content_hash, file_size, token_count, diff_json),
    oldest first.
    """
    return _run_pss_json(["timeline", element_id, "--format", "json"])


@mcp.tool()
def pss_db_path() -> dict[str, Any]:
    """Canonical resolved CozoDB path PSS uses (honors --index / PSS_INDEX_PATH).

    Returns ``{"db_path": "<abs>"}``. Provided so consumers stop reverse-
    engineering PSS path resolution — but they should still shell out to ``pss``
    for every query and NEVER open this ``.db`` file directly (a concurrent
    reindex would race them).
    """
    return _run_pss_json(["db-path", "--format", "json"])


@mcp.tool()
def pss_project_slug(project_path: str) -> dict[str, Any]:
    """Compute a project folder's scope-path slug (``<basename>-<8-char-sha256>``).

    Returns ``{"abs_path": "<in>", "slug": "<out>"}``. This is the SAME algorithm
    PSS uses to key project/local elements, so the slug reconstructs an
    element_id's scope_path from an absolute path.
    """
    return _run_pss_json(["project-slug", project_path, "--format", "json"])


@mcp.tool()
def pss_contract_version() -> dict[str, Any]:
    """The external CLI contract handle for version-gating.

    Returns ``{"cli_version", "schema_version", "contract_version"}`` so a
    consumer can detect a PSS upgrade or a temporal-schema change BEFORE relying
    on any verb's output shape.
    """
    return _run_pss_json(["--contract-version"])


def main() -> None:
    """Serve the tools over stdio (the entry point for ``uv run``)."""
    mcp.run()


if __name__ == "__main__":
    main()
