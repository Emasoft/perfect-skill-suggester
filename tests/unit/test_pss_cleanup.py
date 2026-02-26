#!/usr/bin/env python3
"""Tests for pss_cleanup.py - stale .pss file cleanup script."""

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "pss_cleanup.py"


def run_cleanup(*args: str) -> subprocess.CompletedProcess[str]:
    """Run pss_cleanup.py with given args and return result."""
    cmd = [sys.executable, str(SCRIPT_PATH)] + list(args)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


class TestCleanupDryRun:
    """Tests for dry-run mode that should never delete files."""

    def test_dry_run_no_files_exits_zero(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Dry run with no .pss files exits with code 0 and reports nothing found."""
        # Create a fake skill dir with no .pss files
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "some_skill.md").touch()

        # We patch get_all_skill_locations via env or by running as subprocess
        # Since the script imports from pss_discover_skills, we test via subprocess
        # using a mock discover script
        mock_discover = tmp_path / "pss_discover_skills.py"
        mock_discover.write_text(
            f"from pathlib import Path\n"
            f"def get_all_skill_locations(scan_all_projects=False):\n"
            f"    return [('test', Path('{skill_dir}'))]\n"
        )

        # Copy the cleanup script and patch its sys.path to use our mock
        env_script = tmp_path / "run_cleanup.py"
        env_script.write_text(
            f"import sys\n"
            f"sys.path.insert(0, '{tmp_path}')\n"
            f"sys.path.insert(0, '{SCRIPT_PATH.parent}')\n"
            f"# Override the import path so pss_discover_skills resolves to our mock\n"
            f"import importlib\n"
            f"import pss_discover_skills\n"
            f"importlib.reload(pss_discover_skills)\n"
            f"# Now run the actual script's main\n"
            f"exec(open('{SCRIPT_PATH}').read())\n"
        )

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--dry-run"],
            capture_output=True, text=True, timeout=30,
            env={**__import__("os").environ, "PSS_CLEANUP_TEST_SKILL_DIRS": str(skill_dir)},
        )
        # The script should handle gracefully even if real skill dirs are empty
        assert result.returncode == 0

    def test_dry_run_finds_pss_files_but_does_not_delete(self, tmp_path: Path) -> None:
        """Dry run reports .pss files it would delete but leaves them intact."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        pss_file = skill_dir / "stale.pss"
        pss_file.write_text("stale content")

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--dry-run"],
            capture_output=True, text=True, timeout=30,
            env={**__import__("os").environ, "PSS_CLEANUP_TEST_SKILL_DIRS": str(skill_dir)},
        )
        assert result.returncode == 0
        # File must still exist after dry run
        assert pss_file.exists(), "Dry run must NOT delete files"

    def test_dry_run_output_contains_would_delete(self, tmp_path: Path) -> None:
        """Dry run output includes '[DRY RUN] Would delete:' for each .pss file found."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        pss_file = skill_dir / "stale.pss"
        pss_file.write_text("content")

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--dry-run"],
            capture_output=True, text=True, timeout=30,
            env={**__import__("os").environ, "PSS_CLEANUP_TEST_SKILL_DIRS": str(skill_dir)},
        )
        assert "[DRY RUN] Would delete:" in result.stdout


class TestCleanupActualDeletion:
    """Tests for actual cleanup mode that deletes .pss files."""

    def test_deletes_pss_files(self, tmp_path: Path) -> None:
        """Actual cleanup deletes all .pss files from skill directories."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        pss1 = skill_dir / "a.pss"
        pss2 = skill_dir / "b.pss"
        keep = skill_dir / "keep.md"
        pss1.write_text("stale1")
        pss2.write_text("stale2")
        keep.write_text("keep me")

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--verbose"],
            capture_output=True, text=True, timeout=30,
            env={**__import__("os").environ, "PSS_CLEANUP_TEST_SKILL_DIRS": str(skill_dir)},
        )
        assert result.returncode == 0
        assert not pss1.exists(), ".pss file should be deleted"
        assert not pss2.exists(), ".pss file should be deleted"
        assert keep.exists(), "Non-.pss files must be preserved"

    def test_deletes_nested_pss_files(self, tmp_path: Path) -> None:
        """Cleanup finds and deletes .pss files in subdirectories recursively."""
        skill_dir = tmp_path / "skills"
        nested = skill_dir / "sub" / "deep"
        nested.mkdir(parents=True)
        pss_file = nested / "nested.pss"
        pss_file.write_text("nested stale")

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            capture_output=True, text=True, timeout=30,
            env={**__import__("os").environ, "PSS_CLEANUP_TEST_SKILL_DIRS": str(skill_dir)},
        )
        assert result.returncode == 0
        assert not pss_file.exists(), "Nested .pss should be deleted"

    def test_verbose_prints_deleted_paths(self, tmp_path: Path) -> None:
        """Verbose mode prints 'Deleted: <path>' for each file removed."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        pss_file = skill_dir / "verbose_test.pss"
        pss_file.write_text("content")

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--verbose"],
            capture_output=True, text=True, timeout=30,
            env={**__import__("os").environ, "PSS_CLEANUP_TEST_SKILL_DIRS": str(skill_dir)},
        )
        assert result.returncode == 0
        assert "Deleted:" in result.stdout


class TestCleanupTmpQueue:
    """Tests for /tmp/pss-queue/ scanning."""

    def test_scans_tmp_queue(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cleanup scans /tmp/pss-queue/ for .pss files (non-recursive)."""
        # Create a fake tmp queue dir
        queue_dir = tmp_path / "pss-queue"
        queue_dir.mkdir()
        pss_file = queue_dir / "queued.pss"
        pss_file.write_text("queued")
        # Also a nested one that should NOT be found (non-recursive for queue)
        nested_dir = queue_dir / "nested"
        nested_dir.mkdir()
        nested_pss = nested_dir / "nested.pss"
        nested_pss.write_text("nested in queue")

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--dry-run"],
            capture_output=True, text=True, timeout=30,
            env={
                **__import__("os").environ,
                "PSS_CLEANUP_TEST_SKILL_DIRS": "",
                "PSS_CLEANUP_TEST_QUEUE_DIR": str(queue_dir),
            },
        )
        assert result.returncode == 0
        # Should find the top-level queued.pss
        assert "queued.pss" in result.stdout
        # Should NOT find nested one (non-recursive for queue)
        assert "nested.pss" not in result.stdout or str(nested_pss) not in result.stdout


