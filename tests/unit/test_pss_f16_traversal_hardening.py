"""F16 + F17 (TRDD-1Z8SGQ7N): the remaining element-enumerating traversals must
not drop elements silently, and a non-UTF-8 element file must degrade rather
than vanish.

These tests pin the SAME decision rule F13 established, applied to the sites F13
did not reach:

  Record a scan error IFF the failure can make an on-disk element ABSENT from
  the emitted stream. A failure that only degrades metadata/description of an
  element that is still emitted MUST NOT record.

F16(a) — `_discover_marketplace_mcps`'s `os.walk` enumerates the config files
that BECOME MCP elements, but ran with `onerror=None`: os.walk DISCARDS the
error and yields nothing for that subtree, so an unreadable dir mimics "no MCP
servers here" while the coverage claim still stands.

F16(b) — the bare `.iterdir()` calls in discover_hooks/monitors/output_styles/
themes let an OSError PROPAGATE and abort the whole run. Fail-fast means no
wrong sweep, but a total scan outage. `_iterdir_safe` converts the outage into a
completed-but-non-exhaustive scan that still emits everything else.

F17 — element CONTENT is read with `errors="replace"`, so a non-UTF-8 element
(two cp1252 files exist in the wild) is EMITTED with mojibake instead of being
permanently invisible to discovery.

The anti-over-recording pin below is the other half: `_find_tool_names_in_source`
is ENRICHMENT (it scrapes tool names for an MCP descriptor; the MCP element is
emitted either way), so hardening its walk would permanently disable removal
detection for zero benefit. That test exists to stop exactly that "fix".

Conventions follow tests/unit/test_pss_f13_scan_error_routing.py: the real module
functions are called with get_claude_dir/get_cwd monkeypatched to tmp_path (never
~/.claude), _scan_errors cleared per test. No mocks of the code under test.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pss_discover  # noqa: E402

# chmod 000 is inert on Windows and as root — the read succeeds and the
# scenario under test (unreadable directory) never materializes.
needs_working_chmod = pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="chmod 000 does not deny reads on Windows or as root",
)


def _make_unreadable(path: Path, request: pytest.FixtureRequest) -> None:
    """chmod 000 with a finalizer restoring perms so tmp_path cleanup and
    debugging stay painless."""
    path.chmod(0)
    request.addfinalizer(
        lambda: path.chmod(
            stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
        )
    )


@pytest.fixture()
def fake_claude_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway ~/.claude replacement wired into the module under test.

    get_cwd is redirected too: discover_output_styles reads `cwd / ".claude"`,
    which would otherwise reach into the real repo checkout.

    _scan_errors is cleared explicitly: in production the reset happens in
    get_all_element_locations(), which these direct unit calls bypass.
    """
    claude = tmp_path / ".claude"
    claude.mkdir()
    monkeypatch.setattr(pss_discover, "get_claude_dir", lambda: claude)
    monkeypatch.setattr(pss_discover, "get_cwd", lambda: tmp_path / "proj")
    pss_discover._scan_errors.clear()
    return claude


# ---------------------------------------------------------------------------
# F16(b): the three-level plugin-cache traversals must survive an unreadable
# directory at ANY level, and must shrink the claim when they do.
# ---------------------------------------------------------------------------

# Every discoverer that walks plugins/cache/<marketplace>/<plugin>/<version>/.
_CACHE_DISCOVERERS: list[tuple[str, Callable[[], list[dict[str, Any]]]]] = [
    ("discover_hooks", lambda: pss_discover.discover_hooks()),
    ("discover_monitors", lambda: pss_discover.discover_monitors()),
    ("discover_output_styles", lambda: pss_discover.discover_output_styles()),
    ("discover_themes", lambda: pss_discover.discover_themes()),
]

# Which level of the cache tree gets chmod 000. An unreadable plugin dir drops
# that plugin's elements just as surely as an unreadable marketplace dir does,
# so all three levels must be wired — not just the outermost.
_CACHE_DEPTHS = ["cache", "marketplace", "plugin"]


def _build_cache_tree(claude: Path) -> dict[str, Path]:
    """plugins/cache/<mp>/<plugin>/<version>/ — the shape all four discoverers
    walk. Returns the path of each level so a test can pick one to break."""
    cache = claude / "plugins" / "cache"
    marketplace = cache / "demo-mp"
    plugin = marketplace / "demo-plugin"
    version = plugin / "1.0.0"
    version.mkdir(parents=True)
    return {"cache": cache, "marketplace": marketplace, "plugin": plugin}


