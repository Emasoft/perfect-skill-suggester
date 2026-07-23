"""Tests for scripts/pss_setup.py — platform detection and installation checks.

`detect_platform` / `get_binary_name` decide which prebuilt binary the plugin
loads. A wrong answer is not a soft failure: the setup either builds nothing or
reports a missing binary that is actually present under a different name. The
arch-alias folding and the Android special-case are pure logic and are driven
here with the real `platform` module readings substituted (the substitution is
the *input*, not the code under test).

The health checks are run against the REAL repository — that is the only way to
prove they agree with what the plugin actually ships. Checks that need a built
CozoDB index or a Rust toolchain (`check_skill_index`, `check_rust_installed`,
`build_binary`) are environment-dependent and deliberately not asserted on.
"""

from __future__ import annotations

import importlib.util
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


@pytest.fixture
def setup_mod():
    """Load pss_setup.py without running its CLI."""
    return _load_module("pss_setup_under_test", SCRIPTS_DIR / "pss_setup.py")


def _fake_platform(mod, monkeypatch: pytest.MonkeyPatch, system: str, machine: str) -> None:
    """Feed a specific uname reading to detect_platform (input substitution only)."""
    monkeypatch.setattr(mod.platform, "system", lambda: system)
    monkeypatch.setattr(mod.platform, "machine", lambda: machine)


def test_arch_aliases_fold_onto_the_names_used_in_bin(
    setup_mod, monkeypatch: pytest.MonkeyPatch
) -> None:
    """aarch64→arm64 and amd64→x86_64, so the lookup matches the shipped filenames."""
    monkeypatch.delenv("ANDROID_ROOT", raising=False)
    monkeypatch.delenv("TERMUX_VERSION", raising=False)

    _fake_platform(setup_mod, monkeypatch, "Linux", "aarch64")
    assert setup_mod.detect_platform() == ("linux", "arm64")
    assert setup_mod.get_binary_name() == "pss-linux-arm64"

    _fake_platform(setup_mod, monkeypatch, "Windows", "AMD64")
    assert setup_mod.detect_platform() == ("windows", "x86_64")
    assert setup_mod.get_binary_name() == "pss-windows-x86_64.exe", "missing .exe suffix"

    _fake_platform(setup_mod, monkeypatch, "Darwin", "arm64")
    assert setup_mod.get_binary_name() == "pss-darwin-arm64"


def test_android_is_split_out_from_linux_arm64_via_env_markers(
    setup_mod, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Termux reports linux/aarch64 but needs its own binary — the marker disambiguates."""
    _fake_platform(setup_mod, monkeypatch, "Linux", "aarch64")
    monkeypatch.delenv("ANDROID_ROOT", raising=False)
    monkeypatch.setenv("TERMUX_VERSION", "0.118.0")
    assert setup_mod.detect_platform() == ("android", "arm64")
    assert setup_mod.get_binary_name() == "pss-android-arm64"

    # The marker must not misfire on x86_64 Linux, which has no android build.
    _fake_platform(setup_mod, monkeypatch, "Linux", "x86_64")
    assert setup_mod.detect_platform() == ("linux", "x86_64")


def test_path_helpers_resolve_to_this_repository(setup_mod) -> None:
    """The plugin/rust/bin roots must point at real directories of this checkout."""
    assert setup_mod.get_plugin_root() == PROJECT_ROOT
    assert setup_mod.get_rust_dir() == PROJECT_ROOT / "rust" / "skill-suggester"
    assert setup_mod.get_bin_dir() == PROJECT_ROOT / "bin"
    assert setup_mod.get_bin_dir().is_dir()


def test_health_checks_pass_against_the_real_plugin(setup_mod, capsys) -> None:
    """hooks.json really registers UserPromptSubmit and the interpreter is supported."""
    assert setup_mod.check_python_version() is True
    assert setup_mod.check_hooks_configured() is True
    out = capsys.readouterr().out
    assert "Hooks configured (UserPromptSubmit)" in out


def test_broken_hooks_json_is_reported_not_swallowed(
    setup_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Corrupt JSON and a missing UserPromptSubmit both fail the check loudly."""
    fake_root = tmp_path / "plugin"
    (fake_root / "hooks").mkdir(parents=True)
    monkeypatch.setattr(setup_mod, "get_plugin_root", lambda: fake_root)

    # Missing file.
    assert setup_mod.check_hooks_configured() is False

    # Present but not valid JSON.
    (fake_root / "hooks" / "hooks.json").write_text("{not json", encoding="utf-8")
    assert setup_mod.check_hooks_configured() is False

    # Valid JSON, but the hook PSS depends on is not registered.
    (fake_root / "hooks" / "hooks.json").write_text('{"hooks": {"Stop": []}}', encoding="utf-8")
    assert setup_mod.check_hooks_configured() is False