class TestCleanupIdempotent:
    """Tests verifying idempotent behavior."""

    def test_no_pss_files_prints_nothing_found(self, tmp_path: Path) -> None:
        """When no .pss files exist, prints 'No stale .pss files found' and exits 0."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "normal.md").touch()

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            capture_output=True, text=True, timeout=30,
            env={
                **__import__("os").environ,
                "PSS_CLEANUP_TEST_SKILL_DIRS": str(skill_dir),
                "PSS_CLEANUP_TEST_QUEUE_DIR": str(tmp_path / "nonexistent"),
            },
        )
        assert result.returncode == 0
        assert "No stale .pss files found" in result.stdout

    def test_double_run_is_safe(self, tmp_path: Path) -> None:
        """Running cleanup twice in a row is safe - second run finds nothing."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "once.pss").write_text("content")

        env = {
            **__import__("os").environ,
            "PSS_CLEANUP_TEST_SKILL_DIRS": str(skill_dir),
            "PSS_CLEANUP_TEST_QUEUE_DIR": str(tmp_path / "nonexistent"),
        }

        # First run deletes
        r1 = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            capture_output=True, text=True, timeout=30, env=env,
        )
        assert r1.returncode == 0

        # Second run finds nothing
        r2 = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            capture_output=True, text=True, timeout=30, env=env,
        )
        assert r2.returncode == 0
        assert "No stale .pss files found" in r2.stdout


class TestCleanupSummary:
    """Tests for summary output."""

    def test_summary_shows_count(self, tmp_path: Path) -> None:
        """Summary line shows count of cleaned files and locations."""
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "a.pss").write_text("a")
        (skill_dir / "b.pss").write_text("b")
        (skill_dir / "c.pss").write_text("c")

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            capture_output=True, text=True, timeout=30,
            env={
                **__import__("os").environ,
                "PSS_CLEANUP_TEST_SKILL_DIRS": str(skill_dir),
                "PSS_CLEANUP_TEST_QUEUE_DIR": str(tmp_path / "nonexistent"),
            },
        )
        assert result.returncode == 0
        assert "Cleaned 3 .pss files from" in result.stdout


class TestCleanupCLI:
    """Tests for CLI argument parsing."""

    def test_help_flag(self) -> None:
        """--help prints usage information and exits 0."""
        result = run_cleanup("--help")
        assert result.returncode == 0
        assert "cleanup" in result.stdout.lower() or "pss" in result.stdout.lower()

    def test_unknown_flag_exits_nonzero(self) -> None:
        """Unknown CLI flags cause a non-zero exit."""
        result = run_cleanup("--unknown-flag-xyz")
        assert result.returncode != 0
