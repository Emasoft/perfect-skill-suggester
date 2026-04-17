#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pycozo[embedded]>=0.7.6",
# ]
# ///
"""PSS Reindex — Rebuild the skill index using the deterministic Rust pipeline.

Usage:
    uv run scripts/pss_reindex.py                           # All projects, all plugins
    uv run scripts/pss_reindex.py --exclude-inactive-plugins  # Skip disabled plugins

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


from pss_paths import get_data_dir


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
    binary = plugin_root / "bin" / name
    if not binary.exists() or not os.access(binary, os.X_OK):
        sys.exit(f"ERROR: Binary not found or not executable: {binary}")
    return binary


def backup_index(cache_dir: Path) -> Path:
    """Back up existing index files (does NOT delete originals — crash-safe).

    The old index stays in place until the new one is verified and swapped in.
    Backup is kept as a safety net for manual recovery only.
    Non-fatal: backup failure does not block reindexing.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(tempfile.gettempdir()) / f"pss-backup-{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for name in ("skill-index.json", "pss-skill-index.db"):
        src = cache_dir / name
        try:
            if src.exists():
                shutil.copy2(src, backup_dir / name)
        except OSError as e:
            # Backup is best-effort — don't block reindex if copy fails
            print(f"WARNING: Could not back up {src}: {e}", file=sys.stderr)
    return backup_dir


def run_pipeline(
    scripts_dir: Path,
    binary: Path,
    staging_index: Path,
    *,
    exclude_inactive_plugins: bool = False,
) -> int:
    """Run the 3-stage pipeline: discover | enrich | merge.

    Writes to a staging index file (not the live one) for crash safety.
    Uses shell pipes so that discover's stderr warnings don't kill the pipeline.

    Args:
        exclude_inactive_plugins: If True, pass --exclude-inactive-plugins to discover
                                  to skip plugins disabled in settings.json.
    Returns the pipeline exit code.
    """
    import shlex

    warnings_file = Path(tempfile.gettempdir()) / "pss-discover-warnings.txt"
    stats_file = Path(tempfile.gettempdir()) / "pss-pass1-stats.txt"
    discover_flags = "--jsonl --all-projects"
    if exclude_inactive_plugins:
        discover_flags += " --exclude-inactive-plugins"
    # Use shlex.quote on all interpolated paths to prevent shell injection
    # (CLAUDE_PLUGIN_ROOT or binary paths with special chars could break quoting)
    q = shlex.quote
    # set -o pipefail ensures the pipeline fails if ANY stage fails
    # (without it, only the last stage's exit code is reported)
    cmd = (
        f'set -o pipefail; '
        f'{q(sys.executable)} {q(str(scripts_dir / "pss_discover.py"))} {discover_flags} 2>{q(str(warnings_file))} '
        f'| {q(str(binary))} --pass1-batch 2>{q(str(stats_file))} '
        f'| {q(sys.executable)} {q(str(scripts_dir / "pss_merge_queue.py"))} --batch-stdin --index {q(str(staging_index))}'
    )
    try:
        result = subprocess.run(cmd, shell=True, timeout=300)  # 5-minute timeout
    except subprocess.TimeoutExpired:
        print("ERROR: Pipeline timed out after 5 minutes", file=sys.stderr)
        return 1
    if result.returncode != 0:
        print(f"ERROR: Pipeline exited with code {result.returncode}", file=sys.stderr)
    return result.returncode


def verify_index_file(index_file: Path) -> int:
    """Verify an index file has elements. Returns the element count.

    Phase C note: `index_file` is a legacy staging-JSON path. If it exists
    and contains rows, we trust it. Otherwise we fall through to the CozoDB
    row count (verify_cozodb_has_rows) — the JSON staging file is no longer
    produced by the merge queue in Phase C, so this function returns 0 for
    callers that still only look at JSON.
    """
    if not index_file.exists():
        return 0
    try:
        data = json.loads(index_file.read_text())
        return data.get("skill_count", len(data.get("skills", {})))
    except (json.JSONDecodeError, OSError):
        return 0


