#!/usr/bin/env python3
"""
Perfect Skill Suggester - Stale .pss File Cleanup Script.

Finds and removes stale .pss files left behind by crashed agents or by
pss_generate.py. Scans all skill directories discovered by pss_discover_skills
plus the /tmp/pss-queue/ staging directory.

Usage:
    python3 pss_cleanup.py [--dry-run] [--all-projects] [--verbose]

Options:
    --dry-run        Show what would be deleted without actually deleting
    --all-projects   Scan all projects registered in ~/.claude.json
    --verbose        Print detailed per-file and per-location information

Environment (for testing only):
    PSS_CLEANUP_TEST_SKILL_DIRS  Comma-separated skill dir paths to use instead
                                 of calling get_all_skill_locations()
    PSS_CLEANUP_TEST_QUEUE_DIR   Override /tmp/pss-queue/ with a custom path
"""

import argparse
import os
import sys
from pathlib import Path


def _import_discover_skills() -> object:
    """Import get_all_skill_locations from the sibling pss_discover_skills module.

    Adds the scripts/ directory to sys.path so pss_discover_skills can be
    found as a sibling script regardless of how pss_cleanup.py is invoked.
    """
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import pss_discover_skills  # noqa: E402 -- dynamic path manipulation required

    return pss_discover_skills


def _get_skill_locations(scan_all_projects: bool) -> list[tuple[str, Path]]:
    """Return skill directory locations, respecting test overrides.

    When the PSS_CLEANUP_TEST_SKILL_DIRS env var is set, it is used instead of
    calling get_all_skill_locations() so tests can inject temp directories.
    """
    test_dirs = os.environ.get("PSS_CLEANUP_TEST_SKILL_DIRS")
    if test_dirs is not None:
        # Test mode: parse comma-separated paths (empty string = no dirs)
        if not test_dirs.strip():
            return []
        return [("test", Path(d.strip())) for d in test_dirs.split(",") if d.strip()]

    # Production mode: use the real discovery function
    discover = _import_discover_skills()
    return discover.get_all_skill_locations(scan_all_projects=scan_all_projects)  # type: ignore[union-attr]


def _get_queue_dir() -> Path:
    """Return the pss-queue directory path, respecting test overrides."""
    test_queue = os.environ.get("PSS_CLEANUP_TEST_QUEUE_DIR")
    if test_queue is not None:
        return Path(test_queue)
    return Path("/tmp/pss-queue")


def _collect_pss_files(
    locations: list[tuple[str, Path]],
    queue_dir: Path,
) -> dict[str, list[Path]]:
    """Collect all .pss files from skill directories and the queue directory.

    Args:
        locations: List of (source_label, skill_directory_path) tuples.
        queue_dir: Path to the pss-queue staging directory.

    Returns:
        Dict mapping source label to list of .pss file paths found there.
    """
    results: dict[str, list[Path]] = {}

    # Scan each skill directory recursively for .pss files
    for source, skill_dir in locations:
        if not skill_dir.exists() or not skill_dir.is_dir():
            continue
        pss_files = sorted(skill_dir.rglob("*.pss"))
        if pss_files:
            results[f"{source}:{skill_dir}"] = pss_files

    # Scan queue directory non-recursively for .pss files
    if queue_dir.exists() and queue_dir.is_dir():
        # glob("*.pss") is non-recursive -- only top-level matches
        queue_files = sorted(queue_dir.glob("*.pss"))
        if queue_files:
            results[f"queue:{queue_dir}"] = queue_files

    return results


def _run_cleanup(
    collected: dict[str, list[Path]],
    *,
    dry_run: bool,
    verbose: bool,
) -> int:
    """Delete (or report) collected .pss files.

    Args:
        collected: Dict from _collect_pss_files.
        dry_run: If True, only print what would be deleted.
        verbose: If True, print per-file details.

    Returns:
        Total number of .pss files processed.
    """
    total_deleted = 0

    for source_label, pss_files in collected.items():
        if verbose or dry_run:
            print(f"\n  Location: {source_label} ({len(pss_files)} file(s))")

        for pss_path in pss_files:
            if dry_run:
                print(f"  [DRY RUN] Would delete: {pss_path}")
            else:
                pss_path.unlink()
                if verbose:
                    print(f"  Deleted: {pss_path}")
            total_deleted += 1

    return total_deleted


def main() -> int:
    """Entry point for pss_cleanup CLI.

    Returns:
        Exit code: 0 on success, 1 on error.
    """
    parser = argparse.ArgumentParser(
        description="Clean up stale .pss files left by crashed agents or pss_generate.py.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    parser.add_argument(
        "--all-projects",
        action="store_true",
        help="Scan all projects registered in ~/.claude.json",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed per-file and per-location information",
    )
    args = parser.parse_args()

    try:
        # Discover skill directories
        locations = _get_skill_locations(scan_all_projects=args.all_projects)
        queue_dir = _get_queue_dir()

        # Collect all .pss files
        collected = _collect_pss_files(locations, queue_dir)

        if not collected:
            print("No stale .pss files found.")
            return 0

        # Count total files across all locations
        total_files = sum(len(files) for files in collected.values())
        location_count = len(collected)

        if args.dry_run:
            print(f"[DRY RUN] Found {total_files} .pss file(s) in {location_count} location(s):")

        # Run cleanup (or dry-run report)
        processed = _run_cleanup(collected, dry_run=args.dry_run, verbose=args.verbose)

        # Print summary
        if args.dry_run:
            print(f"\n[DRY RUN] Would clean {processed} .pss files from {location_count} locations")
        else:
            print(f"Cleaned {processed} .pss files from {location_count} locations")

            if args.verbose:
                # Per-location breakdown
                print("\nPer-location breakdown:")
                for source_label, pss_files in collected.items():
                    print(f"  {source_label}: {len(pss_files)} file(s)")

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
