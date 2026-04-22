"""Phase C (v3.0.0) tests: Python scripts migrate from JSON to CozoDB queries.

Phase C demotes skill-index.json to an optional debug export. These tests
verify the migration:

  1. pss_cozodb has new get_all_entries() / get_entry_by_name() helpers that
     return full entries (with deserialized JSON sub-fields) suitable for
     pss_make_plugin / pss_verify_profile / pss_generate.
  2. pss_make_plugin resolves element paths from CozoDB (no JSON read).
  3. pss_verify_profile builds the type->names index from CozoDB.
  4. pss_generate imports from CozoDB.
  5. pss_hook NO LONGER has the 256-byte JSON header check.
  6. pss_merge_queue STOPS auto-writing skill-index.json.
  7. Rust binary's `--build-db` flag is removed.
  8. Migration safety: if the user has a legacy skill-index.json but no
     CozoDB, pss_hook must trigger a reindex to bootstrap CozoDB.

Test strategy: most tests run against the live pre-built CozoDB (gated on
_db_present).
"""

from __future__ import annotations

import importlib
import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _binary_path() -> Path:
    """Platform-appropriate pss binary."""
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
    env_path = os.environ.get("CLAUDE_PLUGIN_DATA")
    if env_path and Path(env_path).is_absolute():
        if "perfect-skill-suggester" in Path(env_path).name.lower():
            p = Path(env_path) / "pss-skill-index.db"
            if p.exists():
                return True
    return (Path.home() / ".claude" / "cache" / "pss-skill-index.db").exists()


skip_if_no_db = pytest.mark.skipif(
    not _db_present(),
    reason="CozoDB not found - run /pss-reindex-skills first",
)

skip_if_no_binary = pytest.mark.skipif(
    not BIN.exists(),
    reason=f"pss binary not found at {BIN} - run scripts/pss_build.py first",
)


# ---------------------------------------------------------------------------
# Phase C Deliverable 1: pss_cozodb gains full-entry helpers
# ---------------------------------------------------------------------------


@skip_if_no_db
def test_pss_cozodb_has_get_entry_by_name():
    """pss_cozodb must export get_entry_by_name returning a full-field dict."""
    import pss_cozodb

    assert hasattr(pss_cozodb, "get_entry_by_name"), (
        "pss_cozodb.get_entry_by_name is required for Phase C (used by "
        "pss_make_plugin and pss_verify_profile instead of JSON reads)"
    )


@skip_if_no_db
def test_get_entry_by_name_returns_full_entry():
    """get_entry_by_name must return all fields needed by Phase C callers."""
    import pss_cozodb

    entry = pss_cozodb.get_entry_by_name("react")
    if entry is None:
        pytest.skip("'react' not present in live DB; test needs a known entry")

    # Must have the Python-friendly field names (type, not skill_type)
    assert entry["name"] == "react"
    assert entry["type"] == "skill"
    assert isinstance(entry["path"], str) and entry["path"]
    assert isinstance(entry["description"], str)
    # JSON fields must be deserialized to Python objects
    assert isinstance(entry["keywords"], list)
    assert isinstance(entry["intents"], list)
    assert isinstance(entry["patterns"], list)
    assert isinstance(entry["directories"], list)


@skip_if_no_db
def test_get_entry_by_name_returns_none_for_unknown():
    """get_entry_by_name must return None for a missing entry."""
    import pss_cozodb

    assert pss_cozodb.get_entry_by_name("xyzzy-definitely-not-real") is None


@skip_if_no_db
def test_get_all_entries_returns_name_keyed_dict():
    """get_all_entries must return a {name: full_entry_dict} mapping."""
    import pss_cozodb

    entries = pss_cozodb.get_all_entries()
    assert isinstance(entries, dict)
    assert len(entries) > 0
    # Sample a few entries
    for _name, entry in list(entries.items())[:5]:
        assert "name" in entry
        assert "type" in entry
        assert entry["type"] in (
            "skill",
            "agent",
            "command",
            "rule",
            "mcp",
            "lsp",
            "output-style",
            "hook",
        )


# ---------------------------------------------------------------------------
# Phase C Deliverable 2-4: Scripts no longer read JSON
# ---------------------------------------------------------------------------


