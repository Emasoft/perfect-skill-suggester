"""Unit tests for TRDD-PHQHS58T keyless asset signing in publish.py."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import publish  # noqa: E402


@pytest.fixture()
def fake_assets(tmp_path):
    files = []
    for name in ("pss-darwin-arm64", "manifest.json"):
        f = tmp_path / name
        f.write_bytes(b"x" * 16)
        files.append(f)
    return files


def test_missing_cosign_is_fatal(fake_assets, capsys):
    with patch.object(publish.shutil, "which", return_value=None):
        with pytest.raises(SystemExit):
            publish.sign_release_assets(fake_assets, dry_run=False)
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "cosign" in out


def test_dry_run_signs_nothing(fake_assets):
    with patch.object(publish.shutil, "which", return_value="/usr/bin/cosign"):
        bundles = publish.sign_release_assets(fake_assets, dry_run=True)
    assert bundles == []
    assert not list(fake_assets[0].parent.glob("*.sigstore.json"))


def test_sign_writes_bundle_beside_asset(fake_assets):
    calls = []

    def fake_run(cmd, timeout):
        calls.append(cmd)
        return type("R", (), {"returncode": 0, "stderr": ""})()

    with (
        patch.object(publish.shutil, "which", return_value="/usr/bin/cosign"),
        patch.object(publish, "run", side_effect=fake_run),
    ):
        bundles = publish.sign_release_assets(fake_assets, dry_run=False)

    assert len(bundles) == 2
    for asset, bundle in zip(fake_assets, bundles):
        assert bundle == asset.with_name(asset.name + ".sigstore.json")
    cmd = calls[0]
    assert cmd[:4] == ["cosign", "sign-blob", "--yes", "--bundle"]
    assert cmd[-1] == str(fake_assets[0])


def test_sign_failure_is_fatal(fake_assets):
    with (
        patch.object(publish.shutil, "which", return_value="/usr/bin/cosign"),
        patch.object(
            publish,
            "run",
            return_value=type("R", (), {"returncode": 1, "stderr": "boom"})(),
        ),
        pytest.raises(SystemExit),
    ):
        publish.sign_release_assets(fake_assets, dry_run=False)
