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


def test_detected_binary_name_exists_in_bin_for_this_host(e2e) -> None:
    """The name the harness resolves must be a binary this repo actually ships."""
    name = e2e.detect_platform_binary()

    assert name.startswith("pss-")
    shipped = PROJECT_ROOT / "bin" / name
    assert shipped.exists(), f"detect_platform_binary() returned {name}, absent from bin/"
    # And find_binary() must agree with it when pointed at the real plugin root.
    assert e2e.find_binary(PROJECT_ROOT) == shipped


def test_missing_binary_raises_with_the_build_command_in_the_message(
    e2e, tmp_path: Path
) -> None:
    """A bare plugin root fails fast and tells the caller exactly how to fix it."""
    with pytest.raises(FileNotFoundError) as exc:
        e2e.find_binary(tmp_path)

    message = str(exc.value)
    assert "pss_build.py" in message, "error must name the build script"
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
