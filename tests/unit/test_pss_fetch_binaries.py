"""Tests for scripts/pss_fetch_binaries.py (TRDD-YC51I1C0 phase 2).

The fetcher's whole value is what it does when things go WRONG. A happy-path
download proves little: the interesting contract is that a corrupted, truncated,
or unverifiable artifact leaves NOTHING behind, because a partially-installed
binary is indistinguishable from a working one until a user's session breaks in
a way nobody can trace back to here.

So these exercise the refusal paths against a real filesystem and a real tarball
built by the same code path publish.py uses:

  * a tarball member whose bytes do not match the manifest is refused, the store
    stays empty, and the state file records why;
  * a member missing from the tarball is refused rather than half-installed;
  * a manifest with no entry for this platform is refused — unverifiable bytes
    are never installed, which is the entire point of shipping the sha in git;
  * a second run over a populated store re-publishes `current/` without needing
    the artifact again (the "unchanged engine costs nothing" property);
  * only the two binaries this machine can run are ever installed.

The network is not mocked because it is never reached: every case here runs
through `--offline`, which is the same verification code with a different
source of bytes.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tarfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fetcher():
    return _load_module("pss_fetch_under_test", SCRIPTS_DIR / "pss_fetch_binaries.py")


@pytest.fixture
def env(fetcher, tmp_path, monkeypatch):
    """A fake plugin root (with a manifest) and an empty data dir."""
    plugin_root = tmp_path / "plugin"
    (plugin_root / "bin").mkdir(parents=True)
    data = tmp_path / "data"
    data.mkdir()

    names = fetcher.needed_names()
    payloads = {n: b"engine-bytes-" + n.encode() for n in names}
    manifest = {
        "schema": 1,
        "plugin_version": "9.9.9",
        "release_tag": "v9.9.9",
        "binaries": {
            n: {"sha256": hashlib.sha256(b).hexdigest(), "size": len(b)}
            for n, b in payloads.items()
        },
    }
    (plugin_root / "bin" / "manifest.json").write_text(json.dumps(manifest))

    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin_root))
    # D3 pin (TRDD-YC51I1C0): the store is the CONSTANT ~/.claude/cache/pss-bin,
    # derived from HOME — so the fixture redirects HOME instead of patching a
    # get_data_dir import that the fetcher no longer has.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()

    def make_tarball(contents: dict[str, bytes] | None = None) -> Path:
        contents = payloads if contents is None else contents
        staging = tmp_path / "staging"
        staging.mkdir(exist_ok=True)
        tarball = tmp_path / "pss-binaries-9.9.9.tar.gz"
        with tarfile.open(tarball, "w:gz") as tf:
            for n, b in contents.items():
                p = staging / n
                p.write_bytes(b)
                tf.add(p, arcname=n)
        return tarball

    return {
        "data": tmp_path / "home" / ".claude" / "cache" / "pss-bin",
        "names": names,
        "payloads": payloads,
        "manifest_path": plugin_root / "bin" / "manifest.json",
        "make_tarball": make_tarball,
    }


def _state(data: Path) -> dict:
    return json.loads((data / ".state.json").read_text())


def test_offline_install_populates_only_this_platforms_binaries(fetcher, env):
    """Exactly two artifacts land, content-addressed, published via current/."""
    assert fetcher.fetch(env["make_tarball"]()) == 0

    store = env["data"]
    for name in env["names"]:
        sha = hashlib.sha256(env["payloads"][name]).hexdigest()
        artifact = store / sha[:16] / name
        assert artifact.read_bytes() == env["payloads"][name]
        assert (store / "current" / name).read_bytes() == env["payloads"][name]

    # Two binaries, not ten: fetching the full set would move ~160 MiB to run
    # ~30 MiB of it.
    assert len(env["names"]) == 2
    assert sorted(p.name for p in (store / "current").iterdir()) == sorted(env["names"])
    assert _state(env["data"])["status"] == "ok"


def test_corrupt_member_is_refused_and_leaves_an_empty_store(fetcher, env):
    """Fail-closed: a byte that does not match the manifest installs nothing.

    The dangerous alternative is a partial install — a `current/` entry pointing
    at bytes nobody verified, which behaves like a working engine right up until
    it does not.
    """
    bad = dict(env["payloads"])
    first = env["names"][0]
    bad[first] = b"tampered"

    assert fetcher.fetch(env["make_tarball"](bad)) == 1

    store = env["data"]
    assert not (store / "current" / first).exists()
    # Nothing half-written anywhere in the store either.
    assert not list(store.glob("*/*.part"))
    assert _state(env["data"])["status"] == "checksum-mismatch"


def test_member_missing_from_the_tarball_is_refused(fetcher, env):
    """An incomplete bundle fails loudly rather than installing what it has."""
    partial = {env["names"][1]: env["payloads"][env["names"][1]]}

    assert fetcher.fetch(env["make_tarball"](partial)) == 1
    assert _state(env["data"])["status"] == "offline-incomplete"
    assert not (env["data"] / "current" / env["names"][0]).exists()


def test_manifest_without_this_platform_installs_nothing(fetcher, env):
    """No trusted sha means no install — that is what shipping it in git buys."""
    manifest = json.loads(env["manifest_path"].read_text())
    del manifest["binaries"][env["names"][0]]
    env["manifest_path"].write_text(json.dumps(manifest))

    assert fetcher.fetch(env["make_tarball"]()) == 1
    assert _state(env["data"])["status"] == "manifest-incomplete"
    assert not (env["data"] / "current").exists()


def test_a_missing_manifest_is_fatal_with_the_path_it_tried(fetcher, env):
    """A plugin install without the manifest is incomplete — say so, don't guess."""
    env["manifest_path"].unlink()
    with pytest.raises(SystemExit) as exc:
        fetcher.fetch(env["make_tarball"]())
    assert "manifest" in str(exc.value).lower()


