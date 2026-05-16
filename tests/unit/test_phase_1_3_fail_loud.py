"""Tests for Phase 1.3 fail-fast hygiene: V-3, V-4, V-5, V-8.

The 5-agent audit (20260514) flagged 5 callsites where a silent
`except Exception: return {}` pattern was masking real failures:

* V-3 — `search_by_name` Python-side LIKE fallback on Cozo rejection
* V-4 — `_snapshot_prior_timestamps` open-DB failure → silent {}
* V-5 — `_snapshot_prior_timestamps` query failure → silent {}
* V-8 — `parse_frontmatter` returns {} on broken YAML without warning

This file verifies the post-fix behaviour: errors are surfaced to stderr
(V-4/V-5/V-8) or raised (V-3), instead of being silently swallowed.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from contextlib import redirect_stderr
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture(scope="module")
def cozodb():
    spec = importlib.util.spec_from_file_location("pss_cozodb", _SCRIPTS / "pss_cozodb.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def discover():
    spec = importlib.util.spec_from_file_location("pss_discover", _SCRIPTS / "pss_discover.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ----------------------------------------------------------------------------
# V-8: parse_frontmatter
# ----------------------------------------------------------------------------


def test_v8_parse_frontmatter_malformed_yaml_writes_warning(discover):
    """V-8: malformed YAML frontmatter must emit a stderr warning."""
    content = "---\nfoo: : : :\n---\nbody"
    buf = io.StringIO()
    with redirect_stderr(buf):
        result = discover.parse_frontmatter(content, source_label="/fake/file.md")
    assert result == {}
    assert "malformed YAML frontmatter" in buf.getvalue()
    assert "/fake/file.md" in buf.getvalue()


def test_v8_parse_frontmatter_valid_yaml_no_warning(discover):
    """V-8: valid YAML must NOT emit a warning (negative case)."""
    content = "---\nname: foo\ndescription: bar\n---\nbody"
    buf = io.StringIO()
    with redirect_stderr(buf):
        result = discover.parse_frontmatter(content, source_label="/fake/file.md")
    assert result == {"name": "foo", "description": "bar"}
    assert buf.getvalue() == ""


def test_v8_parse_frontmatter_no_frontmatter_no_warning(discover):
    """V-8: missing frontmatter (no leading ---) returns {} without warning."""
    content = "just a body, no frontmatter"
    buf = io.StringIO()
    with redirect_stderr(buf):
        result = discover.parse_frontmatter(content, source_label="/fake/file.md")
    assert result == {}
    assert buf.getvalue() == ""


def test_v8_parse_frontmatter_unterminated_no_warning(discover):
    """V-8: leading --- without closing --- is treated as no-frontmatter, not a YAML error."""
    content = "---\nfoo: bar\n(no closing --- here)"
    buf = io.StringIO()
    with redirect_stderr(buf):
        result = discover.parse_frontmatter(content, source_label="/fake/file.md")
    assert result == {}
    # No closing fence means we never tried to parse YAML, so no warning.
    assert buf.getvalue() == ""


# ----------------------------------------------------------------------------
# V-4 / V-5: _snapshot_prior_timestamps
# ----------------------------------------------------------------------------


def test_v4_snapshot_missing_db_returns_empty_no_warning(cozodb, tmp_path):
    """V-4: when prior DB does not exist (first-ever reindex) return {} silently."""
    db_path = tmp_path / "nonexistent.db"
    buf = io.StringIO()
    with redirect_stderr(buf):
        result = cozodb._snapshot_prior_timestamps(db_path)
    assert result == {}
    assert buf.getvalue() == ""  # missing DB is not a corruption event


def test_v4_snapshot_corrupt_db_writes_warning(cozodb, tmp_path):
    """V-4: a corrupt prior DB must write a stderr warning before returning {}."""
    corrupt_db = tmp_path / "corrupt.db"
    corrupt_db.write_bytes(b"\x00\x00\x00 NOT A REAL SQLITE FILE \x00\x00")

    buf = io.StringIO()
    with redirect_stderr(buf):
        result = cozodb._snapshot_prior_timestamps(corrupt_db)

    assert result == {}
    warning = buf.getvalue()
    assert "PSS warning" in warning
    assert str(corrupt_db) in warning
    assert "first_indexed_at" in warning  # explains consequence


def test_v5_snapshot_schema_missing_writes_warning(cozodb, tmp_path):
    """V-5: a valid SQLite DB without the skills schema must warn (not crash)."""
    # Build a minimal valid SQLite file with no Cozo schema.
    import sqlite3

    db_path = tmp_path / "bare.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE foo (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    buf = io.StringIO()
    with redirect_stderr(buf):
        result = cozodb._snapshot_prior_timestamps(db_path)

    assert result == {}
    # The Cozo client may or may not open a non-Cozo SQLite file. Either
    # way, the function must NOT return {} silently — either an open
    # error OR a schema-missing error must surface.
    assert "PSS warning" in buf.getvalue()


# ----------------------------------------------------------------------------
# V-3: search_by_name (fail loud)
# ----------------------------------------------------------------------------


def test_v3_search_by_name_raises_on_cozo_rejection(cozodb, tmp_path, monkeypatch):
    """V-3: a Cozo query rejection must raise RuntimeError, not return [].

    Previously the function silently fell back to a Python-side filter
    after any Cozo exception — masking schema-drift bugs as "no results".
    """

    class BrokenClient:
        def run(self, *_args, **_kwargs):
            raise RuntimeError("Cozo schema rejected: missing column 'name'")

        def close(self):
            pass

    broken = BrokenClient()
    with pytest.raises(RuntimeError, match="search_by_name: Cozo query rejected"):
        cozodb.search_by_name("foo", db=broken)


def test_v3_search_by_name_no_silent_empty_on_error(cozodb):
    """V-3: the function must NOT return [] when Cozo errors."""

    class AlwaysFailClient:
        def run(self, *_args, **_kwargs):
            raise RuntimeError("simulated")

        def close(self):
            pass

    with pytest.raises(RuntimeError):
        cozodb.search_by_name("anything", db=AlwaysFailClient())