def verify_cozodb_has_rows() -> int:
    """Return the CozoDB row count, or 0 if DB is missing or pycozo unavailable.

    Phase C (v3.0.0): CozoDB is the only canonical store after the merge
    pipeline. This is the authoritative post-pipeline verification.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from pss_cozodb import count_skills, get_db_path  # type: ignore[import-not-found]
    except ImportError:
        return 0
    if not get_db_path().exists():
        return 0
    return count_skills()


def aggregate_domains(scripts_dir: Path) -> None:
    """Aggregate the domain registry."""
    subprocess.run(
        [sys.executable, str(scripts_dir / "pss_aggregate_domains.py")],
        check=True,
        timeout=120,
    )


def cleanup_stale(scripts_dir: Path) -> None:
    """Clean stale .pss sidecar files (best-effort)."""
    subprocess.run(
        [sys.executable, str(scripts_dir / "pss_cleanup.py"), "--all-projects"],
        capture_output=True,
        timeout=60,
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
    """Remove the PID lockfile (only if it belongs to this process or a dead process)
    and any stale staging/tmp files from prior crashes."""
    lock_path = cache_dir / "skill-index.reindex.pid"
    if lock_path.exists():
        try:
            pid = int(lock_path.read_text().strip())
            # Only remove if PID matches this process or the process is dead
            if pid == os.getpid() or not _is_pid_alive(pid):
                lock_path.unlink(missing_ok=True)
        except (ValueError, OSError):
            # Corrupt lockfile — safe to remove
            lock_path.unlink(missing_ok=True)
    for stale in ("skill-index.json.tmp", "skill-index.staging.json"):
        (cache_dir / stale).unlink(missing_ok=True)


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    try:
        os.kill(pid, 0)  # Signal 0 = existence check, no actual signal sent
        return True
    except OSError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild the PSS skill index")
    parser.add_argument(
        "--exclude-inactive-plugins",
        action="store_true",
        help="Skip plugins disabled in ~/.claude/settings.json enabledPlugins",
    )
    args = parser.parse_args()

    plugin_root = resolve_plugin_root()
    scripts_dir = plugin_root / "scripts"
    binary = resolve_binary(plugin_root)
    cache_dir = get_data_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Phase C: live_index is no longer written by reindex (CozoDB is the only
    # canonical store). staging_index is kept because the pipeline still
    # accepts --index <path> and will read it as the "previous state" seed
    # if it exists, but no JSON file is produced as output.
    staging_index = cache_dir / "skill-index.staging.json"

    # Step 1: Back up (old index stays in place — crash-safe)
    backup_dir = backup_index(cache_dir)

    # Step 2: Pipeline writes to staging file (not the live index)
    # If crash/blackout happens here, old index is still intact and usable
    staging_index.unlink(missing_ok=True)
    pipeline_rc = run_pipeline(
        scripts_dir,
        binary,
        staging_index,
        exclude_inactive_plugins=args.exclude_inactive_plugins,
    )
    if pipeline_rc != 0:
        print(
            f"ERROR: Pipeline failed with exit code {pipeline_rc}. Old index preserved.",
            file=sys.stderr,
        )
        staging_index.unlink(missing_ok=True)
        _cleanup_lockfile(cache_dir)
        sys.exit(1)

    # Verify the CozoDB — the merge pipeline writes directly to CozoDB now
    # (Phase C v3.0.0), so the staging JSON file is no longer produced.
    element_count = verify_cozodb_has_rows()
    if element_count == 0:
        print("ERROR: Pipeline produced 0 elements. Old index preserved.")
        staging_index.unlink(missing_ok=True)
        warnings_file = Path(tempfile.gettempdir()) / "pss-discover-warnings.txt"
        print(f"Check {warnings_file} for details.")
        _cleanup_lockfile(cache_dir)
        sys.exit(1)

    # Phase C: no JSON swap. The live skill-index.json is not auto-maintained.
    # Users who want a JSON snapshot for git diff run `pss export --json`. If
    # a legacy live_index.json exists from a prior <v3.0.0 install, we leave
    # it in place (harmless, read by nothing) rather than deleting — that
    # would be a surprising side-effect of reindex. Clean up only the staging
    # file (never promoted in Phase C).
    staging_index.unlink(missing_ok=True)

    # Phase C note: the Rust --build-db subcommand has been removed. The Python
    # merge writer (pss_merge_queue._sync_cozodb) populates CozoDB directly
    # during the merge stage under the same file lock, so there is no separate
    # build step any more. First_indexed_at timestamps are preserved by the
    # _snapshot_prior_timestamps helper before :replace.

    # Step 6: Aggregate domains (non-fatal)
    try:
        aggregate_domains(scripts_dir)
    except subprocess.CalledProcessError as e:
        print(
            f"WARNING: Domain aggregation failed (code {e.returncode}).",
            file=sys.stderr,
        )
    except subprocess.TimeoutExpired:
        print("WARNING: Domain aggregation timed out after 120s.", file=sys.stderr)

    # Step 7: Clean stale .pss files (non-fatal)
    try:
        cleanup_stale(scripts_dir)
    except subprocess.TimeoutExpired:
        print("WARNING: Stale file cleanup timed out after 60s.", file=sys.stderr)

    # Step 8: Clean up auto-reindex lockfile (if spawned by hook)
    _cleanup_lockfile(cache_dir)

    # Report
    stats_file = Path(tempfile.gettempdir()) / "pss-pass1-stats.txt"
    try:
        pass1_stats = stats_file.read_text().strip()
    except OSError:
        pass1_stats = "unknown"
    db_size = human_size(cache_dir / "pss-skill-index.db")

    print()
    print("PSS Reindex Complete")
    print("====================")
    print(f"Elements: {element_count}")
    print(f"CozoDB: ~/.claude/cache/pss-skill-index.db ({db_size})")
    print(f"Pass 1: {pass1_stats}")
    print(f"Backup: {backup_dir}")


if __name__ == "__main__":
    main()
