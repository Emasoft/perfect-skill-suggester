"""Phase 3 (v3.7) tests: --format flag standardization, pss summary, pss tree,
and --format table for temporal subcommands.

Covers:
  Task 3.1 — COR-6: `--format <table|json|csv|tsv|markdown>` standardization
             with `--json` retained as a deprecated alias.
  Task 3.2 — `pss summary` (one-line + JSON overview of the index).
  Task 3.3 — `pss tree` (directory-tree view grouped by source/scope/type).
  Task 3.4 — `--format table` for the highest-priority temporal subcommands.

Tests exercise the real pre-built binary against the real pre-built CozoDB,
mirroring the pattern in test_phase_d_cli.py.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _binary_path() -> Path:
    """Resolve the platform-appropriate pre-built pss binary."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "darwin" and machine in ("arm64", "aarch64"):
        return ROOT / "bin" / "pss-darwin-arm64"
    if system == "darwin":
        return ROOT / "bin" / "pss-darwin-x86_64"
    if system == "linux" and machine in ("arm64", "aarch64"):
        return ROOT / "bin" / "pss-linux-arm64"
    if system == "linux":
        return ROOT / "bin" / "pss-linux-x86_64"
    if system == "windows":
        return ROOT / "bin" / "pss-windows-x86_64.exe"
    return ROOT / "bin" / f"pss-{system}-{machine}"


BIN = _binary_path()


def _db_present() -> bool:
    """Does the live CozoDB exist? Tests that need it are gated on this."""
    env_path = os.environ.get("CLAUDE_PLUGIN_DATA")
    if env_path and Path(env_path).is_absolute():
        if "perfect-skill-suggester" in Path(env_path).name.lower():
            p = Path(env_path) / "pss-skill-index.db"
            if p.exists():
                return True
    return (Path.home() / ".claude" / "cache" / "pss-skill-index.db").exists()


skip_if_no_binary = pytest.mark.skipif(
    not BIN.exists(),
    reason=f"pss binary not found at {BIN} — run scripts/pss_build.py first",
)
skip_if_no_db = pytest.mark.skipif(
    not _db_present(),
    reason="CozoDB not found — run /pss-reindex-skills first",
)