def test_second_run_reuses_the_store_without_the_artifact(fetcher, env):
    """An unchanged engine costs a new version nothing — no bytes, no network.

    Proven by deleting the source tarball between runs: if the second run needed
    the artifact it could not possibly succeed.
    """
    tarball = env["make_tarball"]()
    assert fetcher.fetch(tarball) == 0
    (env["data"] / "current" / env["names"][0]).unlink()
    tarball.unlink()

    # No tarball, no network — the content-addressed copies are already there,
    # so the run only has to re-publish current/.
    assert fetcher.fetch(None) == 0
    for name in env["names"]:
        assert (env["data"] / "current" / name).read_bytes() == env["payloads"][name]


def test_a_blocked_network_fails_loudly_and_installs_nothing(fetcher, env, capsys, monkeypatch):
    """The network path, exercised for real — no mock of the thing under test.

    Everything else here runs through `--offline`, which shares the verification
    code but NOT the download loop, its retry bound, or the message a
    corporate-proxy user actually sees. Leaving that untested because "the
    network is not reachable in tests" is the excuse version; pointing the
    fetcher at an address that cannot resolve is the real thing, and it costs
    milliseconds.

    Retries are shortened to keep the test fast — the bound itself is asserted
    separately by reading ATTEMPTS, not by waiting for it.
    """
    monkeypatch.setattr(fetcher, "DOWNLOAD_BASE", "https://pss-invalid.invalid/releases/download")
    monkeypatch.setattr(fetcher, "BACKOFF_SECONDS", 0)

    assert fetcher.fetch(None) == 1

    store = env["data"]
    assert not (store / "current").exists(), "nothing may be published on failure"
    assert not list(store.glob("*/*.part")), "no partial file may survive"

    state = _state(env["data"])
    assert state["status"] == "network-blocked"
    assert "pss-invalid.invalid" in state["url"]

    # The remedy must travel WITH the failure: a user behind a proxy cannot
    # look up documentation they were never pointed at.
    err = capsys.readouterr().err
    assert "offline install" in err
    assert "pss-binaries-9.9.9.tar.gz" in err
    assert "PSS_BINARY_DIR" in err
    assert fetcher.ATTEMPTS == 3, "retries stay bounded; an unbounded loop is a hang"