@needs_working_chmod
@pytest.mark.parametrize("depth", _CACHE_DEPTHS)
@pytest.mark.parametrize(
    "name,discoverer", _CACHE_DISCOVERERS, ids=[n for n, _ in _CACHE_DISCOVERERS]
)
def test_unreadable_plugin_cache_dir_records_instead_of_raising(
    name: str,
    discoverer: Callable[[], list[dict[str, Any]]],
    depth: str,
    fake_claude_dir: Path,
    request: pytest.FixtureRequest,
) -> None:
    """RED (F16b): an unreadable directory anywhere in plugins/cache must NOT
    abort the scan — it must be recorded and the run continue.

    Today the bare `.iterdir()` lets the PermissionError propagate out of the
    discoverer and kill the entire discovery process: every element from every
    OTHER scope is lost too. `_iterdir_safe` downgrades that total outage to a
    completed-but-non-exhaustive scan (claim -> [], so still no wrong sweep).
    """
    levels = _build_cache_tree(fake_claude_dir)
    broken = levels[depth]
    _make_unreadable(broken, request)

    elements = discoverer()  # must not raise

    assert isinstance(elements, list)
    assert pss_discover._scan_errors, (
        f"{name}: an unreadable {depth} dir under plugins/cache dropped every "
        f"element beneath it without shrinking the coverage claim (F16b)"
    )
    # The recorded error must name the dir we actually broke — otherwise the
    # test could pass on an unrelated incidental error and prove nothing.
    assert any(str(broken) in err for err in pss_discover._scan_errors), (
        f"{name}: expected a scan error naming {broken}, got "
        f"{pss_discover._scan_errors}"
    )


# ---------------------------------------------------------------------------
# F16(a): the marketplace MCP walk enumerates element-bearing config files.
# ---------------------------------------------------------------------------


@needs_working_chmod
def test_unreadable_marketplace_subdir_records_scan_error(
    fake_claude_dir: Path, request: pytest.FixtureRequest
) -> None:
    """RED (F16a): _discover_marketplace_mcps walks the marketplaces tree for
    the .mcp.json/mcp.json/plugin.json files that BECOME MCP elements.

    os.walk's default onerror=None DISCARDS the error and simply yields nothing
    for the unreadable subtree — byte-for-byte identical to "this marketplace
    ships no MCP servers". The claim survives, so the real MCP elements sweep
    Removed. Element-dropping => must record.
    """
    marketplaces = fake_claude_dir / "plugins" / "marketplaces"
    hidden = marketplaces / "demo-mp" / "secret-plugin"
    hidden.mkdir(parents=True)
    (hidden / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"vanished": {"command": "node", "args": []}}}),
        encoding="utf-8",
    )
    _make_unreadable(hidden, request)

    servers = pss_discover._discover_marketplace_mcps(seen_names=set())

    assert isinstance(servers, list)
    assert pss_discover._scan_errors, (
        "an unreadable marketplace subdir silently mimicked 'no MCP servers "
        "here' while the coverage claim still stood (F16a)"
    )
    assert any(str(hidden) in err for err in pss_discover._scan_errors), (
        f"expected a scan error naming {hidden}, got {pss_discover._scan_errors}"
    )
    assert not any(s["name"] == "vanished" for s in servers), (
        "the locked subtree must really be unreadable for this test to mean "
        "anything — os.walk yields nothing for it, which is the bug being fixed"
    )


def test_walk_error_handler_suppresses_enoent_but_records_unreadable(
    fake_claude_dir: Path,
) -> None:
    """Both halves of the os.walk onerror decision, on the real handler.

    (fake_claude_dir is taken only for its _scan_errors.clear() — this test
    asserts on an EMPTY error set, so leakage from a prior test would mask a
    real regression.)

    The rule is an IFF: record iff the failure can make an ON-DISK element
    ABSENT from the stream.

    - ENOENT: the directory no longer exists, so it holds no on-disk element
      and nothing can be absent => MUST NOT record. os.walk scandirs a parent
      then descends into each child it listed; a child deleted inside that
      window raises FileNotFoundError to onerror. On a real machine a
      marketplace being re-cloned by a concurrent plugin update (rmdir+mkdir)
      hit this on a measured ~8-40% of runs, and recording it dropped the
      coverage claim for the WHOLE run — F7's outage returning through the back
      door. The F7 walk over this same tree already suppresses exactly this
      ENOENT via its `is_dir()` re-check (is_dir() returns False and never
      raises for a vanished dir), so suppressing it here matches shipped
      behaviour rather than unilaterally tightening it.
    - EACCES: the directory IS on disk and its elements are real but invisible
      => MUST record. This is the drop F16(a) exists to catch.

    Driven with real exception instances against the real handler — the wiring
    of the handler INTO os.walk is pinned separately by the chmod test above,
    which exercises the genuine EACCES path end to end.
    """
    pss_discover._record_walk_error(
        FileNotFoundError(2, "No such file or directory", "/gone/mid-walk")
    )
    assert not pss_discover._scan_errors, (
        "a directory deleted mid-walk holds no on-disk element, so nothing can "
        "be ABSENT from the stream — recording it violates the rule's IFF and "
        "disables removal detection for the whole run"
    )

    pss_discover._record_walk_error(
        PermissionError(13, "Permission denied", "/locked/but/present")
    )
    assert any("/locked/but/present" in e for e in pss_discover._scan_errors), (
        "an unreadable but PRESENT directory hides real on-disk elements — "
        "that drop must shrink the claim (F16a)"
    )


# ---------------------------------------------------------------------------
# The other half of the rule: enrichment traversals must NOT record.
# ---------------------------------------------------------------------------