def _run(*args: str, expect_success: bool = True) -> subprocess.CompletedProcess:
    """Run pss with args, return the completed process."""
    proc = subprocess.run(
        [str(BIN), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if expect_success and proc.returncode != 0:
        raise AssertionError(
            f"pss {' '.join(args)} exited {proc.returncode}\nstdout: {proc.stdout!r}\nstderr: {proc.stderr!r}"
        )
    return proc


# ---------------------------------------------------------------------------
# Task 3.1 — --format standardization across subcommands
# ---------------------------------------------------------------------------


@skip_if_no_binary
@skip_if_no_db
def test_list_json_alias_returns_json():
    """`pss list --json` returns valid JSON (deprecated alias for --format json)."""
    proc = _run("list", "--json", "--top", "3")
    body = proc.stdout.strip()
    # Must parse as JSON without errors
    parsed = json.loads(body)
    assert isinstance(parsed, list), f"Expected list, got {type(parsed).__name__}"


@skip_if_no_binary
@skip_if_no_db
def test_list_format_json_returns_json():
    """`pss list --format json` returns valid JSON."""
    proc = _run("list", "--format", "json", "--top", "3")
    body = proc.stdout.strip()
    parsed = json.loads(body)
    assert isinstance(parsed, list)


@skip_if_no_binary
@skip_if_no_db
def test_list_format_table_returns_table():
    """`pss list --format table` returns a Unicode-bordered table."""
    proc = _run("list", "--format", "table", "--top", "3")
    body = proc.stdout
    # Hand-rolled print_table uses ┌ ┐ ─ ┬ ┴ │ borders
    assert any(c in body for c in ("┌", "│", "└")), (
        f"Expected Unicode table borders in output. Got: {body!r}"
    )


@skip_if_no_binary
@skip_if_no_db
def test_stats_format_json_returns_json():
    """`pss stats --format json` returns valid JSON."""
    proc = _run("stats", "--format", "json")
    body = proc.stdout.strip()
    parsed = json.loads(body)
    assert isinstance(parsed, dict)
    assert "total" in parsed, f"Expected 'total' key. Got: {list(parsed.keys())[:10]}"


@skip_if_no_binary
@skip_if_no_db
def test_vocab_format_json_returns_json():
    """`pss vocab languages --format json` returns valid JSON."""
    proc = _run("vocab", "languages", "--format", "json")
    body = proc.stdout.strip()
    # Vocab can return a list or object — both valid JSON
    json.loads(body)  # raises on garbage


@skip_if_no_binary
@skip_if_no_db
def test_search_format_json_returns_json():
    """`pss search rust --format json` returns valid JSON."""
    proc = _run("search", "rust", "--format", "json", "--top", "3")
    body = proc.stdout.strip()
    parsed = json.loads(body)
    assert isinstance(parsed, list)


@skip_if_no_binary
@skip_if_no_db
def test_coverage_format_json_returns_json():
    """`pss coverage --format json` returns valid JSON."""
    proc = _run("coverage", "--format", "json")
    body = proc.stdout.strip()
    json.loads(body)


# ---------------------------------------------------------------------------
# Task 3.2 — pss summary subcommand
# ---------------------------------------------------------------------------


@skip_if_no_binary
@skip_if_no_db
def test_summary_table_default():
    """`pss summary` (no --format) produces a one-line table summary with
    total counts and per-type breakdown."""
    proc = _run("summary")
    out = proc.stdout
    # Must mention "PSS index" and at least one element-type count
    assert "PSS index" in out, f"Expected 'PSS index' header. Got: {out[:200]!r}"
    # Must contain a total count line
    assert any(ch.isdigit() for ch in out), f"Expected at least one numeric count. Got: {out[:200]!r}"


@skip_if_no_binary
@skip_if_no_db
def test_summary_format_json_structured():
    """`pss summary --format json` returns a structured JSON object with
    total + per-type + per-source counts."""
    proc = _run("summary", "--format", "json")
    parsed = json.loads(proc.stdout)
    assert isinstance(parsed, dict)
    assert "total" in parsed
    assert isinstance(parsed["total"], int)
    assert "by_type" in parsed
    assert isinstance(parsed["by_type"], dict)
    assert "by_source" in parsed or "sources" in parsed, (
        f"Expected 'by_source' or 'sources' key. Got: {list(parsed.keys())}"
    )


@skip_if_no_binary
def test_summary_listed_in_help():
    """`pss --help` lists the summary subcommand."""
    proc = _run("--help")
    assert "summary" in proc.stdout.lower(), (
        f"Expected 'summary' in --help output. Got first 500 chars: {proc.stdout[:500]}"
    )


# ---------------------------------------------------------------------------
# Task 3.3 — pss tree subcommand
# ---------------------------------------------------------------------------


@skip_if_no_binary
@skip_if_no_db
def test_tree_default_renders_unicode():
    """`pss tree` produces a Unicode box-drawing tree (├ │ └ ─)."""
    proc = _run("tree")
    out = proc.stdout
    # Must contain at least some unicode tree characters
    assert any(c in out for c in ("├", "│", "└", "─")), (
        f"Expected Unicode tree chars in output. Got first 500: {out[:500]!r}"
    )


@skip_if_no_binary
@skip_if_no_db
def test_tree_format_json_structured():
    """`pss tree --format json` returns nested JSON."""
    proc = _run("tree", "--format", "json")
    parsed = json.loads(proc.stdout)
    # Top-level should be an object or list
    assert isinstance(parsed, (dict, list)), (
        f"Expected dict or list at top. Got: {type(parsed).__name__}"
    )


@skip_if_no_binary
def test_tree_listed_in_help():
    """`pss --help` lists the tree subcommand."""
    proc = _run("--help")
    assert "tree" in proc.stdout.lower(), (
        f"Expected 'tree' in --help output. Got: {proc.stdout[:500]}"
    )


# ---------------------------------------------------------------------------
# Task 3.4 — --format table on temporal subcommands
# ---------------------------------------------------------------------------


@skip_if_no_binary
@skip_if_no_db
def test_changes_summary_format_table():
    """`pss changes-summary --window 7d --format table` produces a bordered
    Unicode table (or a clean 'no results' line if the window is empty)."""
    proc = _run("changes-summary", "--window", "7d", "--format", "table")
    out = proc.stdout
    # Table or "no results" — either is fine; what we must NOT see is raw JSON.
    assert not out.strip().startswith("{"), (
        f"Expected table, got JSON. Output: {out[:300]!r}"
    )


@skip_if_no_binary
@skip_if_no_db
def test_scan_log_format_table():
    """`pss scan-log --format table` produces a table (Unicode borders)."""
    proc = _run("scan-log", "--limit", "5", "--format", "table")
    out = proc.stdout
    # Must NOT be a JSON array
    assert not out.strip().startswith("["), (
        f"Expected table, got JSON array. Output: {out[:300]!r}"
    )


@skip_if_no_binary
@skip_if_no_db
def test_changes_summary_format_json_still_works():
    """`--format json` still returns valid JSON on temporal cmds."""
    proc = _run("changes-summary", "--window", "7d", "--format", "json")
    parsed = json.loads(proc.stdout)
    assert isinstance(parsed, dict)
    assert "counts" in parsed or "window" in parsed


@skip_if_no_binary
@skip_if_no_db
def test_db_stats_format_table():
    """`pss db-stats --format table` produces a table."""
    proc = _run("db-stats", "--format", "table")
    out = proc.stdout
    assert not out.strip().startswith("{"), (
        f"Expected table, got JSON. Output: {out[:300]!r}"
    )


# ---------------------------------------------------------------------------
# Sanity check — --format table and --json must produce equivalent JSON
# ---------------------------------------------------------------------------


@skip_if_no_binary
@skip_if_no_db
def test_json_alias_and_format_json_equivalent_for_list():
    """`--json` and `--format json` must produce identical JSON for list."""
    proc1 = _run("list", "--json", "--top", "3")
    proc2 = _run("list", "--format", "json", "--top", "3")
    j1 = json.loads(proc1.stdout)
    j2 = json.loads(proc2.stdout)
    assert j1 == j2, f"--json and --format json produced different output.\n--json: {j1!r}\n--format json: {j2!r}"
