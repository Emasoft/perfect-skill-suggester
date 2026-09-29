"""Tests for scripts/pss_test_e2e.py — the e2e harness's own safety rails.

`_isolated_env` exists because the harness once wrote its fixture skills into the
user's REAL ~/.claude/cache/pss-skill-index.db and clobbered the live index (the
2026-05-08 hook timeout). Its HOME redirect and CLAUDE_PLUGIN_DATA scrub are the
whole defence, and its guard clause is what catches a future refactor that hands
it a non-isolated home. That guard is asserted here for real — with an actual
path under $HOME, not a stand-in.

The six pipeline phases themselves are the e2e run (they build a temp index and
shell out to the Rust binary); this module covers the platform/isolation logic
they all sit on, not a second copy of the pipeline.
"""

from __future__ import annotations

import importlib.util
import os
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
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def e2e():
    """Load pss_test_e2e.py without running its CLI."""
    return _load_module("pss_test_e2e_under_test", SCRIPTS_DIR / "pss_test_e2e.py")


def test_detected_binary_name_resolves_for_this_host(e2e) -> None:
    """The resolved name is a real binary reachable via the store or repo bin/.

    Since TRDD-YC51I1C0 phase 3, bin/pss-* is gitignored — binaries come from
    the fetched store (~/.claude/cache/pss-bin/current) or a local build. The
    old premise (must exist in repo bin/) is dead; what must hold is that
    find_binary() resolves SOMETHING executable on a machine that has either.
    On a machine with NEITHER, find_binary raises — that path is the next test,
    which isolates HOME so the store tier misses deterministically.
    """
    name = e2e.detect_platform_binary()
    assert name.startswith("pss-")

    store_copy = Path.home() / ".claude" / "cache" / "pss-bin" / "current" / name
    repo_copy = PROJECT_ROOT / "bin" / name
    if store_copy.exists() or repo_copy.exists():
        resolved = e2e.find_binary(PROJECT_ROOT)
        assert resolved.name == name
        assert resolved.exists()
    else:
        with pytest.raises(FileNotFoundError):
            e2e.find_binary(PROJECT_ROOT)


def test_missing_binary_raises_with_the_fetch_command_in_the_message(
    e2e, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No binary anywhere (store isolated, empty plugin root) fails fast with the fix."""
    # HOME redirect takes the store tier (~/.claude/cache/pss-bin) out of play;
    # PSS_BINARY_DIR unset keeps the operator-escape tier out of play.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("PSS_BINARY_DIR", raising=False)
    (tmp_path / "home").mkdir()
    with pytest.raises(FileNotFoundError) as exc:
        e2e.find_binary(tmp_path)

    message = str(exc.value)
    assert "pss_fetch_binaries.py" in message, "error must name the fetcher"
    assert str(tmp_path) in message, "error must name the path it looked in"


def test_isolated_env_redirects_home_and_scrubs_the_plugin_data_var(
    e2e, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Child processes get the sandbox HOME and cannot reach the real plugin data dir."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", "/real/plugin/data")

    child_env = e2e._isolated_env({"fake_home": fake_home})

    assert child_env["HOME"] == str(fake_home)
    assert "CLAUDE_PLUGIN_DATA" not in child_env
    # The caller's own environment must be left untouched.
    assert os.environ["CLAUDE_PLUGIN_DATA"] == "/real/plugin/data"


def test_isolated_env_refuses_a_home_that_is_not_actually_isolated(e2e) -> None:
    """A fake_home sitting directly under the real $HOME would clobber the user's cache."""
    unsafe = Path(os.path.expanduser("~")) / "pss-fake-home"

    with pytest.raises(RuntimeError) as exc:
        e2e._isolated_env({"fake_home": unsafe})

    assert "not isolated" in str(exc.value)
