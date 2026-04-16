"""Phase D (v2.11.0) tests: Rust CLI query/search/management subcommands.

Covers the new power-user subcommands that expose CozoDB capabilities without
requiring Python:

  - `pss count`                       Total skill count (integer)
  - `pss stats` banner fields         oldest / newest / last-reindex timestamps
  - `pss get <name>`                  Single entry lookup with --json
  - `pss list-added-since <when>`     first_indexed_at-based filtering
  - `pss list-added-between <a> <b>`  first_indexed_at between two timestamps
  - `pss list-updated-since <when>`   last_updated_at-based filtering
  - `pss find-by-name <sub>`          Name substring search
  - `pss find-by-keyword <kw>`        Keyword index lookup
  - `pss find-by-domain <d>`          Domain index lookup
  - `pss find-by-language <l>`        Language index lookup
  - `pss health`                      Exit code 0/1/2

Test strategy: we exercise the real pre-built binary against the real
pre-built CozoDB. The binary is located via the project's `bin/` directory.
Tests that require a specific timestamp shape are skipped if the live DB does
not have timestamp columns populated.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any

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


def _run_pss(*args: str, expect_success: bool = True) -> subprocess.CompletedProcess:
    """Run pss with args, return the completed process. Never shells-out."""
    proc = subprocess.run(
        [str(BIN), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if expect_success and proc.returncode != 0:
        pytest.fail(
            f"pss {' '.join(args)} failed (exit={proc.returncode}):\n"
            f"stdout: {proc.stdout}\n"
            f"stderr: {proc.stderr}"
        )
    return proc


def _run_pss_json(*args: str) -> Any:
    """Run pss with --json and parse stdout."""
    proc = _run_pss(*args, "--json")
    return json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# pss count
# ---------------------------------------------------------------------------


@skip_if_no_binary
@skip_if_no_db
def test_count_returns_positive_integer() -> None:
    """`pss count` prints a single positive integer on stdout."""
    proc = _run_pss("count")
    out = proc.stdout.strip()
    assert out.isdigit(), f"count output should be a plain integer, got: {out!r}"
    assert int(out) > 0, f"count should be > 0, got {out}"


@skip_if_no_binary
@skip_if_no_db
def test_count_json_format() -> None:
    """`pss count --json` returns {"count": N}."""
    obj = _run_pss_json("count")
    assert isinstance(obj, dict), f"count --json should return an object, got {type(obj)}"
    assert "count" in obj, f"count --json should have 'count' key, got keys: {list(obj.keys())}"
    assert isinstance(obj["count"], int) and obj["count"] > 0


# ---------------------------------------------------------------------------
# pss health
# ---------------------------------------------------------------------------


@skip_if_no_binary
@skip_if_no_db
def test_health_exits_zero_when_db_populated() -> None:
    """`pss health` exits 0 when DB exists and has rows."""
    proc = _run_pss("health", expect_success=False)
    assert proc.returncode == 0, (
        f"health should exit 0 on populated DB, got {proc.returncode}\n"
        f"stderr: {proc.stderr}"
    )


@skip_if_no_binary
@skip_if_no_db
def test_health_silent_by_default() -> None:
    """`pss health` is silent on stdout/stderr by default."""
    proc = _run_pss("health", expect_success=False)
    assert proc.stdout.strip() == ""


@skip_if_no_binary
@skip_if_no_db
def test_health_verbose_prints_diagnostic() -> None:
    """`pss health --verbose` prints a diagnostic line."""
    proc = _run_pss("health", "--verbose", expect_success=False)
    assert proc.returncode == 0
    combined = proc.stdout + proc.stderr
    assert combined.strip() != "", "health --verbose should print a diagnostic"


@skip_if_no_binary
def test_health_exits_two_when_db_missing(tmp_path: Path) -> None:
    """`pss health --index <missing>` exits 2 when DB not found.

    Uses tmp_path so we're guaranteed a location with no pre-existing DB —
    tmp_path is fresh per test per pytest's fixture contract.
    """
    # Point --index at a file inside a fresh tmp dir. The `.db` suffix
    # forces the explicit-path code path in the health dispatcher.
    bogus = tmp_path / "no-such-index.db"
    assert not bogus.exists(), "tmp_path should start empty"
    proc = subprocess.run(
        [str(BIN), "--index", str(bogus), "health"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 2, (
        f"health with missing DB should exit 2, got {proc.returncode}\n"
        f"stderr: {proc.stderr}"
    )


# ---------------------------------------------------------------------------
# pss get <name>
# ---------------------------------------------------------------------------


@skip_if_no_binary
@skip_if_no_db
def test_get_nonexistent_returns_error() -> None:
    """`pss get <missing-name>` exits non-zero."""
    proc = _run_pss(
        "get", "this-skill-should-not-exist-phase-d-test", expect_success=False
    )
    assert proc.returncode != 0


@skip_if_no_binary
@skip_if_no_db
def test_get_json_shape() -> None:
    """`pss get <name> --json` returns a dict with core fields."""
    # Find any known skill via the existing `list` subcommand. Legacy
    # subcommands use `--format json` + `--top` (different convention from
    # Phase D's `--json` + `--limit`) — that asymmetry is preserved for
    # backwards compatibility.
    proc = _run_pss("list", "--top", "1", "--type", "skill", "--format", "json")
    list_obj = json.loads(proc.stdout)
    assert isinstance(list_obj, list) and len(list_obj) > 0
    sample_name = list_obj[0]["name"]
    obj = _run_pss_json("get", sample_name)
    # When multiple entries match, the binary returns an array — normalise.
    if isinstance(obj, list):
        assert len(obj) > 0
        obj = obj[0]
    assert "name" in obj
    assert "type" in obj
    assert "description" in obj


# ---------------------------------------------------------------------------
# pss list-added-since <iso-datetime>
# ---------------------------------------------------------------------------


@skip_if_no_binary
@skip_if_no_db
def test_list_added_since_accepts_relative_shorthand() -> None:
    """`pss list-added-since 30d` accepts relative duration."""
    # Even if nothing was added in the last 30 days, the command should succeed
    # with an empty list rather than erroring.
    proc = _run_pss("list-added-since", "30d", "--json")
    assert proc.returncode == 0
    obj = json.loads(proc.stdout)
    assert isinstance(obj, list)


@skip_if_no_binary
@skip_if_no_db
def test_list_added_since_accepts_rfc3339() -> None:
    """`pss list-added-since 2020-01-01T00:00:00Z` accepts RFC 3339."""
    proc = _run_pss(
        "list-added-since", "2020-01-01T00:00:00Z", "--json", "--limit", "5"
    )
    assert proc.returncode == 0
    obj = json.loads(proc.stdout)
    assert isinstance(obj, list)


@skip_if_no_binary
@skip_if_no_db
def test_list_added_since_accepts_date_only() -> None:
    """`pss list-added-since 2020-01-01` accepts date-only (midnight UTC)."""
    proc = _run_pss(
        "list-added-since", "2020-01-01", "--json", "--limit", "3"
    )
    assert proc.returncode == 0
    obj = json.loads(proc.stdout)
    assert isinstance(obj, list)


@skip_if_no_binary
@skip_if_no_db
def test_list_added_since_invalid_datetime_fails() -> None:
    """`pss list-added-since garbage` exits with error."""
    proc = _run_pss("list-added-since", "not-a-datetime", expect_success=False)
    assert proc.returncode != 0
    assert "date" in proc.stderr.lower() or "time" in proc.stderr.lower() or \
        "parse" in proc.stderr.lower() or "invalid" in proc.stderr.lower()


# ---------------------------------------------------------------------------
# pss list-added-between <start> <end>
# ---------------------------------------------------------------------------


@skip_if_no_binary
@skip_if_no_db
def test_list_added_between_wide_range_returns_entries() -> None:
    """A wide range returns non-empty (most entries should match)."""
    proc = _run_pss(
        "list-added-between", "2020-01-01", "2030-01-01", "--json", "--limit", "5"
    )
    assert proc.returncode == 0
    obj = json.loads(proc.stdout)
    assert isinstance(obj, list)
    # Live DB should have some entries within the wide range.
    assert len(obj) > 0, "wide range [2020..2030] should return entries"


# ---------------------------------------------------------------------------
# pss list-updated-since <iso-datetime>
# ---------------------------------------------------------------------------


@skip_if_no_binary
@skip_if_no_db
def test_list_updated_since_wide_range() -> None:
    """Wide range returns entries."""
    proc = _run_pss(
        "list-updated-since", "2020-01-01T00:00:00Z", "--json", "--limit", "5"
    )
    assert proc.returncode == 0
    obj = json.loads(proc.stdout)
    assert isinstance(obj, list)
    assert len(obj) > 0


# ---------------------------------------------------------------------------
# pss find-by-name
# ---------------------------------------------------------------------------


@skip_if_no_binary
@skip_if_no_db
def test_find_by_name_common_substring() -> None:
    """`pss find-by-name docker` should return entries whose name contains 'docker'."""
    obj = _run_pss_json("find-by-name", "docker", "--limit", "10")
    assert isinstance(obj, list)
    if obj:
        for row in obj:
            assert "docker" in row["name"].lower(), (
                f"row name {row['name']!r} should contain 'docker'"
            )


# ---------------------------------------------------------------------------
# pss find-by-keyword
# ---------------------------------------------------------------------------


@skip_if_no_binary
@skip_if_no_db
def test_find_by_keyword_returns_list() -> None:
    """`pss find-by-keyword docker --json` returns a JSON array."""
    proc = _run_pss("find-by-keyword", "docker", "--json", "--limit", "10")
    assert proc.returncode == 0
    obj = json.loads(proc.stdout)
    assert isinstance(obj, list)


# ---------------------------------------------------------------------------
# pss find-by-domain
# ---------------------------------------------------------------------------


@skip_if_no_binary
@skip_if_no_db
def test_find_by_domain_devops_returns_entries() -> None:
    """`pss find-by-domain devops` returns entries (devops is a common domain)."""
    # Try several common domains — pick one that exists.
    domains = ["devops", "testing", "web", "ai-ml", "security", "data"]
    matched = []
    for d in domains:
        obj = _run_pss_json("find-by-domain", d, "--limit", "3")
        assert isinstance(obj, list)
        if obj:
            matched.append(d)
    # At least one of the common domains should have entries.
    assert matched, f"None of {domains} returned entries — check domain index"


# ---------------------------------------------------------------------------
# pss find-by-language
# ---------------------------------------------------------------------------


@skip_if_no_binary
@skip_if_no_db
def test_find_by_language_python_returns_entries() -> None:
    """`pss find-by-language python` returns entries (python is common)."""
    obj = _run_pss_json("find-by-language", "python", "--limit", "5")
    assert isinstance(obj, list)
    assert len(obj) > 0, "python should have at least one skill entry"


# ---------------------------------------------------------------------------
# pss stats banner (Phase D enrichments)
# ---------------------------------------------------------------------------


@skip_if_no_binary
@skip_if_no_db
def test_stats_banner_has_timestamp_fields() -> None:
    """`pss stats --format json` includes oldest_first_indexed, newest_first_indexed, last_reindex.

    Note: `stats` defaults to JSON (legacy), so --format json is redundant here —
    but we pass it explicitly for clarity. Phase D subcommands use --json as an
    opt-in flag; `stats` retains its pre-existing JSON-default behaviour for
    backwards compatibility with downstream scripts.
    """
    proc = _run_pss("stats", "--format", "json")
    obj = json.loads(proc.stdout)
    assert isinstance(obj, dict)
    # New banner fields added by Phase D:
    # We only require the keys exist — values may be null on a fresh DB.
    expected = {"total", "oldest_first_indexed", "newest_first_indexed", "last_reindex"}
    present = set(obj.keys())
    missing = expected - present
    assert not missing, (
        f"stats --json should include Phase D banner fields; missing: {missing}\n"
        f"present: {sorted(present)}"
    )


@skip_if_no_binary
@skip_if_no_db
def test_stats_human_banner_reads_total_first() -> None:
    """`pss stats --format table` prints a 'Total: N entries' line as the first line."""
    # Use explicit --format table because `stats` defaults to JSON for
    # backwards compatibility.
    proc = _run_pss("stats", "--format", "table")
    # First non-blank line should start with "Total"
    first = next(
        (line for line in proc.stdout.splitlines() if line.strip()), ""
    )
    assert first.lower().startswith("total"), (
        f"First stats line should start with 'Total', got: {first!r}"
    )


# ---------------------------------------------------------------------------
# Help & discoverability
# ---------------------------------------------------------------------------


@skip_if_no_binary
def test_help_lists_all_phase_d_subcommands() -> None:
    """`pss --help` lists every Phase D subcommand."""
    proc = _run_pss("--help", expect_success=True)
    expected_subs = [
        "count",
        "get",
        "health",
        "list-added-since",
        "list-added-between",
        "list-updated-since",
        "find-by-name",
        "find-by-keyword",
        "find-by-domain",
        "find-by-language",
    ]
    missing = [s for s in expected_subs if s not in proc.stdout]
    assert not missing, (
        f"--help missing Phase D subcommands: {missing}\n\nstdout:\n{proc.stdout}"
    )


@skip_if_no_binary
def test_existing_flags_still_work() -> None:
    """Backwards-compat: --pass1-batch, --extract-prev-msg still in help.

    Phase C (v3.0.0): --build-db was intentionally removed; CozoDB is now
    populated exclusively by the Python merge writer (pss_merge_queue).
    """
    proc = _run_pss("--help", expect_success=True)
    assert "--pass1-batch" in proc.stdout, "pass1-batch flag removed"
    assert "--build-db" not in proc.stdout, (
        "build-db flag must be removed in Phase C"
    )
    assert "--extract-prev-msg" in proc.stdout, "extract-prev-msg flag removed"
    assert "--index-file" in proc.stdout, "index-file flag removed"