def test_a_tampered_download_is_recorded_not_just_refused(fetcher, env, tmp_path, monkeypatch):
    """The DOWNLOAD path, run for real over file:// — no network, no mock.

    `urlopen` handles `file://`, so pointing DOWNLOAD_BASE at a directory
    exercises the actual retry/verify/replace code rather than the `--offline`
    branch that was previously asserted to stand in for it. The two are NOT the
    same code and diverged exactly where it mattered: a network mismatch used to
    raise SystemExit, which — being a BaseException — escaped every handler and
    left `.state.json` holding the PREVIOUS run's `{"status": "ok"}`. A
    /pss-status reading healthy right after a tampered download is the silent
    degradation the git-shipped checksum exists to prevent.
    """
    served = tmp_path / "served" / "v9.9.9"
    served.mkdir(parents=True)
    for name in env["names"]:
        (served / name).write_bytes(b"TAMPERED-" + name.encode())
    monkeypatch.setattr(fetcher, "DOWNLOAD_BASE", f"file://{tmp_path / 'served'}")
    monkeypatch.setattr(fetcher, "BACKOFF_SECONDS", 0)

    # Seed a prior success, so a missing write would leave a STALE "ok" behind
    # — the exact failure this test exists to catch.
    fetcher.write_state("ok", release_tag="v0.0.0")

    assert fetcher.fetch(None) == 1

    state = _state(env["data"])
    assert state["status"] == "checksum-mismatch", "a mismatch must overwrite a stale ok"
    assert not (env["data"] / "current").exists()
    assert not list((env["data"]).glob("*/*.part"))


def test_good_download_over_file_url_installs_and_records_ok(fetcher, env, tmp_path, monkeypatch):
    """The happy download path, also real: correct bytes install and publish."""
    served = tmp_path / "served" / "v9.9.9"
    served.mkdir(parents=True)
    for name, payload in env["payloads"].items():
        (served / name).write_bytes(payload)
    monkeypatch.setattr(fetcher, "DOWNLOAD_BASE", f"file://{tmp_path / 'served'}")

    assert fetcher.fetch(None) == 0
    for name in env["names"]:
        assert (env["data"] / "current" / name).read_bytes() == env["payloads"][name]
    assert _state(env["data"])["status"] == "ok"


def test_engine_present_but_nlp_sibling_missing_installs_neither(fetcher, env):
    """"Installs nothing" must hold when the FIRST name succeeds and a later one fails.

    The earlier missing-member test omitted names[0], so it returned before
    installing anything and the contract was never actually exercised. With the
    engine present and its nlp sibling absent, publishing inside the loop left
    a half-installed store behind an exit 1.
    """
    engine_only = {env["names"][0]: env["payloads"][env["names"][0]]}

    assert fetcher.fetch(env["make_tarball"](engine_only)) == 1
    assert _state(env["data"])["status"] == "offline-incomplete"
    current = env["data"] / "current"
    assert not current.exists() or not list(current.iterdir()), "no partial publish"


def test_needed_names_pairs_the_engine_with_its_nlp_sibling(fetcher):
    """The name map is the contract shared by all three resolvers."""
    names = fetcher.needed_names()
    assert len(names) == 2
    assert names[1] == names[0].replace("pss-", "pss-nlp-", 1)
    assert names[0].startswith("pss-") and not names[0].startswith("pss-nlp-")


def test_session_start_spawns_once_when_binaries_absent(fetcher, env, capsys, monkeypatch):
    """The spawn decision itself (review fork 2026-09-28 finding 5).

    env gives a plugin root whose bin/ holds only the manifest — no binaries —
    and an empty HOME store. The gate must: print the in-flight notice exactly
    once, spawn the fetcher exactly once, and exit 0.
    """
    spawns = []

    class _FakeProc:
        pass

    monkeypatch.setattr(
        fetcher.subprocess, "Popen", lambda *a, **k: spawns.append(k) or _FakeProc()
    )
    assert fetcher.session_start() == 0
    assert spawns, "expected exactly one detached spawn on a binary-less install"
    assert len(spawns) == 1
    assert spawns[0].get("start_new_session") is True
    # The child must NEVER inherit this process's stdout — a spawned fetcher
    # printing anything would break the one-line-only SessionStart contract.
    assert spawns[0].get("stdout") is fetcher.subprocess.DEVNULL
    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1, captured.out
    assert captured.out.strip() == fetcher.IN_FLIGHT_NOTICE


def test_session_start_stays_silent_when_binaries_resolve(fetcher, env, capsys, monkeypatch):
    """The binaries-present path prints NOTHING (CC 2.1.277 cache-miss rule)."""
    for name in env["names"]:
        (env["data"] / "current").mkdir(parents=True, exist_ok=True)
        (env["data"] / "current" / name).write_bytes(b"x")
        (env["data"] / "current" / name).chmod(0o755)
    spawns = []
    monkeypatch.setattr(
        fetcher.subprocess, "Popen", lambda *a, **k: spawns.append(k)
    )
    assert fetcher.session_start() == 0
    assert not spawns
    assert capsys.readouterr().out == ""
