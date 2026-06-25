"""P-9 (issue #12) tests: the PSS stdio MCP server (``scripts/pss_mcp_server.py``).

Strategy — NO MOCKS (project rule: mocked tests are useless). Every tool is
exercised against the REAL pre-built ``pss`` binary in ``<repo>/bin`` and the
REAL installed CozoDB index that ``pss db-path`` resolves. Tool functions are
imported and called DIRECTLY — the FastMCP ``@mcp.tool()`` decorator returns
the original function unchanged — so the tests stay fast and hermetic without
spawning the stdio transport.

Covered:
  * the shared binary resolver picks the right per-platform binary, honors
    ``$CLAUDE_PLUGIN_ROOT``, and fails fast when the binary is missing;
  * each of the 6 tools returns parsed JSON of the expected shape;
  * ``pss_contract_version`` returns exactly the 3 contract fields and its
    ``cli_version`` equals ``<binary> --version`` — the regression guard for
    the cli_version-mismatch bug fixed just before P-9;
  * all 6 tools are registered on the FastMCP instance.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

# The server imports the `mcp` SDK; skip the whole module cleanly if it is not
# present. The documented run command supplies it:
#   uv run --with "mcp[cli]" --with pytest pytest tests/unit/test_pss_mcp_server.py
pytest.importorskip("mcp.server.fastmcp")

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pss_paths  # noqa: E402  (import after sys.path injection is intentional)

BIN = ROOT / "bin" / pss_paths.detect_platform()

pytestmark = pytest.mark.skipif(
    not BIN.exists(),
    reason=f"pss binary not found at {BIN} — run scripts/pss_build.py first",
)


@pytest.fixture(scope="module")
def server() -> ModuleType:
    """Load ``scripts/pss_mcp_server.py`` as a module object."""
    spec = importlib.util.spec_from_file_location(
        "pss_mcp_server", SCRIPTS / "pss_mcp_server.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def repo_binary(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pin binary + VERSION resolution to the repo for deterministic tool runs.

    Setting ``$CLAUDE_PLUGIN_ROOT`` to the repo root makes ``resolve_pss_binary()``
    resolve ``<repo>/bin/<name>`` AND makes the binary read ``<repo>/VERSION``,
    so the contract-version regression guard compares like with like.
    """
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(ROOT))
    return BIN


# ---------------------------------------------------------------------------
# Binary resolver (shared, in pss_paths) — platform pick / env override / fail-fast
# ---------------------------------------------------------------------------


def test_resolve_binary_picks_platform_binary(repo_binary: Path) -> None:
    """resolve_pss_binary returns the correct per-platform binary under bin/."""
    resolved = pss_paths.resolve_pss_binary()
    assert resolved.name == pss_paths.detect_platform()
    assert resolved == ROOT / "bin" / pss_paths.detect_platform()
    assert resolved.exists()