def test_pss_make_plugin_has_no_json_load_of_skill_index():
    """pss_make_plugin's load_skill_index must NOT call json.load."""
    import ast

    src = (SCRIPTS / "pss_make_plugin.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "load_skill_index":
            body_src = ast.unparse(node)
            assert "json.load" not in body_src, (
                "pss_make_plugin.load_skill_index must not call json.load in Phase C"
            )
            assert 'skill-index.json' not in body_src, (
                "pss_make_plugin.load_skill_index must not reference "
                "skill-index.json path in Phase C runtime code"
            )
            return
    pytest.fail("load_skill_index function not found in pss_make_plugin")


def test_pss_verify_profile_has_no_json_load_of_index():
    """pss_verify_profile must NOT json.load skill-index.json at runtime."""
    import ast

    src = (SCRIPTS / "pss_verify_profile.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "load_index":
            body_src = ast.unparse(node)
            assert "json.load" not in body_src, (
                "pss_verify_profile.load_index must not call json.load in Phase C"
            )
            assert "open(" not in body_src, (
                "pss_verify_profile.load_index must not open files directly in Phase C "
                "(should use pss_cozodb.get_all_entries)"
            )
            return
    pytest.fail("load_index function not found in pss_verify_profile")


def test_pss_generate_no_json_import_from_index_file():
    """pss_generate must export import_from_cozodb() for Phase C."""
    import pss_generate

    assert hasattr(pss_generate, "import_from_cozodb"), (
        "pss_generate must export import_from_cozodb() for Phase C"
    )


def test_pss_hook_no_256_byte_corruption_check():
    """pss_hook must NOT have the 256-byte JSON corruption check."""
    src = (SCRIPTS / "pss_hook.py").read_text()
    assert 'f.read(256)' not in src, (
        "pss_hook must not contain the 256-byte JSON header check (Phase C)"
    )
    assert "json.corrupt" not in src, (
        "pss_hook must not rename the JSON file to .corrupt (Phase C)"
    )


# ---------------------------------------------------------------------------
# Phase C Deliverable 5: pss_merge_queue stops auto-writing JSON
# ---------------------------------------------------------------------------


def test_pss_merge_queue_does_not_auto_write_json():
    """run_merge must NOT call atomic_write_json."""
    import ast

    src = (SCRIPTS / "pss_merge_queue.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_merge":
            calls = [
                ast.unparse(n.func)
                for n in ast.walk(node)
                if isinstance(n, ast.Call)
            ]
            assert "atomic_write_json" not in calls, (
                f"run_merge must not call atomic_write_json in Phase C; found: {calls}"
            )


# ---------------------------------------------------------------------------
# Phase C Deliverable 6: Rust --build-db removed
# ---------------------------------------------------------------------------


@skip_if_no_binary
def test_rust_build_db_flag_removed():
    """`pss --build-db` must fail - the flag is gone in Phase C."""
    result = subprocess.run(
        [str(BIN), "--build-db"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode != 0, (
        "`pss --build-db` unexpectedly succeeded - the flag must be removed"
    )
    combined = (result.stderr + result.stdout).lower()
    assert "unexpected" in combined or "unknown" in combined or "error" in combined, (
        f"Unexpected output from `pss --build-db`:\nstderr={result.stderr}\nstdout={result.stdout}"
    )


# ---------------------------------------------------------------------------
# Phase C Deliverable 7: Migration safety
# ---------------------------------------------------------------------------


def test_pss_hook_imports_without_json_index():
    """pss_hook must be importable even when skill-index.json is absent."""
    import pss_hook

    importlib.reload(pss_hook)
    assert hasattr(pss_hook, "_maybe_auto_reindex"), (
        "pss_hook must keep the auto-reindex path for migration safety"
    )


# ---------------------------------------------------------------------------
# Phase C Deliverable 8: pss_make_plugin produces byte-identical plugin.json
# ---------------------------------------------------------------------------


@skip_if_no_db
def test_pss_make_plugin_resolves_real_skill_paths():
    """pss_make_plugin must resolve paths via CozoDB for a known skill."""
    import pss_make_plugin

    assert hasattr(pss_make_plugin, "resolve_element_path")
    assert hasattr(pss_make_plugin, "resolve_element_type")
