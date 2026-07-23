"""Tests for scripts/pss_build_all.py — binary staging into bin/.

`_copy_binary` is the step that decides which file ships. Two of its behaviours
are load-bearing and were both written in response to real breakage:
  * it must find the artifact under the *workspace* target dir (cargo puts it
    there, not under the crate) and fall back to the crate dir;
  * it must use shutil.copy, NOT copy2, so the staged binary gets a fresh mtime
    — copy2 preserves the source mtime and publish.py's staleness check then
    flags a freshly built binary as stale.
Both are asserted against a real filesystem layout. The cargo/cross invocations
themselves are not run here (a 30-minute cross build is not a unit test); only
the dispatch guard that needs no toolchain is exercised.
"""

from __future__ import annotations

import importlib.util
import os
import stat
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
def builder():
    """Load pss_build_all.py without running its CLI."""
    return _load_module("pss_build_all_under_test", SCRIPTS_DIR / "pss_build_all.py")


def _make_crate(tmp_path: Path, *, rel: str, name: str) -> Path:
    """Create a fake built artifact at `rel` under the fake rust workspace."""
    crate_dir = tmp_path / "rust" / "skill-suggester"
    artifact = tmp_path / "rust" / rel / name
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"\x7fELF fake binary")
    crate_dir.mkdir(parents=True, exist_ok=True)
    return crate_dir


def test_target_table_matches_the_binaries_actually_shipped(builder) -> None:
    """Every TARGETS entry names a triple/tool and a bin/ artifact that exists."""
    known_tools = {"cargo", "cargo-cross", "zigbuild", "cross"}
    for target_name, info in builder.TARGETS.items():
        assert info["tool"] in known_tools, f"{target_name} uses an unknown build tool"
        assert info["triple"], f"{target_name} has no target triple"
        ext = ".exe" if "windows" in info["triple"] else ""
        shipped = PROJECT_ROOT / "bin" / f"pss-{target_name}{ext}"
        assert shipped.exists(), f"TARGETS names {target_name} but {shipped.name} is not in bin/"

    assert set(builder.BINARIES) == {"pss", "pss-nlp"}


def test_copy_stages_from_the_workspace_target_dir_with_a_fresh_mtime(
    builder, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The native artifact is copied to bin/ 0755 and does NOT inherit the source mtime."""
    crate_dir = _make_crate(tmp_path, rel="target/release", name="pss")
    src = tmp_path / "rust" / "target" / "release" / "pss"
    os.utime(src, (100_000, 100_000))  # ancient mtime — copy2 would preserve it

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setattr(builder, "BIN_DIR", bin_dir)

    dest = builder._copy_binary(crate_dir, "pss", "pss", "darwin-arm64", "aarch64-apple-darwin")

    assert dest == bin_dir / "pss-darwin-arm64"
    assert dest.read_bytes() == b"\x7fELF fake binary"
    assert dest.stat().st_mtime > src.stat().st_mtime, "staged binary inherited a stale mtime"
    assert stat.S_IMODE(dest.stat().st_mode) == 0o755


def test_copy_falls_back_to_the_crate_target_dir_and_adds_exe_on_windows(
    builder, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the workspace dir has no artifact, the crate-local one is used."""
    triple = "x86_64-pc-windows-gnu"
    crate_dir = tmp_path / "rust" / "skill-suggester"
    crate_local = crate_dir / "target" / triple / "release" / "pss.exe"
    crate_local.parent.mkdir(parents=True)
    crate_local.write_bytes(b"MZ fake")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setattr(builder, "BIN_DIR", bin_dir)

    dest = builder._copy_binary(crate_dir, "pss", "pss", "windows-x86_64", triple)

    assert dest == bin_dir / "pss-windows-x86_64.exe"
    assert dest.read_bytes() == b"MZ fake"


def test_missing_artifact_and_unknown_tool_fail_instead_of_shipping_nothing(
    builder, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No artifact → None (main turns that into FAIL); an unknown tool never runs a build."""
    crate_dir = tmp_path / "rust" / "skill-suggester"
    crate_dir.mkdir(parents=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setattr(builder, "BIN_DIR", bin_dir)

    assert builder._copy_binary(
        crate_dir, "pss", "pss", "linux-x86_64", "x86_64-unknown-linux-musl"
    ) is None
    assert not list(bin_dir.iterdir())

    log_path = tmp_path / "build.log"
    with open(log_path, "w") as log_fh:
        ok, err = builder._build_one(
            crate_dir, "linux-x86_64", "x86_64-unknown-linux-musl", "bogus-tool", log_fh
        )
    assert ok is False and err == "Unknown tool: bogus-tool"

    # _has_tool must report honestly — the fallback ladder in _build_one depends on it.
    fake_tool = tmp_path / "zigbuild-stand-in"
    fake_tool.write_text("#!/bin/sh\nexit 0\n")
    fake_tool.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    assert builder._has_tool("zigbuild-stand-in") is True
    assert builder._has_tool("definitely-not-installed-xyzzy") is False
