#!/usr/bin/env python3
"""PSS Reindex — Rebuild the skill index using the deterministic Rust pipeline.

Usage:
    uv run scripts/pss_reindex.py                      # All projects (default)
    uv run scripts/pss_reindex.py --index-only-this-project  # Current project + user scope only

Steps:
    1. Back up old index
    2. Discover + Enrich + Merge (3-stage shell pipeline)
    3. Build CozoDB index
    4. Aggregate domain registry
    5. Clean stale .pss files
    6. Report results
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path


from pss_paths import get_claude_config_dir


def resolve_plugin_root() -> Path:
    """Resolve the plugin root directory from env var or plugin cache."""
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return Path(env_root)
    # Fallback: find latest version in plugin cache
    cache_base = (
        Path.home()
        / ".claude"
        / "plugins"
        / "cache"
        / "emasoft-plugins"
        / "perfect-skill-suggester"
    )
    if not cache_base.exists():
        sys.exit(f"ERROR: Plugin cache not found: {cache_base}")

    def _version_key(p: Path) -> tuple[int, ...]:
        """Parse '2.3.28' into (2, 3, 28) for correct numeric sorting."""
        try:
            return tuple(int(x) for x in p.name.split("."))
        except ValueError:
            return (0,)

    versions = sorted([d for d in cache_base.iterdir() if d.is_dir()], key=_version_key)
    if not versions:
        sys.exit(f"ERROR: No versions found in {cache_base}")
    return versions[-1]


def resolve_binary(plugin_root: Path) -> Path:
    """Resolve the PSS binary for the current platform."""
    system = platform.system()
    machine = platform.machine()
    if system == "Darwin" and machine == "arm64":
        name = "pss-darwin-arm64"
    elif system == "Darwin" and machine == "x86_64":
        name = "pss-darwin-x86_64"
    elif system == "Linux" and machine == "x86_64":
        name = "pss-linux-x86_64"
    elif system == "Linux" and machine == "aarch64":
        name = "pss-linux-arm64"
    else:
        sys.exit(f"ERROR: Unsupported platform: {system}/{machine}")
    binary = plugin_root / "src" / "skill-suggester" / "bin" / name
    if not binary.exists() or not os.access(binary, os.X_OK):
        sys.exit(f"ERROR: Binary not found or not executable: {binary}")
    return binary


def backup_index(cache_dir: Path) -> Path:
    """Back up existing index files (does NOT delete originals — crash-safe).

    The old index stays in place until the new one is verified and swapped in.
    Backup is kept as a safety net for manual recovery only.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(tempfile.gettempdir()) / f"pss-backup-{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for name in ("skill-index.json", "skill-index.db"):
        src = cache_dir / name
        if src.exists():
            shutil.copy2(src, backup_dir / name)
    return backup_dir


def run_pipeline(
    scripts_dir: Path, binary: Path, staging_index: Path, *, all_projects: bool = True
) -> int:
    """Run the 3-stage pipeline: discover | enrich | merge.

    Writes to a staging index file (not the live one) for crash safety.
    Uses shell pipes so that discover's stderr warnings don't kill the pipeline.

    Args:
        all_projects: If True (default), discover scans all registered projects.
                      If False, only current project + user scope.
    Returns the pipeline exit code.
    """
    warnings_file = Path(tempfile.gettempdir()) / "pss-discover-warnings.txt"
    stats_file = Path(tempfile.gettempdir()) / "pss-pass1-stats.txt"
    discover_flags = "--jsonl --all-projects" if all_projects else "--jsonl"
    cmd = (
        f'python3 "{scripts_dir / "pss_discover.py"}" {discover_flags} 2>"{warnings_file}" '
        f'| "{binary}" --pass1-batch 2>"{stats_file}" '
        f'| python3 "{scripts_dir / "pss_merge_queue.py"}" --batch-stdin --index "{staging_index}"'
    )
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"ERROR: Pipeline exited with code {result.returncode}", file=sys.stderr)
    return result.returncode


def verify_index_file(index_file: Path) -> int:
    """Verify an index file has elements. Returns the element count."""
    if not index_file.exists():
        return 0
    try:
        data = json.loads(index_file.read_text())
        return data.get("skill_count", len(data.get("skills", {})))
    except (json.JSONDecodeError, OSError):
        return 0


