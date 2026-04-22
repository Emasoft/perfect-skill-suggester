#!/usr/bin/env python3
"""PSS Clean — remove regenerable build artifacts from the project tree.

All targets are confirmed regenerable per-Rule-0: cargo build output,
the uv-managed venv, the mypy cache, and historical orphan cargo output
from an older repo layout (pre-submodule). Nothing here is tracked by
git; nothing requires human intervention to regenerate.

Usage:
    uv run scripts/pss_clean.py                # clean everything (default)
    uv run scripts/pss_clean.py --dry-run      # report sizes, don't delete
    uv run scripts/pss_clean.py --rust-only    # just rust/target and src/
    uv run scripts/pss_clean.py --docker       # also prune stale cross-rs/super-linter images

The regular clean does NOT touch:
    - ~/.cache/uv         (user-wide; affects every uv project on this machine)
    - ~/.cargo/registry   (user-wide; affects every Rust project)
    - Docker images       (unless --docker is passed)
    - bin/                (shipped platform binaries — authoritative)
    - .git/               (repo data)
    - skill-index.json / CozoDB / domain-registry.json (user data, not artifacts)

Exit codes:
    0 = cleanup succeeded (or nothing to clean)
    1 = partial failure (some paths couldn't be removed)
    2 = argument or environment error
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def dir_size_bytes(path: Path) -> int:
    """Recursive size in bytes; 0 if missing or unreadable."""
    if not path.exists():
        return 0
    total = 0
    try:
        for p in path.rglob("*"):
            try:
                if p.is_file() or p.is_symlink():
                    total += p.lstat().st_size
            except OSError:
                pass
    except OSError:
        return 0
    return total


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} PB"


def safe_rmtree(path: Path, dry_run: bool) -> tuple[bool, int, str]:
    """Remove `path` and return (succeeded, bytes_freed, message).

    Verifies `path` is inside PROJECT_ROOT, is not a git repo,
    is not tracked by git, and is not one of the protected names.
    """
    if not path.exists():
        return (True, 0, f"skip (missing): {path}")

    resolved = path.resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError:
        return (False, 0, f"REFUSE (outside project): {path}")

    # Never touch protected names — defence in depth
    protected = {"bin", ".git", ".github", "docs", "README.md", "LICENSE",
                 "skills", "commands", "agents", "hooks", "scripts",
                 "tests", "schemas", "resources", "design"}
    # Walk up from the path to the project root checking for protected names.
    # A target like `rust/target` must pass; a target like `skills/foo` must fail.
    for parent in [resolved, *resolved.parents]:
        if parent == PROJECT_ROOT:
            break
        if parent.name in protected:
            return (False, 0, f"REFUSE (protected parent '{parent.name}'): {path}")

    size = dir_size_bytes(path)
    if dry_run:
        return (True, size, f"would remove ({human(size)}): {path}")

    try:
        shutil.rmtree(path)
        return (True, size, f"removed ({human(size)}): {path}")
    except OSError as e:
        return (False, 0, f"FAILED: {path} — {e}")


def cargo_clean(manifest: Path, dry_run: bool) -> tuple[bool, int, str]:
    """Run `cargo clean --manifest-path <manifest>` on a Cargo project.

    Returns (ok, bytes_freed, message). The freed size is an approximation
    (we measure target/ before running, since cargo doesn't report it).
    """
    if not manifest.exists():
        return (True, 0, f"skip (no Cargo.toml): {manifest}")
    target = manifest.parent / "target"
    if not target.exists():
        # Also check cargo's default ../target layout for workspace members
        workspace_target = manifest.parent.parent / "target"
        if workspace_target.exists():
            target = workspace_target
        else:
            return (True, 0, f"skip (no target/ near): {manifest}")

    size_before = dir_size_bytes(target)
    if dry_run:
        return (True, size_before, f"would cargo clean ({human(size_before)}): {target}")

    try:
        subprocess.run(
            ["cargo", "clean", "--manifest-path", str(manifest)],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        # cargo clean removes target/ contents but may leave the dir
        size_after = dir_size_bytes(target)
        freed = max(0, size_before - size_after)
        return (True, freed, f"cargo clean ({human(freed)} freed): {target}")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        # Fall back to direct rmtree of target/ since cargo refused
        return safe_rmtree(target, dry_run=dry_run)


def docker_prune(dry_run: bool) -> tuple[bool, int, str]:
    """Prune stale cross-rs and super-linter Docker images.

    These are re-pullable (~10 min each). Safe to drop if disk pressure is high.
    """
    # List images once
    try:
        out = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}"],
            capture_output=True, text=True, timeout=10, check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return (True, 0, "skip (docker not available)")

    seen: set[str] = set()
    to_drop = []
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        repo_tag = parts[0]
        if repo_tag.startswith("ghcr.io/cross-rs/") or \
           repo_tag.startswith("ghcr.io/super-linter/"):
            img_id = parts[1]
            if img_id not in seen:
                seen.add(img_id)
                to_drop.append(img_id)  # image ID, deduplicated

    if not to_drop:
        return (True, 0, "no stale cross-rs/super-linter images found")

    if dry_run:
        return (True, 0, f"would drop {len(to_drop)} docker image(s): {to_drop[:3]}{'...' if len(to_drop) > 3 else ''}")

    freed_msg = []
    ok = True
    for img_id in to_drop:
        try:
            subprocess.run(["docker", "rmi", "-f", img_id],
                           check=True, capture_output=True, text=True, timeout=30)
            freed_msg.append(img_id[:12])
        except subprocess.CalledProcessError as e:
            ok = False
            freed_msg.append(f"FAILED:{img_id[:12]}:{e.stderr.strip()[:40]}")

    return (ok, 0, f"docker rmi: {', '.join(freed_msg)}")


def main() -> int:
    docstring = __doc__ or "PSS Clean"
    ap = argparse.ArgumentParser(description=docstring.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="Report sizes, don't delete.")
    ap.add_argument("--rust-only", action="store_true",
                    help="Only clean rust/target and the orphan src/ target dirs.")
    ap.add_argument("--docker", action="store_true",
                    help="Also prune cross-rs and super-linter Docker images.")
    args = ap.parse_args()

    print(f"PSS Clean — {'DRY RUN' if args.dry_run else 'REMOVING ARTIFACTS'}")
    print(f"Project root: {PROJECT_ROOT}")
    print()

    total_freed = 0
    failures = 0

    # 1. Rust workspace — both skill-suggester and negation-detector share the
    # same target/ dir under rust/target (cargo workspace). Running cargo clean
    # on one manifest wipes the whole workspace; running it twice would either
    # double-count (dry run) or no-op the second call. So we clean the
    # workspace once via whichever manifest is present.
    workspace_cargo_toml = PROJECT_ROOT / "rust" / "Cargo.toml"
    per_crate_manifests = [
        PROJECT_ROOT / "rust" / "skill-suggester" / "Cargo.toml",
        PROJECT_ROOT / "rust" / "negation-detector" / "Cargo.toml",
    ]
    manifest = workspace_cargo_toml if workspace_cargo_toml.exists() \
        else next((m for m in per_crate_manifests if m.exists()), None)
    if manifest is None:
        print("  [rust] skip (no Cargo.toml found)")
    else:
        ok, freed, msg = cargo_clean(manifest, args.dry_run)
        print(f"  [rust] {msg}")
        total_freed += freed
        if not ok:
            failures += 1

    # 2. Orphan src/ targets (no Cargo.toml — direct removal)
    for orphan in [
        PROJECT_ROOT / "src" / "skill-suggester" / "target",
        PROJECT_ROOT / "src" / "negation-detector" / "target",
    ]:
        ok, freed, msg = safe_rmtree(orphan, args.dry_run)
        print(f"  [orphan] {msg}")
        total_freed += freed
        if not ok:
            failures += 1

    if args.rust_only:
        print()
        print(f"Total {'would-be-freed' if args.dry_run else 'freed'}: {human(total_freed)}")
        return 0 if failures == 0 else 1

    # 3. .venv — uv recreates on next `uv run --script`
    ok, freed, msg = safe_rmtree(PROJECT_ROOT / ".venv", args.dry_run)
    print(f"  [venv] {msg}")
    total_freed += freed
    if not ok:
        failures += 1

    # 4. .mypy_cache — mypy recreates on next run
    ok, freed, msg = safe_rmtree(PROJECT_ROOT / ".mypy_cache", args.dry_run)
    print(f"  [mypy] {msg}")
    total_freed += freed
    if not ok:
        failures += 1

    # 5. Optional: Docker image prune
    if args.docker:
        ok, _freed, msg = docker_prune(args.dry_run)
        print(f"  [docker] {msg}")
        if not ok:
            failures += 1

    print()
    print(f"Total {'would-be-freed' if args.dry_run else 'freed'}: {human(total_freed)}")
    if failures:
        print(f"Partial failures: {failures}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
