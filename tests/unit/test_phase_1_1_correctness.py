#!/usr/bin/env python3
"""Phase 1.1 — correctness pass (audit 20260514).

Covers:
  - DI-5: count_skills returns -1 sentinel on corrupt DB, 0 on missing/empty.
  - HP-1: _safe_read_text caps at max_bytes and never raises.
  - HP-2: installed_plugins.json v1 format rejected fail-fast (CC v2.1.69+ uses v2).
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
    """Load a script module from path so we don't depend on PYTHONPATH layout."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def discover():
    """Load pss_discover.py without running its CLI."""
    return _load_module("pss_discover_under_test", SCRIPTS_DIR / "pss_discover.py")


@pytest.fixture
def cozodb():
    """Load pss_cozodb.py."""
    return _load_module("pss_cozodb_under_test", SCRIPTS_DIR / "pss_cozodb.py")


# ----------------------------------------------------------------------------
# DI-5 — count_skills sentinel
# ----------------------------------------------------------------------------


def test_count_skills_returns_zero_when_db_missing(cozodb, tmp_path, monkeypatch):
    """Missing DB file → 0 (legit empty, auto-reindex appropriate)."""
    fake_path = tmp_path / "absent.db"
    assert not fake_path.exists()
    monkeypatch.setattr(cozodb, "get_db_path", lambda: fake_path)
    assert cozodb.count_skills() == 0


def test_count_skills_returns_neg_one_when_open_fails(cozodb, tmp_path, monkeypatch):
    """DB file exists but open fails → -1 sentinel (corrupt — do NOT auto-reindex)."""
    bogus = tmp_path / "corrupt.db"
    bogus.write_bytes(b"\x00\x01not-a-real-cozo-db\x02")
    monkeypatch.setattr(cozodb, "get_db_path", lambda: bogus)
    # Force open_db to raise — simulates pycozo failing on truly corrupt file.
    def fail_open(_path: Path | None = None) -> object:
        raise RuntimeError("simulated open failure")
    monkeypatch.setattr(cozodb, "open_db", fail_open)
    assert cozodb.count_skills() == -1


def test_count_skills_returns_neg_one_when_query_fails(cozodb, tmp_path, monkeypatch):
    """Open succeeds but query raises unexpected → -1 sentinel."""
    bogus = tmp_path / "schema_corrupt.db"
    bogus.write_bytes(b"placeholder")  # exists so get_db_path check passes
    monkeypatch.setattr(cozodb, "get_db_path", lambda: bogus)

    class FakeClient:
        def run(self, *_args, **_kwargs):
            raise RuntimeError("simulated internal corruption")

        def close(self) -> None:
            return None

    monkeypatch.setattr(cozodb, "open_db", lambda *_a, **_k: FakeClient())
    assert cozodb.count_skills() == -1


def test_count_skills_returns_zero_when_schema_absent(cozodb, tmp_path, monkeypatch):
    """'relation does not exist' is a legit empty state (pre-reindex)."""
    bogus = tmp_path / "no_schema.db"
    bogus.write_bytes(b"placeholder")
    monkeypatch.setattr(cozodb, "get_db_path", lambda: bogus)

    class FakeClient:
        def run(self, *_args, **_kwargs):
            raise RuntimeError("relation 'skills' does not exist")

        def close(self) -> None:
            return None

    monkeypatch.setattr(cozodb, "open_db", lambda *_a, **_k: FakeClient())
    assert cozodb.count_skills() == 0


def test_count_skills_returns_count_for_healthy_db(cozodb, tmp_path, monkeypatch):
    """Legit count makes it through unmodified."""
    fake = tmp_path / "healthy.db"
    fake.write_bytes(b"placeholder")
    monkeypatch.setattr(cozodb, "get_db_path", lambda: fake)

    class FakeClient:
        def run(self, *_args, **_kwargs):
            return {"rows": [[42]], "headers": ["count(name)"]}

        def close(self) -> None:
            return None

    monkeypatch.setattr(cozodb, "open_db", lambda *_a, **_k: FakeClient())
    assert cozodb.count_skills() == 42


def test_db_is_healthy_treats_neg_one_as_unhealthy(cozodb, tmp_path, monkeypatch):
    """db_is_healthy() must return False for both 0 (empty) AND -1 (corrupt)."""
    monkeypatch.setattr(cozodb, "count_skills", lambda *_a, **_k: -1)
    assert cozodb.db_is_healthy() is False
    monkeypatch.setattr(cozodb, "count_skills", lambda *_a, **_k: 0)
    assert cozodb.db_is_healthy() is False
    monkeypatch.setattr(cozodb, "count_skills", lambda *_a, **_k: 1)
    assert cozodb.db_is_healthy() is True


# ----------------------------------------------------------------------------
# HP-1 — _safe_read_text capping
# ----------------------------------------------------------------------------


def test_safe_read_text_returns_content_under_cap(discover, tmp_path):
    f = tmp_path / "small.md"
    f.write_text("hello world", encoding="utf-8")
    result = discover._safe_read_text(f)
    assert result == "hello world"


def test_safe_read_text_returns_none_over_cap(discover, tmp_path, capsys):
    f = tmp_path / "big.md"
    payload = "x" * 5000
    f.write_text(payload, encoding="utf-8")
    result = discover._safe_read_text(f, max_bytes=100)
    assert result is None
    captured = capsys.readouterr()
    assert "size 5000 bytes > cap 100" in captured.err
    assert str(f) in captured.err


def test_safe_read_text_returns_none_on_missing_file(discover, tmp_path, capsys):
    f = tmp_path / "absent.md"
    assert not f.exists()
    result = discover._safe_read_text(f)
    assert result is None
    captured = capsys.readouterr()
    assert "stat failed" in captured.err