def test_resolve_binary_honors_plugin_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """resolve_pss_binary honors $CLAUDE_PLUGIN_ROOT over the repo fallback."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    dummy = fake_bin / pss_paths.detect_platform()
    dummy.write_text("#!/bin/sh\n")
    dummy.chmod(0o755)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    assert pss_paths.resolve_pss_binary() == dummy


def test_resolve_binary_missing_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """resolve_pss_binary fails fast (FileNotFoundError) when no binary exists."""
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))  # empty dir, no bin/
    with pytest.raises(FileNotFoundError):
        pss_paths.resolve_pss_binary()


# ---------------------------------------------------------------------------
# The 6 tools — each returns parsed JSON of the expected shape (real binary)
# ---------------------------------------------------------------------------


def test_active_in_returns_list_of_dicts(server: ModuleType, repo_binary: Path) -> None:
    """pss_active_in returns a JSON list of element row dicts for a folder."""
    rows = server.pss_active_in(str(ROOT))
    assert isinstance(rows, list)
    if rows:
        row = rows[0]
        assert isinstance(row, dict)
        for key in ("element_id", "element_type", "element_name", "scope", "enabled"):
            assert key in row, f"row missing key {key!r}: {row}"


def test_active_in_accepts_as_of(server: ModuleType, repo_binary: Path) -> None:
    """The as_of param is wired: a pre-index date yields a list, not an error."""
    rows = server.pss_active_in(str(ROOT), as_of="2000-01-01")
    assert isinstance(rows, list)


def test_as_of_returns_list(server: ModuleType, repo_binary: Path) -> None:
    """pss_as_of returns a JSON list snapshot of active elements at a date."""
    rows = server.pss_as_of("now")
    assert isinstance(rows, list)
    assert rows, "the real index should report active elements at now"
    assert "element_id" in rows[0]


def test_timeline_returns_list(server: ModuleType, repo_binary: Path) -> None:
    """pss_timeline returns a JSON list of lifecycle events for one element."""
    snapshot = server.pss_as_of("now")
    assert snapshot, "need at least one active element to timeline"
    element_id = snapshot[0]["element_id"]
    events = server.pss_timeline(element_id)
    assert isinstance(events, list)
    assert events, f"element {element_id} should have >=1 event"
    assert "event_type" in events[0]
    assert "observed_at" in events[0]


def test_db_path_returns_dict(server: ModuleType, repo_binary: Path) -> None:
    """pss_db_path returns {"db_path": <abs .db path>}."""
    out = server.pss_db_path()
    assert isinstance(out, dict)
    assert "db_path" in out
    db_path = out["db_path"]
    assert os.path.isabs(db_path) and db_path.endswith(".db")


def test_project_slug_returns_dict(server: ModuleType, repo_binary: Path) -> None:
    """pss_project_slug returns {"abs_path": ..., "slug": "<basename>-<8hex>"}."""
    out = server.pss_project_slug(str(ROOT))
    assert isinstance(out, dict)
    assert out["abs_path"] == str(ROOT)
    assert re.fullmatch(r".+-[0-9a-f]{8}", out["slug"]), out["slug"]


def test_contract_version_three_fields(server: ModuleType, repo_binary: Path) -> None:
    """pss_contract_version returns exactly the 3 contract fields."""
    out = server.pss_contract_version()
    assert isinstance(out, dict)
    assert set(out) == {"cli_version", "schema_version", "contract_version"}


def test_contract_version_cli_matches_version_flag(
    server: ModuleType, repo_binary: Path
) -> None:
    """Regression guard: contract cli_version == ``<binary> --version``.

    Both read ``<repo>/VERSION`` (pinned via $CLAUDE_PLUGIN_ROOT) so a mismatch
    would mean the contract handle drifted from the real version — the exact
    bug fixed just before P-9.
    """
    contract = server.pss_contract_version()
    proc = subprocess.run(
        [str(BIN), "--version"],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT)},
    )
    version_from_flag = proc.stdout.strip().split()[-1]
    assert contract["cli_version"] == version_from_flag


# ---------------------------------------------------------------------------
# MCP registration + fail-fast at the tool layer
# ---------------------------------------------------------------------------


def test_all_six_tools_registered(server: ModuleType) -> None:
    """The 6 read verbs are registered as MCP tools on the FastMCP instance."""
    names = {tool.name for tool in server.mcp._tool_manager.list_tools()}
    assert names == {
        "pss_active_in",
        "pss_as_of",
        "pss_timeline",
        "pss_db_path",
        "pss_project_slug",
        "pss_contract_version",
    }


def test_registered_tools_have_descriptions(server: ModuleType) -> None:
    """Every registered tool carries a non-empty description (its docstring)."""
    for tool in server.mcp._tool_manager.list_tools():
        assert tool.description and tool.description.strip(), tool.name


def test_tool_raises_when_binary_missing(
    server: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail-fast: a tool call raises when the binary cannot be resolved."""
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))  # empty dir, no bin/
    with pytest.raises(FileNotFoundError):
        server.pss_db_path()
