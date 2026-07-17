"""F7 (TRDD-1Z8SGQ7N): manifest v2 `exhaustive_scopes` coverage claim.

The discoverer is the only component that knows whether a run enumerated a
scope completely, so it states that claim on the manifest line. The claim is
load-bearing: the Rust writer removes any active element of a claimed scope it
did not observe, so an over-claim mass-deletes real history. These tests pin
the exact flag→claim mapping, driving the REAL script via subprocess (no mocks
— a mocked filesystem would prove nothing about the claim's honesty).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DISCOVER = REPO_ROOT / "scripts" / "pss_discover.py"

# The exact output space of scope_from_discovery_source (temporal.rs) — a claim
# naming anything else would match no element and be silently inert.
VALID_SCOPES = {"user", "project", "plugin", "marketplace", "local"}


def run_discover(*flags: str) -> dict:
    """Run the real discoverer and return its parsed manifest line.

    Asserts the manifest is the FIRST line: the writer must read the coverage
    claim before it processes any observation, so position is part of the wire
    contract, not an accident of ordering.
    """
    proc = subprocess.run(
        [sys.executable, str(DISCOVER), "--jsonl", *flags],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=600,
    )
    assert proc.returncode == 0, f"discover failed: {proc.stderr[-2000:]}"
    first = proc.stdout.split("\n", 1)[0]
    manifest = json.loads(first)
    assert manifest.get("_pss_manifest") is True, "first line must be the manifest"
    return manifest


@pytest.fixture(scope="module")
def full_run() -> dict:
    """A full, unfiltered run — the only shape that may claim every scope."""
    return run_discover("--all-projects")


def test_full_run_emits_manifest_version_2(full_run: dict) -> None:
    """A full run bumps the manifest to v2 and keeps visited_scope_paths."""
    assert full_run["_pss_manifest_version"] == 2
    # v2 is additive: v1's key must survive so an older Rust binary that ignores
    # exhaustive_scopes still behaves exactly as it does today.
    assert isinstance(full_run["visited_scope_paths"], list)
    assert full_run["visited_scope_paths"], "a full run must visit some scope_path"


def test_full_run_claims_every_scope(full_run: dict) -> None:
    """Spec §6.6: a full `--jsonl --all-projects` run claims all five scopes."""
    claimed = set(full_run["exhaustive_scopes"])
    assert claimed >= VALID_SCOPES, (
        f"full run must claim every scope, got {sorted(claimed)}. If a scope is "
        "missing, the run hit a scan error (check stderr) — that is the guard "
        "working, not necessarily a code bug."
    )


def test_claim_only_uses_known_scope_values(full_run: dict) -> None:
    """A claim outside scope_from_discovery_source's output space is inert."""
    assert set(full_run["exhaustive_scopes"]) <= VALID_SCOPES


def test_name_filter_claims_nothing() -> None:
    """Spec §6.7: `--name X` sees one element, so it can claim no scope."""
    assert run_discover("--all-projects", "--name", "pss-usage")["exhaustive_scopes"] == []


def test_type_filter_claims_nothing() -> None:
    """Spec §6.8: `--type skill` skips every other type — not exhaustive."""
    assert run_discover("--all-projects", "--type", "skill")["exhaustive_scopes"] == []


def test_without_all_projects_no_project_or_local_claim() -> None:
    """Spec §6.9: other projects' elements are unreachable without
    --all-projects, so claiming `project`/`local` would remove all of them."""
    claimed = set(run_discover()["exhaustive_scopes"])
    assert "project" not in claimed
    assert "local" not in claimed
    # …but the scopes that ARE fully enumerated must still be claimed, or the
    # fix would regress to today's inoperative detection for plain runs.
    assert claimed == {"user", "plugin", "marketplace"}


def test_exclude_inactive_plugins_drops_plugin_and_marketplace() -> None:
    """Spec §6.10: with disabled plugins skipped, an unobserved element may be
    merely DISABLED, not removed — the F2 confusion. Drop both scopes."""
    claimed = set(run_discover("--all-projects", "--exclude-inactive-plugins")["exhaustive_scopes"])
    assert "plugin" not in claimed
    assert "marketplace" not in claimed
    assert claimed == {"user", "project", "local"}


def test_project_only_claims_nothing_even_with_all_projects() -> None:
    """`--project-only` forces scan_all_projects False, so the run only sees the
    CWD project and must claim nothing.

    DEVIATION from spec §6.11, which expects ["project"] when --all-projects is
    also passed. That is unreachable: pss_discover.main() computes
    `scan_all_projects = args.all_projects and not (args.project_only or
    args.user_only)`, so --all-projects is inert under --project-only and every
    OTHER project's elements go unobserved. Claiming "project" there would
    delete them all. Under-claiming is the spec's own tie-breaker.
    """
    assert run_discover("--project-only")["exhaustive_scopes"] == []
    assert run_discover("--project-only", "--all-projects")["exhaustive_scopes"] == []


def test_user_only_claims_user() -> None:
    """Spec §6.12: user scope is enumerated in full regardless of flags."""
    assert run_discover("--user-only")["exhaustive_scopes"] == ["user"]


def test_empty_scan_claims_nothing(tmp_path: Path) -> None:
    """A scan that found NOTHING is a broken scan, not an empty machine —
    claiming exhaustive there would wipe the whole index in one pass.

    Driven with HOME pointed at an empty dir so every scope root is genuinely
    absent, which is the real shape of the catastrophic case.
    """
    proc = subprocess.run(
        [sys.executable, str(DISCOVER), "--jsonl", "--all-projects"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
        timeout=600,
    )
    assert proc.returncode == 0, f"discover failed: {proc.stderr[-2000:]}"
    manifest = json.loads(proc.stdout.split("\n", 1)[0])
    assert manifest["element_count"] == 0, "fixture must produce an empty scan"
    assert manifest["exhaustive_scopes"] == []