@needs_working_chmod
def test_tool_name_scrape_traversal_failure_does_not_record(
    fake_claude_dir: Path, tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """ANTI-OVER-RECORDING PIN — do not "harden" _find_tool_names_in_source.

    Its os.walk scrapes tool NAMES out of .ts/.py/.js to enrich an MCP server's
    descriptor. The MCP element is emitted either way, so an unreadable subdir
    here degrades metadata only. Adding onerror=_record_scan_error would make
    one permanently-unreadable vendor directory permanently disable removal
    detection machine-wide — the exact over-recording bug the F13 rule forbids.

    This test fails the moment someone adds onerror= to that walk.
    """
    plugin_dir = tmp_path / "mcp-plugin"
    src = plugin_dir / "src"
    src.mkdir(parents=True)
    (src / "server.ts").write_text(
        'server.tool("visible_tool", {})\n', encoding="utf-8"
    )
    locked = plugin_dir / "vendor"
    locked.mkdir()
    (locked / "hidden.ts").write_text(
        'server.tool("hidden_tool", {})\n', encoding="utf-8"
    )
    _make_unreadable(locked, request)

    tools = pss_discover._find_tool_names_in_source(plugin_dir)  # must not raise

    assert "visible_tool" in tools, "the readable source must still be scraped"
    # Proves the traversal really did hit the unreadable dir — without this the
    # test could pass vacuously (e.g. if chmod silently had no effect) and would
    # stop guarding anything.
    assert "hidden_tool" not in tools, (
        "the locked dir must actually be unreadable for this pin to mean "
        "anything — os.walk swallowed it, which is the behaviour under test"
    )
    assert not pss_discover._scan_errors, (
        "an enrichment-only traversal failure must NOT shrink the coverage "
        "claim — the MCP element is emitted regardless, so recording here "
        "would permanently disable removal detection (F13 rule, second half)"
    )


# ---------------------------------------------------------------------------
# F17: a non-UTF-8 element degrades (mojibake description) instead of dropping.
# ---------------------------------------------------------------------------

# 0x92 is a cp1252 right-single-quote — invalid as a UTF-8 continuation byte.
CP1252_SKILL = b"---\nname: broken\ndescription: smart\x92quote\n---\n\nbody\n"
CP1252_MD = b"---\ndescription: smart\x92quote\n---\n\nbody\n"


def test_non_utf8_skill_is_emitted_not_dropped(
    fake_claude_dir: Path, tmp_path: Path
) -> None:
    """RED (F17), SKILL.md branch: a cp1252 SKILL.md must be EMITTED.

    Before F17 the strict decode raised UnicodeDecodeError past _safe_read_text
    (a UnicodeDecodeError is a ValueError, not an OSError, so _safe_read_text's
    `except OSError` does not catch it) and the element was skipped — silently
    invisible to discovery FOREVER, since the encoding is a permanent property
    of the file, not a transient failure. Degrading (mojibake description) beats
    dropping. Still no scan error: the element is emitted, so nothing sweeps.
    """
    skills_dir = tmp_path / "skills"
    (skills_dir / "broken").mkdir(parents=True)
    (skills_dir / "broken" / "SKILL.md").write_bytes(CP1252_SKILL)
    (skills_dir / "healthy").mkdir()
    (skills_dir / "healthy" / "SKILL.md").write_text(
        "---\nname: healthy\ndescription: fine\n---\n\nbody\n", encoding="utf-8"
    )

    elements = pss_discover.discover_elements([("user", "skill", skills_dir)])

    names = [e["name"] for e in elements]
    assert "healthy" in names, "one bad file must not abort the directory"
    assert "broken" in names, (
        "a non-UTF-8 SKILL.md must degrade to a mojibake description, not "
        "vanish from discovery permanently (F17)"
    )
    broken = next(e for e in elements if e["name"] == "broken")
    assert "�" in broken["description"], (
        "the undecodable byte must survive as U+FFFD REPLACEMENT CHARACTER — "
        "proof the content was actually read, not defaulted to empty"
    )
    assert not pss_discover._scan_errors, (
        "the element is emitted, so nothing drops and the claim must stand"
    )


def test_non_utf8_md_element_is_emitted_not_dropped(
    fake_claude_dir: Path, tmp_path: Path
) -> None:
    """RED (F17), plain-.md branch: same guarantee for agents/commands/rules."""
    cmd_dir = tmp_path / "commands"
    cmd_dir.mkdir()
    (cmd_dir / "broken.md").write_bytes(CP1252_MD)
    (cmd_dir / "healthy.md").write_text(
        "---\ndescription: fine\n---\n\nbody\n", encoding="utf-8"
    )

    elements = pss_discover.discover_elements([("user", "command", cmd_dir)])

    names = [e["name"] for e in elements]
    assert "healthy" in names, "one bad file must not abort the directory"
    assert "broken" in names, (
        "a non-UTF-8 command .md must degrade, not vanish permanently (F17)"
    )
    broken = next(e for e in elements if e["name"] == "broken")
    assert "�" in broken["description"], (
        "the undecodable byte must survive as U+FFFD — proof of a real read"
    )
    assert not pss_discover._scan_errors, (
        "the element is emitted, so nothing drops and the claim must stand"
    )
