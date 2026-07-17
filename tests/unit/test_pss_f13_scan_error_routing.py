"""F13 (TRDD-1Z8SGQ7N): element-dropping I/O failures in the type-specific
discoverers must shrink the F7 coverage claim.

F7 wired only the scope-root enumeration in get_all_element_locations into
_record_scan_error. The type-specific discoverers (discover_plugins,
discover_marketplaces, discover_hooks, ...) have their own `except OSError:
continue|return` paths: a read failure there silently DROPS elements from the
emitted stream while `exhaustive_scopes` still stands, so the consumer sweeps
the dropped elements as Removed — spurious churn in an append-only history.

The rule these tests pin (both halves):
  - a failure that makes an on-disk element ABSENT from the stream MUST call
    _record_scan_error (claim drops);
  - a failure that only degrades metadata/description (element still emitted)
    MUST NOT record (otherwise one permanently-unreadable optional file
    permanently disables removal detection — F7's outage from the other side).

Conventions follow tests/unit/test_pss_f7_scan_coverage.py: the end-to-end
tests drive the REAL script via subprocess against a fixture HOME; the unit
tests call the real module functions with get_claude_dir monkeypatched to
tmp_path (never ~/.claude). No mocks of the code under test.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pss_discover  # noqa: E402

DISCOVER = SCRIPTS / "pss_discover.py"

# chmod 000 is inert on Windows and as root — the read succeeds and the
# scenario under test (unreadable file) never materializes.
needs_working_chmod = pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod 000 does not deny reads on Windows or as root",
)


def _make_unreadable(path: Path, request: pytest.FixtureRequest) -> None:
    """chmod 000 with a finalizer restoring perms so tmp_path cleanup and
    debugging stay painless."""
    path.chmod(0)
    request.addfinalizer(
        lambda: path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    )


@pytest.fixture()
def fake_claude_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway ~/.claude replacement wired into the module under test.

    _scan_errors is cleared explicitly: in production the reset happens in
    get_all_element_locations(), which these direct unit calls bypass.
    """
    claude = tmp_path / ".claude"
    claude.mkdir()
    monkeypatch.setattr(pss_discover, "get_claude_dir", lambda: claude)
    pss_discover._scan_errors.clear()
    return claude


# ---------------------------------------------------------------------------
# Half 1 of the rule: dropping-shaped failures MUST record.
# ---------------------------------------------------------------------------


@needs_working_chmod
def test_unreadable_installed_plugins_records_scan_error(
    fake_claude_dir: Path, request: pytest.FixtureRequest
) -> None:
    """RED/regression: installed_plugins.json present but unreadable drops the
    ENTIRE plugin container (all install entries vanish in one scan) — the
    coverage claim must shrink, so _scan_errors must become non-empty.

    Mechanically the unreadable file surfaces as json.JSONDecodeError, not
    OSError: _safe_read_text swallows the PermissionError and returns None,
    and json.loads(None or "") raises JSONDecodeError — the wired handler
    must record for BOTH exception arms.
    """
    plugins_dir = fake_claude_dir / "plugins"
    plugins_dir.mkdir()
    plugins_file = plugins_dir / "installed_plugins.json"
    plugins_file.write_text(
        json.dumps({"version": 2, "plugins": {"demo@mp": []}}), encoding="utf-8"
    )
    _make_unreadable(plugins_file, request)

    elements = pss_discover.discover_plugins()

    assert elements == [], "unreadable container must yield no plugin elements"
    assert pss_discover._scan_errors, (
        "an unreadable installed_plugins.json silently dropped every plugin "
        "element without shrinking the coverage claim (F13)"
    )


@needs_working_chmod
def test_unreadable_known_marketplaces_records_scan_error(
    fake_claude_dir: Path, request: pytest.FixtureRequest
) -> None:
    """Same container-drop shape for known_marketplaces.json /
    discover_marketplaces(): every marketplace element vanishes while the
    claim stands unless the failure is recorded."""
    plugins_dir = fake_claude_dir / "plugins"
    plugins_dir.mkdir()
    mp_file = plugins_dir / "known_marketplaces.json"
    mp_file.write_text(
        json.dumps({"emasoft-plugins": {"source": {"source": "github"}}}),
        encoding="utf-8",
    )
    _make_unreadable(mp_file, request)

    elements = pss_discover.discover_marketplaces()

    assert elements == [], "unreadable container must yield no marketplace elements"
    assert pss_discover._scan_errors, (
        "an unreadable known_marketplaces.json silently dropped every "
        "marketplace element without shrinking the coverage claim (F13)"
    )


# ---------------------------------------------------------------------------
# Half 2 of the rule: enrichment-shaped failures MUST NOT record.
# ---------------------------------------------------------------------------


