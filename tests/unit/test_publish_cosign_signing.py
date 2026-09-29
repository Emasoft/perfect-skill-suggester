"""Unit tests for TRDD-PHQHS58T signing placement and dry-run safety.

Signing lives in CI (build-binaries.yml sign-release job), NOT in
publish.py — keyless cosign on a laptop produces a human-identity cert
the G3 workflow-identity pin rejects. What publish.py must guarantee:
the dev-side upload stays 12 assets (no bundles), and --dry-run never
uploads anything.
"""

import sys
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import publish  # noqa: E402


def test_upload_dry_run_performs_no_upload(capsys):
    """The load-bearing property: --dry-run uploads nothing, ever.

    Regression guard: the cosign commit deleted this early-exit and
    --dry-run executed `gh release upload` for real.
    """
    with patch.object(publish, "run") as mock_run:
        publish.upload_release_assets("9.9.9", dry_run=True)
    mock_run.assert_not_called()
    out = capsys.readouterr().out
    assert "DRY-RUN" in out


def test_upload_real_run_uploads_exactly_twelve_assets(tmp_path):
    """10 binaries + manifest + tarball = 12; bundles come from CI, not here."""
    calls = []

    def fake_run(cmd, timeout=None):
        calls.append(cmd)
        return type("R", (), {"returncode": 0, "stderr": ""})()

    fake_bins = [tmp_path / f"pss-fake-{i}" for i in range(10)]
    for f in fake_bins:
        f.write_bytes(b"x")
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")

    with (
        patch.object(publish, "run", side_effect=fake_run),
        patch.object(publish, "RELEASE_BINARIES", tuple(f.name for f in fake_bins)),
        patch.object(publish, "BIN_DIR", tmp_path),
        patch.object(publish, "BIN_MANIFEST", manifest),
    ):
        publish.upload_release_assets("9.9.9", dry_run=False)

    upload = next(c for c in calls if c[:2] == ["gh", "release"])
    assert upload[0] == "gh" and upload[1] == "release" and upload[2] == "upload"
    # gh release upload v<new> <12 assets> --clobber → 4 + 12 + 1 items
    assert len(upload) == 4 + 12 + 1
    assert not any("sigstore" in a for a in upload)


def test_no_laptop_signing_surface_exists():
    """publish.py must not grow a cosign dependency back."""
    src = Path(publish.__file__).read_text()
    assert "cosign" not in src.lower().replace(
        "trdd-phqhs58t", ""
    ) or "sign-blob" not in src, "publish.py grew a cosign signing path again"
