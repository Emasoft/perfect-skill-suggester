"""Binary-path parity: Python ↔ sh-shim ↔ Rust ↔ release naming (TRDD-YC51I1C0).

Three resolvers map a platform to a binary NAME and stat for it:

  1. ``scripts/pss_paths.py::resolve_pss_binary``  (Python: hook / scripts)
  2. ``bin/pss-hook-dispatch.sh``                  (POSIX sh: hot UserPromptSubmit path)
  3. ``find_pss_nlp_binary`` in the Rust binary    (negation detection), probed
     here via the ``nlp-binary-path`` subcommand (prints the resolved path on
     one line; bare newline + exit 0 when not found)

and one release surface names the assets (``RELEASE_BINARIES`` +
``bin/manifest.json``). If any of them disagree — about the platform→filename
map or the directory search order — a user gets suggestions from a stale copy
while another path silently ships a new one.

These tests drive the REAL sh shim, the REAL Python resolver and the REAL
Rust binary in subprocesses under a controlled env (fake HOME, plugin vars
cleared). No mocks: a mocked resolver would agree with itself and prove
nothing. Skipped entirely when the platform binary is not built — the test
needs a phase-2 rebuild containing the ``nlp-binary-path`` subcommand (CI
builds it).
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
BIN = ROOT / "bin"
SHIM = BIN / "pss-hook-dispatch.sh"
HOOKS_JSON = ROOT / "hooks" / "hooks.json"
MANIFEST = BIN / "manifest.json"
PLUGIN_ROOT = str(ROOT)  # the repo IS the plugin root for these runs

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pss_paths import detect_platform  # noqa: E402

PLATFORM = detect_platform()
BINARY = ROOT / "bin" / PLATFORM

pytestmark = pytest.mark.skipif(
    not BINARY.exists(), reason=f"platform binary not built: {BINARY}"
)

PLATFORM_POSIX = pytest.mark.skipif(
    sys.platform == "win32", reason="sh shim needs a POSIX sh"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_env(tmp_home: Path, **extra: str) -> dict[str, str]:
    """Env with HOME pinned to a temp dir and the path vars controlled.

    Clearing is load-bearing: the developer's real session exports
    CLAUDE_PLUGIN_DATA / CLAUDE_PLUGIN_ROOT, which would silently redirect
    every resolver at the developer's real store — exactly what these tests
    must never assert against.
    """
    env = {k: v for k, v in os.environ.items()}
    for var in ("CLAUDE_PLUGIN_DATA", "CLAUDE_PLUGIN_ROOT", "PSS_BINARY_DIR"):
        env.pop(var, None)
    env["HOME"] = str(tmp_home)
    env.update(extra)
    return env


def _mk_exec(path: Path) -> Path:
    """Create an empty executable file (existence + exec bit is all resolvers stat)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    path.chmod(0o755)
    return path


def _store_current(tmp_home: Path) -> Path:
    """The fetched-binary store under the FAKE home — the constant layout."""
    return tmp_home / ".claude" / "cache" / "pss-bin" / "current"


