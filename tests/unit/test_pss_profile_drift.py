"""Tests for pss_profile_drift.py (issue #15 contract).

Covers the 8 spec cases: empty profile, one missing skill, near-match extra,
moved_scope via [pss.scope_hints], absent scope_hints, missing file (exit 2),
index unavailable (exit 3), and counts mirroring the arrays.

`get_all_entries` is monkeypatched on the drift module itself (it is imported
as a symbol there), so no CozoDB is touched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pss_profile_drift  # noqa: E402  (import after sys.path injection is intentional)

EMPTY_PROFILE = ""


def _write_profile(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "fixture.agent.toml"
    path.write_text(content, encoding="utf-8")
    return path


FIXTURE_INDEX = {
    "python-lsp": {
        "name": "python-lsp",
        "source": "user:python-lsp",
        "type": "skill",
    },
    "Python-LSP": {
        "name": "Python-LSP",
        "source": "user:python-lsp",
        "type": "skill",
    },
    "pyton-lsp": {
        "name": "pyton-lsp",
        "source": "user:pyton-lsp",
        "type": "skill",
    },
    "code-review": {
        "name": "code-review",
        "source": "plugin:foo/code-review",
        "type": "skill",
    },
    "test-writer": {
        "name": "test-writer",
        "source": "user:test-writer",
        "type": "skill",
    },
}


class TestDriftContract:
    def test_empty_profile_all_empty_exit_0(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        path = _write_profile(tmp_path, EMPTY_PROFILE)
        monkeypatch.setattr(pss_profile_drift, "get_all_entries", lambda: FIXTURE_INDEX)
        pss_profile_drift.main([str(path)])
        out = json.loads(capsys.readouterr().out)
        assert out["missing"] == []
        assert out["extra"] == []
        assert out["moved_scope"] == []
        assert out["counts"] == {"missing": 0, "extra": 0, "moved_scope": 0}

    def test_one_missing_skill_reports_type_and_section(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        path = _write_profile(
            tmp_path, '[skills]\nprimary = ["totally-absent-skill"]\n'
        )
        monkeypatch.setattr(pss_profile_drift, "get_all_entries", lambda: FIXTURE_INDEX)
        pss_profile_drift.main([str(path)])
        out = json.loads(capsys.readouterr().out)
        assert out["missing"] == [
            {
                "name": "totally-absent-skill",
                "type": "skill",
                "section": "skills.primary",
            }
        ]

    def test_extra_near_match_and_case_insensitive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        path = _write_profile(tmp_path, '[skills]\nprimary = ["python-lsp"]\n')
        monkeypatch.setattr(pss_profile_drift, "get_all_entries", lambda: FIXTURE_INDEX)
        pss_profile_drift.main([str(path)])
        out = json.loads(capsys.readouterr().out)
        reasons = {item["name"]: item["reason"] for item in out["extra"]}
        assert reasons.get("Python-LSP") == "case-insensitive"
        assert reasons.get("pyton-lsp", "").startswith("near-match:python-lsp")
        # code-review and test-writer are not near python-lsp.
        assert "code-review" not in reasons
        assert "test-writer" not in reasons
        assert out["missing"] == []

    def test_same_scope_hint_is_not_moved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        # Index source "plugin:foo/code-review" has prefix "plugin:foo/",
        # matching the hint — no drift.
        path = _write_profile(
            tmp_path,
            '[skills]\nprimary = ["code-review"]\n\n[pss.scope_hints]\n"code-review" = "plugin:foo/"\n',
        )
        monkeypatch.setattr(pss_profile_drift, "get_all_entries", lambda: FIXTURE_INDEX)
        pss_profile_drift.main([str(path)])
        out = json.loads(capsys.readouterr().out)
        assert out["moved_scope"] == []

    def test_moved_scope_detects_user_vs_plugin(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        path = _write_profile(
            tmp_path,
            '[skills]\nprimary = ["test-writer"]\n\n[pss.scope_hints]\n"test-writer" = "plugin:bar/"\n',
        )
        monkeypatch.setattr(pss_profile_drift, "get_all_entries", lambda: FIXTURE_INDEX)
        pss_profile_drift.main([str(path)])
        out = json.loads(capsys.readouterr().out)
        assert out["moved_scope"] == [
            {
                "name": "test-writer",
                "type": "skill",
                "generated_scope": "plugin:bar/",
                "current_scope": "user:",
            }
        ]

    def test_no_scope_hints_key_moved_scope_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        path = _write_profile(tmp_path, '[skills]\nprimary = ["test-writer"]\n')
        monkeypatch.setattr(pss_profile_drift, "get_all_entries", lambda: FIXTURE_INDEX)
        pss_profile_drift.main([str(path)])
        out = json.loads(capsys.readouterr().out)
        assert out["moved_scope"] == []
        assert out["counts"]["moved_scope"] == 0

    def test_missing_file_exit_2_no_stdout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        monkeypatch.setattr(pss_profile_drift, "get_all_entries", lambda: FIXTURE_INDEX)
        with pytest.raises(SystemExit) as excinfo:
            pss_profile_drift.main([str(tmp_path / "nope.agent.toml")])
        assert excinfo.value.code == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.strip() != ""

    def test_index_unavailable_exit_3(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        def _boom() -> dict:
            raise ImportError("pycozo not installed")

        path = _write_profile(tmp_path, '[skills]\nprimary = ["x"]\n')
        monkeypatch.setattr(pss_profile_drift, "get_all_entries", _boom)
        with pytest.raises(SystemExit) as excinfo:
            pss_profile_drift.main([str(path)])
        assert excinfo.value.code == 3
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.strip() != ""

    def test_counts_mirror_arrays(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        path = _write_profile(
            tmp_path,
            '[skills]\nprimary = ["test-writer", "ghost-skill"]\n',
        )
        monkeypatch.setattr(pss_profile_drift, "get_all_entries", lambda: FIXTURE_INDEX)
        pss_profile_drift.main([str(path)])
        out = json.loads(capsys.readouterr().out)
        assert out["counts"]["missing"] == len(out["missing"])
        assert out["counts"]["extra"] == len(out["extra"])
        assert out["counts"]["moved_scope"] == len(out["moved_scope"])
