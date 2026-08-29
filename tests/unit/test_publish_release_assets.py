"""Tests for the release-asset half of scripts/publish.py (TRDD-YC51I1C0 phase 1).

`bin/manifest.json` is the trust anchor of the whole binary-distribution plan:
a later phase stops tracking the binaries and fetches them from the GitHub
release instead, verifying each download against the sha256 recorded here. The
manifest arrives through git — a channel the user already trusted by installing
the plugin — which is what makes it worth more than a `.sha256` published
beside the download on the same server.

So the properties under test are the ones a fetcher will depend on:
  * every shipped binary has an entry, and its sha256/size describe the REAL
    bytes on disk (a manifest that merely looks well-formed is worthless);
  * a missing binary is FATAL, never a quietly-omitted entry — an omitted
    entry is precisely what a fetcher refuses to install, so the failure has
    to surface while a human is watching the release, not at a user's first
    cold install;
  * the tarball carries exactly the ten names, flat, for the air-gapped tier.

The real functions run against a real temp filesystem. Nothing about the unit
under test is mocked; only BIN_DIR/BIN_MANIFEST are repointed, which is input,
not substitution.
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
def publish():
    """Load publish.py without running its CLI."""
    return _load_module("publish_under_test", SCRIPTS_DIR / "publish.py")


@pytest.fixture
def staged_bin(publish, tmp_path, monkeypatch):
    """A bin/ holding all ten release binaries with distinct, known contents."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for index, name in enumerate(publish.RELEASE_BINARIES):
        # Distinct per file, so a generator that hashed the wrong path (or the
        # same path ten times) cannot pass by coincidence.
        (bin_dir / name).write_bytes(b"binary-" + name.encode() + bytes([index]) * 32)
    monkeypatch.setattr(publish, "BIN_DIR", bin_dir)
    monkeypatch.setattr(publish, "BIN_MANIFEST", bin_dir / "manifest.json")
    return bin_dir


def test_manifest_records_the_real_bytes_of_every_binary(publish, staged_bin):
    """Manifest entry per shipped binary, with sha256/size of the actual file."""
    publish.write_binary_manifest("9.9.9", dry_run=False)

    manifest = json.loads((staged_bin / "manifest.json").read_text())
    assert manifest["schema"] == publish.MANIFEST_SCHEMA
    assert manifest["plugin_version"] == "9.9.9"
    assert manifest["release_tag"] == "v9.9.9"
    assert set(manifest["binaries"]) == set(publish.RELEASE_BINARIES)

    for name, entry in manifest["binaries"].items():
        raw = (staged_bin / name).read_bytes()
        assert entry["sha256"] == hashlib.sha256(raw).hexdigest(), name
        assert entry["size"] == len(raw), name


def test_dry_run_writes_no_manifest(publish, staged_bin):
    """--dry-run must not touch the tracked manifest."""
    publish.write_binary_manifest("9.9.9", dry_run=True)
    assert not (staged_bin / "manifest.json").exists()


def test_a_missing_binary_is_fatal_not_a_hole_in_the_manifest(publish, staged_bin):
    """A manifest may never ship with an entry silently absent.

    The tempting alternative — record what is present, skip what is not — is
    the dangerous one: the release still publishes, and the omission only
    surfaces later as an uninstallable platform for whoever happens to run it.
    """
    (staged_bin / publish.RELEASE_BINARIES[3]).unlink()

    with pytest.raises(SystemExit) as exc:
        publish.write_binary_manifest("9.9.9", dry_run=False)
    assert exc.value.code == 1
    # Fail-closed: no partially-populated manifest is left behind either.
    assert not (staged_bin / "manifest.json").exists()


def test_tarball_holds_exactly_the_ten_binaries_flat(publish, staged_bin, tmp_path):
    """The air-gapped bundle: ten members, flat names, byte-identical content."""
    dest = tmp_path / "assets"
    dest.mkdir()
    tarball = publish._binaries_tarball("9.9.9", dest)

    assert tarball.name == "pss-binaries-9.9.9.tar.gz"
    # Built OUTSIDE the repo: a tarball written into bin/ would dirty the tree
    # mid-release and be swept into the `git add bin/` that stages the binaries.
    assert publish.BIN_DIR not in tarball.parents

    with tarfile.open(tarball) as tf:
        members = tf.getnames()
        assert sorted(members) == sorted(publish.RELEASE_BINARIES)
        for name in members:
            extracted = tf.extractfile(name)
            assert extracted is not None
            assert extracted.read() == (staged_bin / name).read_bytes(), name


def test_release_binaries_matches_what_the_repo_actually_ships(publish):
    """The name list is not free-floating — it must match tracked bin/ reality.

    A name added to bin/ but not here would be published to nobody; a name here
    but not in bin/ would make every release fatal at manifest time. Asserted
    against the REAL bin/ directory, not the fixture.
    """
    real_bin = PROJECT_ROOT / "bin"
    on_disk = {
        p.name
        for p in real_bin.iterdir()
        if p.is_file() and p.name.startswith("pss-") and p.suffix != ".sh"
    }
    assert on_disk == set(publish.RELEASE_BINARIES)
