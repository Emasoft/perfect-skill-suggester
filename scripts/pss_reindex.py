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
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from pss_paths import detect_platform, get_data_dir


def resolve_plugin_root() -> Path:
    """Resolve the plugin root directory from env var or plugin cache."""
    env_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if env_root:
        return Path(env_root)
    # Fallback: find the plugin under ANY installed marketplace cache dir.
    # A single hardcoded marketplace name (formerly "emasoft-plugins") broke
    # for anyone installing PSS from a fork, a private marketplace, or a
    # renamed channel — glob across all of them instead.
    cache_root = Path.home() / ".claude" / "plugins" / "cache"
    candidates = sorted(cache_root.glob("*/perfect-skill-suggester"))
    if not candidates:
        sys.exit(f"ERROR: Plugin cache not found under {cache_root}/*/perfect-skill-suggester")
    if len(candidates) > 1:
        sys.exit(
            "ERROR: perfect-skill-suggester found in multiple marketplace caches ("
            + ", ".join(c.parent.name for c in candidates)
            + "). Set CLAUDE_PLUGIN_ROOT to disambiguate."
        )
    cache_base = candidates[0]

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
    """Resolve the PSS binary for the current platform.

    Delegates the platform→filename mapping to pss_paths.detect_platform() —
    the single source of truth already shared by pss_hook.py, pss_mcp_server.py,
    and bin/pss-hook-dispatch.sh — instead of re-implementing a second,
    narrower Darwin/Linux-only table here (which also lacked Windows and
    Android/Termux support that detect_platform() already handles).
    """
    try:
        name = detect_platform()
    except RuntimeError as e:
        sys.exit(f"ERROR: {e}")
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
    """Run the 4-stage pipeline: discover → enrich → merge → merge-events.

    Stages 1-3 build the legacy `skills` table (CozoDB) consumed by the
    suggestion hot path. Stage 4 (the temporal-index `merge-events`) reads
    the same discover output to populate the event-sourced `events` and
    `elements_state` tables introduced in TRDD-152e697f. The Rust
    binary's `merge-events` subcommand is the only writer of the events
    table during normal reindex flow.

    Implementation: discover output is captured once into a tmpfile, then
    fanned out to (enrich → merge_queue) AND (merge-events). This avoids
    re-running the slow discover stage at the cost of one tmpfile on disk
    that is removed in the finally block. The tmpfile lives in
    $TMPDIR/pss-reindex-<pid>.jsonl.

    Args:
        exclude_inactive_plugins: If True, pass --exclude-inactive-plugins to discover
                                  to skip plugins disabled in settings.json.
    Returns the pipeline exit code (the first non-zero stage code, or 0).
    """
    warnings_file = Path(tempfile.gettempdir()) / "pss-discover-warnings.txt"
    stats_file = Path(tempfile.gettempdir()) / "pss-pass1-stats.txt"
    discover_jsonl = Path(tempfile.gettempdir()) / f"pss-reindex-{os.getpid()}.jsonl"

    discover_args = [
        sys.executable,
        str(scripts_dir / "pss_discover.py"),
        "--jsonl",
        "--all-projects",
    ]
    if exclude_inactive_plugins:
        discover_args.append("--exclude-inactive-plugins")
    enrich_args = [str(binary), "--pass1-batch"]
    merge_args = [
        sys.executable,
        str(scripts_dir / "pss_merge_queue.py"),
        "--batch-stdin",
        "--index",
        str(staging_index),
    ]
    # merge-events targets the same DB the merge stage writes (default
    # CozoDB path). The binary resolves it via $CLAUDE_PLUGIN_DATA /
    # ~/.claude/cache/ unless --index overrides.
    merge_events_args = [str(binary), "merge-events"]

    # Stage 0: discover → tmpfile. We could use Popen to stream into the
    # next stages, but capturing once and replaying twice is simpler than
    # tee'ing across two downstream pipes and lets each downstream stage
    # set its own timeout.
    try:
        with open(warnings_file, "wb") as wf:
            with open(discover_jsonl, "wb") as out:
                rc_d = subprocess.run(
                    discover_args, stdout=out, stderr=wf, timeout=300
                ).returncode
        if rc_d != 0:
            print(
                f"ERROR: Pipeline stage 'discover' exited with code {rc_d}",
                file=sys.stderr,
            )
            return rc_d
    except subprocess.TimeoutExpired:
        print("ERROR: discover stage timed out after 5 minutes", file=sys.stderr)
        return 1

    # Stage 1-2-3: cat tmpfile | enrich | merge_queue
    p2: subprocess.Popen[bytes] | None = None
    p3: subprocess.Popen[bytes] | None = None
    try:
        with open(discover_jsonl, "rb") as inp, open(stats_file, "wb") as sf:
            p2 = subprocess.Popen(
                enrich_args, stdin=inp, stdout=subprocess.PIPE, stderr=sf
            )
            assert p2.stdout is not None
            p3 = subprocess.Popen(merge_args, stdin=p2.stdout)
            p2.stdout.close()
            try:
                p3.wait(timeout=300)
            except subprocess.TimeoutExpired:
                for proc in (p3, p2):
                    proc.kill()
                print("ERROR: Pipeline timed out after 5 minutes", file=sys.stderr)
                return 1
            rc2 = p2.wait()
            rc3 = p3.returncode
            for stage, rc in (("enrich", rc2), ("merge", rc3)):
                if rc != 0:
                    print(
                        f"ERROR: Pipeline stage '{stage}' exited with code {rc}",
                        file=sys.stderr,
                    )
                    return rc
    finally:
        running: tuple[subprocess.Popen[bytes] | None, ...] = (p2, p3)
        for p in running:
            if p is not None and p.poll() is None:
                p.kill()

    # Stage 4: cat tmpfile | merge-events. Populates the event-sourced
    # temporal index (events + elements_state, TRDD-152e697f). merge-events is
    # the ONLY writer of the events table during reindex, so a swallowed
    # failure here silently stops temporal tracking from advancing while
    # `pss-reindex-skills` still reports SUCCESS. That violates the project
    # fail-fast rule, so a failure/timeout now propagates a NON-ZERO result —
    # EXACTLY like stages 1-3 (which `return rc`) — instead of a stderr
    # WARNING. The skills table (stages 1-3) is already committed at this
    # point, so the messages make the partial state explicit; main() then
    # exits non-zero so the caller learns the reindex did not fully complete.
    try:
        with open(discover_jsonl, "rb") as inp:
            rc_e = subprocess.run(
                merge_events_args, stdin=inp, timeout=300
            ).returncode
        if rc_e != 0:
            print(
                f"ERROR: Pipeline stage 'merge-events' exited with code {rc_e} "
                "(skills table updated; temporal events/elements_state NOT updated)",
                file=sys.stderr,
            )
            return rc_e
    except subprocess.TimeoutExpired:
        print(
            "ERROR: Pipeline stage 'merge-events' timed out after 5 minutes "
            "(skills table updated; temporal events/elements_state NOT updated)",
            file=sys.stderr,
        )
        return 1
    finally:
        try:
            discover_jsonl.unlink(missing_ok=True)
        except OSError:
            pass

    # DI-8 (audit 20260514): rules used to never appear in the DB because
    # `pss index-rules` was a separate on-demand command. Now invoke it
    # automatically after merge-events so consumers (pss-agent-profiler,
    # /pss-get-description) see populated rules without a manual step.
    # Failures here are logged but DO NOT fail the overall reindex — the
    # skills/events tables (which drive the suggestion hot path) are
    # already up to date.
    try:
        rc_r = subprocess.run(
            [str(binary), "index-rules"],
            timeout=60,
        ).returncode
        if rc_r != 0:
            print(
                f"WARNING: index-rules exited with code {rc_r} "
                "(skills/events index OK; rules table may be stale)",
                file=sys.stderr,
            )
    except subprocess.TimeoutExpired:
        print(
            "WARNING: index-rules timed out after 60 s (skills/events OK)",
            file=sys.stderr,
        )
    except (OSError, subprocess.SubprocessError) as e:
        print(
            f"WARNING: index-rules failed to spawn: {e} (skills/events OK)",
            file=sys.stderr,
        )

    return 0


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
        from pss_cozodb import (  # type: ignore[import-not-found]
            count_skills,
            get_db_path,
        )
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
        # run_pipeline already printed the stage-specific ERROR. A stage 1-3
        # failure leaves the previous skills DB intact (the atomic swap never
        # ran); a stage-4 (merge-events) failure means the skills DB WAS
        # swapped but the temporal index did not update. Don't assert a blanket
        # "old index preserved" here — it is only true for stages 1-3.
        print(
            f"ERROR: Reindex pipeline failed with exit code {pipeline_rc}. "
            "See the stage error above.",
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