def build_db(binary: Path) -> None:
    """Build the CozoDB index for fast scoring."""
    subprocess.run([str(binary), "--build-db"], check=True)


def aggregate_domains(scripts_dir: Path) -> None:
    """Aggregate the domain registry."""
    subprocess.run(
        ["python3", str(scripts_dir / "pss_aggregate_domains.py")], check=True
    )


def cleanup_stale(scripts_dir: Path) -> None:
    """Clean stale .pss sidecar files (best-effort)."""
    subprocess.run(
        ["python3", str(scripts_dir / "pss_cleanup.py"), "--all-projects"],
        capture_output=True,
    )


def human_size(path: Path) -> str:
    """Return human-readable file size."""
    if not path.exists():
        return "?"
    sz: float = path.stat().st_size
    for unit in ("B", "K", "M", "G"):
        if sz < 1024:
            return f"{sz:.0f}{unit}" if unit == "B" else f"{sz:.1f}{unit}"
        sz /= 1024
    return f"{sz:.1f}T"


def _cleanup_lockfile(cache_dir: Path) -> None:
    """Remove the PID lockfile and any stale staging/tmp files from prior crashes."""
    lock_path = cache_dir / "skill-index.reindex.pid"
    lock_path.unlink(missing_ok=True)
    for stale in ("skill-index.json.tmp", "skill-index.staging.json"):
        (cache_dir / stale).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild the PSS skill index")
    parser.add_argument(
        "--index-only-this-project",
        action="store_true",
        help="Index only current project + user scope (default: all projects)",
    )
    args = parser.parse_args()
    all_projects = not args.index_only_this_project

    plugin_root = resolve_plugin_root()
    scripts_dir = plugin_root / "scripts"
    binary = resolve_binary(plugin_root)
    cache_dir = get_claude_config_dir() / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    live_index = cache_dir / "skill-index.json"
    staging_index = cache_dir / "skill-index.staging.json"

    # Step 1: Back up (old index stays in place — crash-safe)
    backup_dir = backup_index(cache_dir)

    # Step 2: Pipeline writes to staging file (not the live index)
    # If crash/blackout happens here, old index is still intact and usable
    staging_index.unlink(missing_ok=True)
    run_pipeline(scripts_dir, binary, staging_index, all_projects=all_projects)

    # Verify the staging index
    element_count = verify_index_file(staging_index)
    if element_count == 0:
        print("ERROR: Pipeline produced 0 elements. Old index preserved.")
        staging_index.unlink(missing_ok=True)
        warnings_file = Path(tempfile.gettempdir()) / "pss-discover-warnings.txt"
        print(f"Check {warnings_file} for details.")
        _cleanup_lockfile(cache_dir)
        sys.exit(1)

    # Step 3: Atomic swap — staging replaces live index in one syscall
    # os.replace() is atomic on the same filesystem (POSIX rename guarantee)
    os.replace(staging_index, live_index)

    # Step 4: Remove old CozoDB (will be rebuilt from new index)
    (cache_dir / "pss-skill-index.db").unlink(missing_ok=True)

    # Step 5: Build CozoDB from new index
    build_db(binary)

    # Step 6: Aggregate domains
    aggregate_domains(scripts_dir)

    # Step 7: Clean stale .pss files
    cleanup_stale(scripts_dir)

    # Step 8: Clean up auto-reindex lockfile (if spawned by hook)
    _cleanup_lockfile(cache_dir)

    # Report
    stats_file = Path(tempfile.gettempdir()) / "pss-pass1-stats.txt"
    pass1_stats = stats_file.read_text().strip() if stats_file.exists() else "unknown"
    index_size = human_size(cache_dir / "skill-index.json")

    print()
    print("PSS Reindex Complete")
    print("====================")
    print(f"Elements: {element_count}")
    print(f"Index: ~/.claude/cache/skill-index.json ({index_size})")
    print(f"Pass 1: {pass1_stats}")
    print(f"Backup: {backup_dir}")


if __name__ == "__main__":
    main()
