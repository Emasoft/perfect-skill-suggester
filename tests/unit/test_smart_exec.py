"""Tests for scripts/smart_exec.py — the no-install tool runner.

Two things here are genuinely dangerous if they regress:
  1. `resolve_tool` is the allowlist that stops smart_exec from fetching an
     arbitrary (typosquatted) package name straight off the command line.
  2. `powershell_module_argv` interpolates names into a `-Command` string, so
     the name validators are the only thing between a tool name and shell
     injection.
The argv builders are pure and executor-independent (npx/npm/yarn/pnpm), so
they are asserted verbatim — each executor has a *different* way to select a
binary whose name differs from its package, and getting that wrong silently
runs the wrong tool.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def _load_module(name: str, path: Path):
    """Load a script module by path so the test does not depend on PYTHONPATH."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    # smart_exec uses `from __future__ import annotations` + @dataclass; the
    # dataclass machinery resolves the stringified annotations through
    # sys.modules[cls.__module__], so the module must be registered BEFORE exec.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def se():
    """Load smart_exec.py without running its CLI."""
    return _load_module("smart_exec_under_test", SCRIPTS_DIR / "smart_exec.py")


def test_resolve_tool_is_an_allowlist_not_a_passthrough(se) -> None:
    """Unknown tool names raise instead of being fetched — anti-typosquat guard."""
    assert se.resolve_tool("ruff").package == "ruff"
    assert se.resolve_tool("tsc").package == "typescript"

    with pytest.raises(ValueError) as exc:
        se.resolve_tool("rufff")
    # The message must list the legal names, otherwise the failure is unactionable.
    assert "rufff" in str(exc.value) and "ruff" in str(exc.value)


def test_each_node_executor_selects_a_renamed_binary_its_own_way(se) -> None:
    """npx uses -p, npm uses --package=, yarn appends cmd, pnpm must not."""
    args = ["-p", "."]
    assert se.npx_argv("typescript", "tsc", args) == [
        "npx", "--yes", "-p", "typescript", "tsc", "-p", "."
    ]
    assert se.npm_exec_argv("typescript", "tsc", args) == [
        "npm", "exec", "--yes", "--package=typescript", "--", "tsc", "-p", "."
    ]
    assert se.yarn_dlx_argv("typescript", "tsc", args) == [
        "yarn", "dlx", "typescript", "tsc", "-p", "."
    ]
    # pnpm dlx has no package-selection flag: prepending the cmd would pass it
    # as an ARGUMENT to the default bin, not select a different bin.
    assert se.pnpm_dlx_argv("typescript", "tsc", args) == ["pnpm", "dlx", "typescript", "-p", "."]

    # When binary == package, no selection machinery is emitted at all.
    assert se.npx_argv("ruff", "ruff", []) == ["npx", "--yes", "ruff"]
    assert se.yarn_dlx_argv("ruff", "ruff", []) == ["yarn", "dlx", "ruff"]


def test_powershell_argv_rejects_injection_and_escapes_quotes(se) -> None:
    """Module/cmdlet names are validated before interpolation; args are ''-escaped."""
    for bad_module in ("PSScriptAnalyzer; rm -rf /", "$(whoami)", "-Recurse", ""):
        with pytest.raises(ValueError):
            se.powershell_module_argv(bad_module, "Invoke-ScriptAnalyzer", [])

    for bad_cmdlet in ("Invoke-ScriptAnalyzer; iex $x", "notacmdlet", "Get_Thing"):
        with pytest.raises(ValueError):
            se.powershell_module_argv("PSScriptAnalyzer", bad_cmdlet, [])

    # PowerShell single-quote escaping doubles the quote — the only safe form.
    assert se.ps_quote("it's") == "'it''s'"
    assert se.ps_quote("plain") == "'plain'"


def test_cli_db_subcommand_reports_the_allowlist_as_machine_readable_json(se, capsys) -> None:
    """`db --json` dumps every ToolSpec so callers can discover legal tool names."""
    rc = se.main(["db", "--json"])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ruff"]["ecosystem"] == "python"
    assert payload["tsc"]["package"] == "typescript" and payload["tsc"]["command"] == "tsc"
    assert set(payload) == set(se.TOOL_DB)


def test_run_subcommand_keeps_tool_flags_out_of_smart_execs_own_argv(se) -> None:
    """REMAINDER capture means `--check` belongs to the tool, not to smart_exec."""
    ns = se.parse_args(["run", "--dry-run", "prettier", "--check", "."])
    assert ns.subcmd == "run"
    assert ns.dry_run is True
    assert ns.tool == "prettier"
    assert ns.tool_args == ["--check", "."]