def _python_resolver(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run the real resolve_pss_binary() in a subprocess under `env`."""
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, %r); "
            "from pss_paths import resolve_pss_binary; "
            "print(resolve_pss_binary())" % str(SCRIPTS),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _run_shim(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run the real sh shim with empty stdin under `env`."""
    return subprocess.run(
        ["sh", str(SHIM)],
        env=env,
        input="",
        capture_output=True,
        text=True,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# 1. Platform-name agreement: detect_platform ↔ manifest ↔ RELEASE_BINARIES ↔ shim
# ---------------------------------------------------------------------------


def test_name_map_agrees() -> None:
    """detect_platform() must name a real release asset and match the sh shim."""
    # Release surface: manifest .binaries and publish.py RELEASE_BINARIES
    # must both carry this platform's filename.
    manifest_binaries = set(json.loads(MANIFEST.read_text())["binaries"])
    sys.path.insert(0, str(SCRIPTS))
    from publish import RELEASE_BINARIES  # noqa: E402  (constants-only import)

    assert PLATFORM in manifest_binaries, (
        f"{PLATFORM} missing from {MANIFEST} .binaries — the fetcher would "
        "refuse to verify a downloaded binary for this platform"
    )
    assert PLATFORM in RELEASE_BINARIES, (
        f"{PLATFORM} missing from RELEASE_BINARIES — release assets and bin/ "
        "filenames must stay byte-identical (TRDD-YC51I1C0 phase 1)"
    )

    # The sh shim's case arms must map this platform to the SAME name.
    # Tiny table mirroring the shim's case structure (Darwin/Linux blocks are
    # keyed by SYSTEM and normalized MACHINE; Windows has a single arm).
    system = platform.system()
    machine = platform.machine().lower()
    if machine == "aarch64":
        machine = "arm64"
    elif machine == "amd64":
        machine = "x86_64"
    shim_text = SHIM.read_text()

    if system == "Windows":
        assert 'BIN_NAME="pss-windows-x86_64.exe"' in shim_text
        return

    expected = {
        ("Darwin", "arm64"): "pss-darwin-arm64",
        ("Darwin", "x86_64"): "pss-darwin-x86_64",
        ("Linux", "arm64"): "pss-linux-arm64",
        ("Linux", "x86_64"): "pss-linux-x86_64",
    }[(system, machine)]
    arm = re.compile(
        rf"{re.escape(machine)}\)\s+BIN_NAME=\"{re.escape(expected)}\""
    )
    assert arm.search(shim_text), (
        f"{SHIM} has no case arm mapping {system}/{machine} to {expected} — "
        "the shim's platform map has drifted from detect_platform()"
    )


# ---------------------------------------------------------------------------
# 2. Python resolver search order (resolve_pss_binary)
# ---------------------------------------------------------------------------


def _python_order_scenario(
    tmp_path: Path,
    *,
    with_pss_dir: bool = False,
    with_plugin_bin: bool = False,
    with_store: bool = False,
) -> tuple[dict[str, str], dict[str, Path]]:
    """Place the platform binary in the requested roots; return (env, roots)."""
    tmp_home = tmp_path / "home"
    root_a = tmp_path / "escape"  # $PSS_BINARY_DIR
    root_b = tmp_path / "plugin" / "bin"  # $CLAUDE_PLUGIN_ROOT/bin
    store = _store_current(tmp_home)
    if with_pss_dir:
        _mk_exec(root_a / PLATFORM)
    if with_plugin_bin:
        _mk_exec(root_b / PLATFORM)
    if with_store:
        _mk_exec(store / PLATFORM)
    env = _clean_env(
        tmp_home,
        CLAUDE_PLUGIN_ROOT=str(root_b.parent),
        **({"PSS_BINARY_DIR": str(root_a)} if with_pss_dir else {}),
    )
    return env, {"escape": root_a / PLATFORM, "plugin": root_b / PLATFORM, "store": store / PLATFORM}


@pytest.mark.parametrize(
    "kw, expected",
    [
        ({"with_pss_dir": True}, "escape"),
        ({"with_pss_dir": True, "with_store": True}, "escape"),
        ({"with_pss_dir": True, "with_plugin_bin": True}, "escape"),
        ({"with_store": True}, "store"),
        ({"with_store": True, "with_plugin_bin": True}, "store"),
        ({"with_plugin_bin": True}, "plugin"),
    ],
    ids=[
        "only-PSS_BINARY_DIR",
        "PSS_BINARY_DIR-beats-store",
        "PSS_BINARY_DIR-beats-plugin-bin",
        "only-store",
        "store-beats-plugin-bin",
        "only-plugin-bin",
    ],
)
def test_python_resolver_search_order(tmp_path: Path, kw: dict, expected: str) -> None:
    """resolve_pss_binary() follows: $PSS_BINARY_DIR → store → plugin bin.

    Phase-3 order (TRDD-YC51I1C0): the fetched store WINS over the plugin/repo
    copy; here the plugin root is always pinned to a tmp dir so the repo's own
    bin/ never participates.
    """
    env, roots = _python_order_scenario(tmp_path, **kw)
    out = _python_resolver(env)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == str(roots[expected])


def test_python_resolver_fails_fast_when_absent(tmp_path: Path) -> None:
    """No binary anywhere → FileNotFoundError (nonzero exit), never a fallback."""
    tmp_home = tmp_path / "home"
    empty_plugin = tmp_path / "plugin"
    (empty_plugin / "bin").mkdir(parents=True)
    env = _clean_env(tmp_home, CLAUDE_PLUGIN_ROOT=str(empty_plugin))
    out = _python_resolver(env)
    assert out.returncode != 0
    assert "FileNotFoundError" in out.stderr


# ---------------------------------------------------------------------------
# 3. Rust nlp-binary-path search order (find_pss_nlp_binary)
# ---------------------------------------------------------------------------


def _nlp_name() -> str:
    """The pss-nlp platform filename (pss-darwin-arm64 → pss-nlp-darwin-arm64)."""
    return "pss-nlp-" + PLATFORM.removeprefix("pss-")


def _run_nlp_probe(tmp_path: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run `nlp-binary-path` on a COPY of the real binary in an empty dir.

    The exe-dir root (root 1 of find_pss_nlp_binary) is the directory of the
    running binary — running the repo's bin/pss-darwin-arm64 directly would let
    the sibling pss-nlp-* files in bin/ win before roots 2-4 are consulted. A
    copy in an empty tmp dir neutralizes root 1 so the documented order for
    roots 2-4 is what's actually exercised.
    """
    exe_dir = tmp_path / "exe"
    exe_copy = _mk_exec(exe_dir / PLATFORM)
    shutil.copy2(BINARY, exe_copy)
    return subprocess.run(
        [str(exe_copy), "nlp-binary-path"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


@PLATFORM_POSIX
def test_rust_nlp_resolver_search_order(tmp_path: Path) -> None:
    """Rust order: $PSS_BINARY_DIR → store/current → $CLAUDE_PLUGIN_ROOT/bin."""
    tmp_home = tmp_path / "home"
    root_a = tmp_path / "escape"
    root_b = tmp_path / "plugin" / "bin"
    store = _store_current(tmp_home)
    nlp = _nlp_name()

    def env_for(pss_dir: bool, plugin_bin: bool, store_bin: bool) -> dict[str, str]:
        # Scenarios share the dirs inside one test — clear all roots first so
        # a stub from a previous scenario cannot win this one's assertion.
        for stale in (root_a / nlp, root_b / nlp, store / nlp):
            stale.unlink(missing_ok=True)
        if pss_dir:
            _mk_exec(root_a / nlp)
        if plugin_bin:
            _mk_exec(root_b / nlp)
        if store_bin:
            _mk_exec(store / nlp)
        return _clean_env(
            tmp_home,
            CLAUDE_PLUGIN_ROOT=str(root_b.parent),
            **({"PSS_BINARY_DIR": str(root_a)} if pss_dir else {}),
        )

    for kw, expected in [
        (dict(pss_dir=True, plugin_bin=True, store_bin=True), root_a / nlp),
        (dict(pss_dir=False, plugin_bin=True, store_bin=True), store / nlp),
        (dict(pss_dir=False, plugin_bin=False, store_bin=True), store / nlp),
        (dict(pss_dir=False, plugin_bin=True, store_bin=False), root_b / nlp),
    ]:
        out = _run_nlp_probe(tmp_path, env_for(**kw))
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == str(expected), (
            f"nlp-binary-path resolved {out.stdout.strip()!r}, expected {expected}"
        )


@PLATFORM_POSIX
def test_rust_nlp_resolver_prints_empty_when_not_found(tmp_path: Path) -> None:
    """Nothing anywhere → bare newline + exit 0 (negation detection skipped)."""
    tmp_home = tmp_path / "home"
    tmp_home.mkdir()
    empty_plugin = tmp_path / "plugin"
    (empty_plugin / "bin").mkdir(parents=True)
    env = _clean_env(tmp_home, CLAUDE_PLUGIN_ROOT=str(empty_plugin))
    out = _run_nlp_probe(tmp_path, env)
    assert out.returncode == 0, out.stderr
    assert out.stdout == "\n", f"expected bare newline, got {out.stdout!r}"


# ---------------------------------------------------------------------------
# 4. sh shim search order
# ---------------------------------------------------------------------------


@PLATFORM_POSIX
def test_sh_resolver_search_order(tmp_path: Path) -> None:
    """Shim execs: $PSS_BINARY_DIR → store/current → $CLAUDE_PLUGIN_ROOT/bin.

    Phase-3 order (TRDD-YC51I1C0): the fetched store WINS over the plugin/repo
    copy. Each candidate is a stub SCRIPT echoing which root it came from, so
    the assertion pins which file the shim actually exec'd.
    """
    tmp_home = tmp_path / "home"
    root_a = tmp_path / "escape"
    root_b = tmp_path / "plugin" / "bin"
    store = _store_current(tmp_home)

    def stub(root: Path, marker: str) -> None:
        path = root / PLATFORM
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'#!/bin/sh\necho "FROM:{marker}"\n')
        path.chmod(0o755)

    def env_for(pss_dir: bool) -> dict[str, str]:
        return _clean_env(
            tmp_home,
            CLAUDE_PLUGIN_ROOT=str(root_b.parent),
            **({"PSS_BINARY_DIR": str(root_a)} if pss_dir else {}),
        )

    for kw, expected in [
        (dict(pss_dir=True), "PSS_BINARY_DIR"),
        (dict(pss_dir=False), "STORE"),
        (dict(pss_dir=False), "PLUGIN_BIN"),
    ]:
        # Scenarios share the dirs inside one test — clear all roots first so
        # a stub from a previous scenario cannot win this one's assertion.
        for stale in (root_a / PLATFORM, root_b / PLATFORM, store / PLATFORM):
            stale.unlink(missing_ok=True)
        if kw["pss_dir"]:
            stub(root_a, "PSS_BINARY_DIR")
        elif expected == "STORE":
            stub(store, "STORE")
        else:
            stub(root_b, "PLUGIN_BIN")
        out = _run_shim(env_for(**kw))
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == f"FROM:{expected}", (
            f"shim exec'd {out.stdout.strip()!r}, expected the {expected} stub"
        )


@PLATFORM_POSIX
def test_sh_resolver_empty_hook_json_when_not_found(tmp_path: Path) -> None:
    """No binary anywhere → empty-additionalContext hook JSON, exit 0.

    CLAUDE_PLUGIN_ROOT must be pinned: unset, the shim falls back to its own
    directory — the repo's bin/, which HAS the binary.
    """
    tmp_home = tmp_path / "home"
    empty_plugin = tmp_path / "plugin"
    (empty_plugin / "bin").mkdir(parents=True)
    env = _clean_env(tmp_home, CLAUDE_PLUGIN_ROOT=str(empty_plugin))
    out = _run_shim(env)
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    assert payload["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert payload["hookSpecificOutput"]["additionalContext"] == ""


# ---------------------------------------------------------------------------
# 5. hooks.json quoting invariant (CC 2.1.281 validator)
# ---------------------------------------------------------------------------


def test_quoted_plugin_root_in_hooks_json() -> None:
    """Every ${CLAUDE_PLUGIN_ROOT} occurrence is inside double quotes.

    The CC 2.1.281 hook validator rejects unquoted references; the quote is
    also load-bearing on paths with spaces.
    """
    data = json.loads(HOOKS_JSON.read_text())
    commands = [
        hook["command"]
        for event_hooks in data.get("hooks", {}).values()
        for matcher_block in event_hooks
        for hook in matcher_block.get("hooks", [])
    ]
    assert commands, f"no hook commands found in {HOOKS_JSON}"
    needle = "${CLAUDE_PLUGIN_ROOT}"
    for command in commands:
        start = 0
        while (idx := command.find(needle, start)) != -1:
            assert idx > 0 and command[idx - 1] == '"', (
                f"unquoted {needle} in hook command: {command!r}"
            )
            start = idx + len(needle)