@needs_working_chmod
def test_unreadable_theme_body_still_emits_element_without_scan_error(
    fake_claude_dir: Path, request: pytest.FixtureRequest
) -> None:
    """Anti-over-recording pin: in _discover_styled_files_in_dir the per-file
    read only feeds the DESCRIPTION — the element is appended regardless. An
    unreadable theme file must still emit its element AND leave _scan_errors
    empty; wiring this site would let one permanently-unreadable optional
    file permanently disable removal detection machine-wide."""
    themes_dir = fake_claude_dir / "themes"
    themes_dir.mkdir()
    theme_file = themes_dir / "midnight.json"
    theme_file.write_text('{"description": "a dark theme"}', encoding="utf-8")
    _make_unreadable(theme_file, request)

    elements = pss_discover.discover_themes()

    names = [e["name"] for e in elements]
    assert "midnight" in names, "enrichment failure must not drop the element"
    theme = next(e for e in elements if e["name"] == "midnight")
    assert theme["description"] == "", "unreadable body degrades to empty description"
    assert not pss_discover._scan_errors, (
        "an enrichment-only failure (element still emitted) must NOT shrink "
        "the coverage claim — over-recording permanently disables removal "
        "detection (F13 decision rule, second half)"
    )


def test_non_utf8_element_file_drops_without_scan_error(
    fake_claude_dir: Path, tmp_path: Path
) -> None:
    """Pin of a DELIBERATE deviation from the rule's letter (see the report's
    classification table, sites L1839/L1905): a non-UTF-8 element .md is
    dropped from the stream, yet must NOT record. Its unreadability is a
    PERMANENT content property — recording it would keep the coverage claim
    off forever on any machine hosting one such third-party file (two exist
    on the machine this was developed on), while the never-emitted element
    causes no Removed churn. The healthy sibling must survive the loop."""
    cmd_dir = tmp_path / "commands"
    cmd_dir.mkdir()
    (cmd_dir / "broken.md").write_bytes(
        b"---\ndescription: smart\x92quote\n---\n\nbody\n"  # 0x92 = cp1252
    )
    (cmd_dir / "healthy.md").write_text(
        "---\ndescription: fine\n---\n\nbody\n", encoding="utf-8"
    )

    elements = pss_discover.discover_elements([("user", "command", cmd_dir)])

    names = [e["name"] for e in elements]
    assert "healthy" in names, "one bad file must not abort the directory"
    assert "broken" not in names, "non-UTF-8 element is dropped (current design)"
    assert not pss_discover._scan_errors, (
        "a permanently non-UTF-8 element file must not permanently disable "
        "removal detection (F13 over-recording guard)"
    )


# ---------------------------------------------------------------------------
# End-to-end: the claim on the manifest line, via the real subprocess.
# ---------------------------------------------------------------------------


def _build_fixture_home(tmp_path: Path) -> Path:
    """A minimal HOME whose scan yields >=1 element and a valid v2 plugin
    container. element_count must be > 0: an empty scan forces the claim to []
    unconditionally, which would mask the failure this test targets."""
    home = tmp_path / "home"
    claude = home / ".claude"
    skill_dir = claude / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: fixture skill for F13\n---\n\nBody.\n",
        encoding="utf-8",
    )
    plugins_dir = claude / "plugins"
    plugins_dir.mkdir(parents=True)
    (plugins_dir / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {}}), encoding="utf-8"
    )
    return home


def _run_discover_with_home(home: Path, cwd: Path) -> dict:
    """Run the real discoverer against a fixture HOME; return the manifest."""
    proc = subprocess.run(
        [sys.executable, str(DISCOVER), "--jsonl"],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        timeout=600,
    )
    assert proc.returncode == 0, f"discover failed: {proc.stderr[-2000:]}"
    manifest = json.loads(proc.stdout.split("\n", 1)[0])
    assert manifest.get("_pss_manifest") is True, "first line must be the manifest"
    return manifest


def test_e2e_readable_fixture_claims_scopes(tmp_path: Path) -> None:
    """Control: with every container readable, a plain --jsonl run over the
    fixture claims user/plugin/marketplace (the F7 mapping for plain runs)."""
    home = _build_fixture_home(tmp_path)
    manifest = _run_discover_with_home(home, cwd=tmp_path)
    assert manifest["element_count"] >= 1, "fixture must yield at least one element"
    assert set(manifest["exhaustive_scopes"]) == {"user", "plugin", "marketplace"}


@needs_working_chmod
def test_e2e_unreadable_installed_plugins_drops_claim(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """RED/regression, end to end: the SAME fixture with an unreadable
    installed_plugins.json must emit `exhaustive_scopes: []` — the scan is not
    exhaustive, so no scope may be swept."""
    home = _build_fixture_home(tmp_path)
    plugins_file = home / ".claude" / "plugins" / "installed_plugins.json"
    _make_unreadable(plugins_file, request)

    manifest = _run_discover_with_home(home, cwd=tmp_path)
    assert manifest["element_count"] >= 1, (
        "the skill must survive — only the plugin container is unreadable"
    )
    assert manifest["exhaustive_scopes"] == [], (
        "a scan that silently dropped the whole plugin container must not "
        "claim ANY scope exhaustive (F13)"
    )
