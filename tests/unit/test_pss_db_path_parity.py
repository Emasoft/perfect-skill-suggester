"""Python↔Rust DB-path parity (TRDD-1Z8SGQ7N F1 step 2).

The suggestion hot path, the `merge-events` writer, and every temporal verb
live in the Rust binary; the `skills`-table writer and the hook's
"is the DB ready" check live in Python. If the two resolvers disagree about
WHICH file is the DB, Python writes skills into one file while Rust writes
history into another — the divergence that produced an 8488-skill/0-event
orphan alongside the real 8965-skill/9135-event DB.

These tests drive the REAL binary's `db-path` subcommand (which mirrors
`get_db_path`'s resolution order without the existence gate) and the REAL
`pss_cozodb.get_db_path()` in a subprocess, under a controlled env and a
fake HOME. No mocks: a mocked resolver would agree with itself and prove
nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pss_paths import detect_platform  # noqa: E402

BINARY = ROOT / "bin" / detect_platform()


def _clean_env(tmp_home: Path, **extra: str) -> dict[str, str]:
    """Env with HOME pinned to a temp dir and both path vars cleared.

    Clearing is load-bearing: the developer's real session exports
    CLAUDE_PLUGIN_DATA, which is exactly the variable that used to make the
    two resolvers disagree — inheriting it would make the "unset" case
    silently test something else.
    """
    env = {k: v for k, v in os.environ.items()}
    env.pop("PSS_INDEX_PATH", None)
    env.pop("CLAUDE_PLUGIN_DATA", None)
    env["HOME"] = str(tmp_home)
    env.update(extra)
    return env


def _rust_db_path(env: dict[str, str]) -> str:
    out = subprocess.run(
        [str(BINARY), "db-path"], env=env, capture_output=True, text=True, timeout=30
    )
    assert out.returncode == 0, f"db-path failed: {out.stderr}"
    text = out.stdout.strip()
    # The subcommand emits a bare path by default and JSON under --format json;
    # accept either so the test pins the VALUE, not the presentation.
    if text.startswith("{"):
        return str(json.loads(text)["db_path"])
    return text


def _python_db_path(env: dict[str, str]) -> str:
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, %r); "
            "import pss_cozodb; print(pss_cozodb.get_db_path())" % str(SCRIPTS),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert out.returncode == 0, f"get_db_path failed: {out.stderr}"
    return out.stdout.strip()


pytestmark = pytest.mark.skipif(
    not BINARY.exists(), reason=f"platform binary not built: {BINARY}"
)


def test_db_path_parity_no_env(tmp_path: Path) -> None:
    """With no override, both resolvers land on ~/.claude/cache."""
    env = _clean_env(tmp_path)
    rust, py = _rust_db_path(env), _python_db_path(env)
    assert py == rust
    assert py == str(tmp_path / ".claude" / "cache" / "pss-skill-index.db")


def test_db_path_parity_pss_index_path(tmp_path: Path) -> None:
    """PSS_INDEX_PATH moves BOTH resolvers to the sibling DB of its dir."""
    seed = tmp_path / "elsewhere" / "skill-index.json"
    env = _clean_env(tmp_path, PSS_INDEX_PATH=str(seed))
    rust, py = _rust_db_path(env), _python_db_path(env)
    assert py == rust
    assert py == str(seed.parent / "pss-skill-index.db")


def test_db_path_parity_claude_plugin_data_is_ignored(tmp_path: Path) -> None:
    """A PSS-scoped $CLAUDE_PLUGIN_DATA must NOT move the DB.

    This is the F1 regression pin: Python used to honour this variable while
    Rust never has, so the skills table and the events table ended up in two
    different files. The env var still backs non-DB state (staging JSON,
    lockfiles) via pss_paths.get_data_dir() — only the DB is pinned.
    """
    plugin_data = (
        tmp_path / "plugins" / "data" / "perfect-skill-suggester-emasoft-plugins"
    )
    plugin_data.mkdir(parents=True)
    env = _clean_env(tmp_path, CLAUDE_PLUGIN_DATA=str(plugin_data))
    rust, py = _rust_db_path(env), _python_db_path(env)
    assert py == rust
    assert py == str(tmp_path / ".claude" / "cache" / "pss-skill-index.db")
    assert str(plugin_data) not in py


def test_non_db_state_still_follows_plugin_data(tmp_path: Path) -> None:
    """get_data_dir() keeps its $CLAUDE_PLUGIN_DATA preference.

    Pins the OTHER half of the option-B decision: only the DB path was
    canonicalized. If this ever starts returning ~/.claude/cache, the
    persistent-data feature (CC v2.1.78+) was silently reverted wholesale
    rather than narrowed to the DB.
    """
    plugin_data = (
        tmp_path / "plugins" / "data" / "perfect-skill-suggester-emasoft-plugins"
    )
    plugin_data.mkdir(parents=True)
    env = _clean_env(tmp_path, CLAUDE_PLUGIN_DATA=str(plugin_data))
    out = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, %r); "
            "import pss_paths; print(pss_paths.get_data_dir())" % str(SCRIPTS),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == str(plugin_data)