def test_safe_read_text_respects_default_cap(discover):
    # 4 MB default
    assert discover.DEFAULT_READ_CAP == 4 * 1024 * 1024


def test_safe_read_text_respects_manifest_cap(discover):
    # 1 MB manifest cap (smaller for JSON)
    assert discover.MANIFEST_READ_CAP == 1 * 1024 * 1024


def test_safe_read_text_honors_errors_arg(discover, tmp_path):
    """errors='replace' must not crash on invalid bytes."""
    f = tmp_path / "binary.md"
    # 0x80 is invalid as a UTF-8 start byte
    f.write_bytes(b"valid \x80 invalid")
    result = discover._safe_read_text(f, errors="replace")
    assert result is not None
    # Replacement happened (no exception)
    assert "valid" in result


# ----------------------------------------------------------------------------
# HP-2 — installed_plugins.json v2 enforcement
# ----------------------------------------------------------------------------


def test_installed_plugins_v1_rejected(discover, tmp_path, monkeypatch, capsys):
    """v1 format (no version key, plugins flat dict) must be rejected."""
    fake_claude_dir = tmp_path / ".claude"
    plugins_dir = fake_claude_dir / "plugins"
    plugins_dir.mkdir(parents=True)
    plugins_file = plugins_dir / "installed_plugins.json"
    # v1 format: flat dict, no version key.
    plugins_file.write_text(json.dumps({
        "plugins": {"foo@bar": {"installPath": "/p", "version": "1.0"}}
    }), encoding="utf-8")
    monkeypatch.setattr(discover, "get_claude_dir", lambda: fake_claude_dir)
    elements = discover.discover_plugins()
    assert elements == []
    captured = capsys.readouterr()
    assert "version None" in captured.err or "version" in captured.err
    assert "expected 2" in captured.err


def test_installed_plugins_v2_accepted(discover, tmp_path, monkeypatch):
    """v2 format with valid plugin entry produces elements."""
    fake_claude_dir = tmp_path / ".claude"
    plugins_dir = fake_claude_dir / "plugins"
    plugins_dir.mkdir(parents=True)
    plugins_file = plugins_dir / "installed_plugins.json"
    plugins_file.write_text(json.dumps({
        "version": 2,
        "plugins": {
            "test-plugin@test-market": [
                {
                    "scope": "user",
                    "installPath": "/tmp/p",
                    "version": "1.0.0",
                    "installedAt": "2026-05-15T00:00:00Z",
                    "gitCommitSha": "abc123",
                }
            ]
        }
    }), encoding="utf-8")
    monkeypatch.setattr(discover, "get_claude_dir", lambda: fake_claude_dir)
    elements = discover.discover_plugins()
    assert len(elements) == 1
    assert elements[0]["type"] == "plugin"
    assert elements[0]["name"] == "test-plugin@test-market"


def test_installed_plugins_v1_with_explicit_version_one_rejected(
    discover, tmp_path, monkeypatch, capsys
):
    """v1 format with explicit version=1 must be rejected (catches downgrade)."""
    fake_claude_dir = tmp_path / ".claude"
    plugins_dir = fake_claude_dir / "plugins"
    plugins_dir.mkdir(parents=True)
    plugins_file = plugins_dir / "installed_plugins.json"
    plugins_file.write_text(json.dumps({
        "version": 1,
        "plugins": {"old@market": {"installPath": "/p"}}
    }), encoding="utf-8")
    monkeypatch.setattr(discover, "get_claude_dir", lambda: fake_claude_dir)
    elements = discover.discover_plugins()
    assert elements == []
    captured = capsys.readouterr()
    assert "version 1" in captured.err
    assert "expected 2" in captured.err


def test_installed_plugins_non_object_rejected(
    discover, tmp_path, monkeypatch, capsys
):
    """JSON array (not object) must be rejected gracefully."""
    fake_claude_dir = tmp_path / ".claude"
    plugins_dir = fake_claude_dir / "plugins"
    plugins_dir.mkdir(parents=True)
    plugins_file = plugins_dir / "installed_plugins.json"
    plugins_file.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    monkeypatch.setattr(discover, "get_claude_dir", lambda: fake_claude_dir)
    elements = discover.discover_plugins()
    assert elements == []
    captured = capsys.readouterr()
    assert "not a JSON object" in captured.err


def test_installed_plugins_missing_file_empty(discover, tmp_path, monkeypatch):
    """No installed_plugins.json → no plugins, no error."""
    fake_claude_dir = tmp_path / ".claude"
    (fake_claude_dir / "plugins").mkdir(parents=True)
    monkeypatch.setattr(discover, "get_claude_dir", lambda: fake_claude_dir)
    elements = discover.discover_plugins()
    assert elements == []


# ----------------------------------------------------------------------------
# Smoke tests
# ----------------------------------------------------------------------------


def test_safe_read_text_callsites_dont_raise(discover, tmp_path):
    """Smoke: discovery flows that touched read_text don't raise on empty fixtures."""
    fake_claude_dir = tmp_path / ".claude"
    fake_claude_dir.mkdir()
    # The discovery functions all handle missing files gracefully via _safe_read_text.
    # Just verify no exceptions on empty directories.
    elements_marketplaces = discover.discover_marketplaces()
    assert isinstance(elements_marketplaces, list)


def test_phase_1_1_constants_defined(discover, cozodb):
    """Smoke: required constants/symbols exist after edits."""
    assert hasattr(discover, "_safe_read_text")
    assert hasattr(discover, "DEFAULT_READ_CAP")
    assert hasattr(discover, "MANIFEST_READ_CAP")
    assert hasattr(cozodb, "count_skills")
    assert hasattr(cozodb, "db_is_healthy")
