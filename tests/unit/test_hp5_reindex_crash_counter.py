"""HP-5 (audit 20260514): max-retry counter on auto-reindex.

If pss_reindex.py crashes hard (SIGSEGV, OOM, syntax error) the PID
lockfile is never written. The dead-PID branch in _maybe_auto_reindex
respawns it for every prompt, forever. HP-5 introduces a crash log:
3 crashes in 1 hour disables auto-reindex with a user-facing warning.

These tests exercise the helpers in isolation (no actual subprocess
spawning).
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture(scope="module")
def hook():
    spec = importlib.util.spec_from_file_location("pss_hook", _SCRIPTS / "pss_hook.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_record_crash_writes_timestamp_line(hook, tmp_path):
    """HP-5: each call appends one ISO-8601 line."""
    log = tmp_path / "crashes.log"
    hook._record_reindex_crash(log)
    hook._record_reindex_crash(log)
    lines = log.read_text().strip().split("\n")
    assert len(lines) == 2
    for line in lines:
        datetime.fromisoformat(line)  # must round-trip


def test_recent_crashes_returns_only_within_window(hook, tmp_path):
    """HP-5: lines older than the window must be excluded."""
    log = tmp_path / "crashes.log"
    now = datetime.now(timezone.utc)
    with open(log, "w") as f:
        f.write((now - timedelta(hours=2)).isoformat() + "\n")  # outside 1h window
        f.write((now - timedelta(minutes=5)).isoformat() + "\n")  # inside
        f.write(now.isoformat() + "\n")  # inside
    recent = hook._recent_reindex_crashes(log, window_seconds=3600)
    assert len(recent) == 2


def test_recent_crashes_prunes_old_entries(hook, tmp_path):
    """HP-5: entries older than the window are pruned from the file."""
    log = tmp_path / "crashes.log"
    now = datetime.now(timezone.utc)
    with open(log, "w") as f:
        f.write((now - timedelta(hours=2)).isoformat() + "\n")
        f.write(now.isoformat() + "\n")
    hook._recent_reindex_crashes(log, window_seconds=3600)
    lines = log.read_text().strip().split("\n")
    # Only the recent (in-window) line should remain.
    assert len(lines) == 1
    assert lines[0]  # non-empty


def test_recent_crashes_missing_file_returns_empty(hook, tmp_path):
    """HP-5: no crash log → empty list, no error."""
    log = tmp_path / "nonexistent.log"
    assert hook._recent_reindex_crashes(log, window_seconds=3600) == []


def test_recent_crashes_malformed_lines_skipped(hook, tmp_path):
    """HP-5: lines that don't parse as ISO-8601 are ignored, not crashes."""
    log = tmp_path / "crashes.log"
    now = datetime.now(timezone.utc)
    log.write_text(
        "garbage line\n"
        + now.isoformat()
        + "\n"
        + "another bad line\n"
    )
    recent = hook._recent_reindex_crashes(log, window_seconds=3600)
    assert len(recent) == 1  # garbage lines silently skipped


def test_recent_crashes_threshold_three_in_hour(hook, tmp_path):
    """HP-5: 3 crashes in 1 h → the trigger condition we check in
    _maybe_auto_reindex. Verifies the helper returns the right count."""
    log = tmp_path / "crashes.log"
    now = datetime.now(timezone.utc)
    with open(log, "w") as f:
        for offset_min in (50, 30, 10):
            f.write((now - timedelta(minutes=offset_min)).isoformat() + "\n")
    recent = hook._recent_reindex_crashes(log, window_seconds=3600)
    assert len(recent) == 3
