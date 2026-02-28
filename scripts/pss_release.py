#!/usr/bin/env python3
"""
PSS Release Pipeline - Unified release automation for Perfect Skill Suggester.

Handles: test -> lint -> bump -> changelog -> build -> commit -> tag -> push.

Usage:
    pss_release.py                    # Interactive: prompts for bump type
    pss_release.py --bump patch       # 2.2.1 -> 2.2.2
    pss_release.py --bump minor       # 2.2.1 -> 2.3.0
    pss_release.py --bump major       # 2.2.1 -> 3.0.0
    pss_release.py --dry-run          # Show what would happen, no changes
    pss_release.py --skip-build       # Skip binary compilation
    pss_release.py --skip-tests       # Skip test step
    pss_release.py --version-only     # Only bump version, no build/commit/push
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

# -- Project root: scripts/ is one level below project root --
ROOT = Path(__file__).resolve().parent.parent

# -- File paths relative to project root --
CARGO_TOML = ROOT / "rust" / "skill-suggester" / "Cargo.toml"
MAIN_RS = ROOT / "rust" / "skill-suggester" / "src" / "main.rs"
PLUGIN_JSON = ROOT / ".claude-plugin" / "plugin.json"
PYPROJECT_TOML = ROOT / "pyproject.toml"
README_MD = ROOT / "README.md"
CHANGELOG_MD = ROOT / "CHANGELOG.md"
BUILD_SCRIPT = ROOT / "scripts" / "pss_build.py"
BIN_DIR = ROOT / "rust" / "skill-suggester" / "bin"

# -- ANSI color helpers (no external deps) --
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"


def info(msg: str) -> None:
    print(f"{CYAN}[INFO]{RESET} {msg}")


def success(msg: str) -> None:
    print(f"{GREEN}[OK]{RESET}   {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}[WARN]{RESET} {msg}")


def error(msg: str) -> None:
    print(f"{RED}[ERR]{RESET}  {msg}")


def fatal(msg: str) -> NoReturn:
    """Print error and exit with code 1."""
    error(msg)
    sys.exit(1)


def run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command and return the result (check=False)."""
    return subprocess.run(
        cmd, cwd=cwd or ROOT, capture_output=True, text=True, check=False
    )


# ---------------------------------------------------------------------------
# Step 1: Pre-flight checks
# ---------------------------------------------------------------------------
def preflight_checks(skip_build: bool, dry_run: bool = False) -> None:
    """Verify git working tree is clean and required tools are available."""
    info("Pre-flight checks...")

    # Git working tree must be clean (skip for dry-run — no files are modified)
    result = run(["git", "status", "--porcelain"])
    if result.returncode != 0:
        fatal(f"git status failed: {result.stderr.strip()}")
    if result.stdout.strip() and not dry_run:
        fatal("Git working tree is dirty. Commit or stash changes before releasing.")

    # Check uv is available
    if shutil.which("uv") is None:
        fatal("'uv' is not installed or not on PATH.")

    # Check rustup is available (needed for builds)
    if not skip_build and shutil.which("rustup") is None:
        warn("'rustup' is not installed. Builds will likely fail.")

    success("Pre-flight checks passed.")


# ---------------------------------------------------------------------------
# Step 2: Run tests
# ---------------------------------------------------------------------------
def run_tests() -> None:
    """Run pytest and abort on failure."""
    info("Running tests...")
    result = run(["uv", "run", "pytest", "tests/", "-q"])
    if result.returncode != 0:
        error(result.stdout.strip() if result.stdout else "")
        error(result.stderr.strip() if result.stderr else "")
        fatal("Tests failed, aborting release.")
    success("Tests passed.")


# ---------------------------------------------------------------------------
# Step 3: Run linter
# ---------------------------------------------------------------------------
def run_linter() -> None:
    """Run ruff check on scripts/ and abort on failure."""
    info("Running linter...")
    result = run(["uv", "run", "ruff", "check", "scripts/"])
    if result.returncode != 0:
        error(result.stdout.strip() if result.stdout else "")
        error(result.stderr.strip() if result.stderr else "")
        fatal("Lint failed, aborting release.")
    success("Lint passed.")


# ---------------------------------------------------------------------------
# Step 4: Read current version
# ---------------------------------------------------------------------------
def read_current_version() -> str:
    """Parse current version from Cargo.toml (single source of truth)."""
    content = CARGO_TOML.read_text(encoding="utf-8")
    # Match the version line in the [package] section (first occurrence)
    match = re.search(r'^version\s*=\s*"(\d+\.\d+\.\d+)"', content, re.MULTILINE)
    if not match:
        fatal(f"Could not parse version from {CARGO_TOML}")
    version = match.group(1)
    info(f"Current version: {BOLD}{version}{RESET}")
    return version


# ---------------------------------------------------------------------------
# Step 5: Compute new version
# ---------------------------------------------------------------------------
def compute_new_version(current: str, bump_type: str | None) -> str:
    """Compute the next version based on bump type."""
    if bump_type is None:
        # Interactive prompt
        bump_type = (
            input(f"{CYAN}Bump type (patch/minor/major): {RESET}").strip().lower()
        )
        if bump_type not in ("patch", "minor", "major"):
            fatal(f"Invalid bump type: '{bump_type}'. Must be patch, minor, or major.")

    parts = list(map(int, current.split(".")))
    if len(parts) != 3:
        fatal(f"Version '{current}' is not in X.Y.Z format.")

    major, minor, patch = parts

    if bump_type == "patch":
        patch += 1
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        fatal(f"Invalid bump type: '{bump_type}'.")

    new_version = f"{major}.{minor}.{patch}"
    info(f"New version: {BOLD}{new_version}{RESET}")
    return new_version


# ---------------------------------------------------------------------------
# Step 6: Bump version in 4 files
# ---------------------------------------------------------------------------
def bump_file(
    filepath: Path,
    pattern: str,
    replacement: str,
    dry_run: bool,
    label: str,
) -> None:
    """Replace exactly one occurrence of pattern in file. Abort if no match."""
    content = filepath.read_text(encoding="utf-8")
    new_content, count = re.subn(pattern, replacement, content, count=1)

    if count == 0:
        fatal(f"No match for version pattern in {filepath.relative_to(ROOT)} ({label})")
    if count > 1:
        fatal(
            f"Multiple matches for version pattern in {filepath.relative_to(ROOT)} ({label})"
        )

    if dry_run:
        info(f"  [DRY-RUN] Would update {filepath.relative_to(ROOT)} ({label})")
    else:
        filepath.write_text(new_content, encoding="utf-8")
        success(f"  Updated {filepath.relative_to(ROOT)} ({label})")


def bump_versions(old: str, new: str, dry_run: bool) -> None:
    """Bump version string in all 4 source files."""
    info("Bumping versions...")

    # Escape dots for regex
    old_re = re.escape(old)

    # 1. Cargo.toml — version = "X.Y.Z" (first occurrence, in [package] section)
    bump_file(
        CARGO_TOML,
        rf'(version\s*=\s*"){old_re}(")',
        rf"\g<1>{new}\2",
        dry_run,
        label="Cargo.toml [package].version",
    )

    # 2. main.rs — #[command(version = "X.Y.Z")]
    bump_file(
        MAIN_RS,
        rf'(#\[command\(version\s*=\s*"){old_re}("\)\])',
        rf"\g<1>{new}\2",
        dry_run,
        label='main.rs #[command(version = "...")]',
    )

    # 3. plugin.json — "version": "X.Y.Z"
    bump_file(
        PLUGIN_JSON,
        rf'("version"\s*:\s*"){old_re}(")',
        rf"\g<1>{new}\2",
        dry_run,
        label="plugin.json version",
    )

    # 4. pyproject.toml — version = "X.Y.Z" (first occurrence)
    bump_file(
        PYPROJECT_TOML,
        rf'(version\s*=\s*"){old_re}(")',
        rf"\g<1>{new}\2",
        dry_run,
        label="pyproject.toml version",
    )


# ---------------------------------------------------------------------------
# Step 7: Update version badge in README.md
# ---------------------------------------------------------------------------
def update_readme_badge(old: str, new: str, dry_run: bool) -> None:
    """Replace version badge in README.md."""
    info("Updating README badge...")
    old_badge = f"version-{old}-blue"
    new_badge = f"version-{new}-blue"

    content = README_MD.read_text(encoding="utf-8")
    if old_badge not in content:
        warn(f"Version badge '{old_badge}' not found in README.md, skipping.")
        return

    new_content = content.replace(old_badge, new_badge, 1)

    if dry_run:
        info(f"  [DRY-RUN] Would replace '{old_badge}' with '{new_badge}' in README.md")
    else:
        README_MD.write_text(new_content, encoding="utf-8")
        success(f"  Updated README.md badge: {old_badge} -> {new_badge}")


# ---------------------------------------------------------------------------
# Step 8: Generate changelog
# ---------------------------------------------------------------------------
def generate_changelog(new: str, dry_run: bool) -> None:
    """Run git-cliff to generate CHANGELOG.md, if available."""
    info("Generating changelog...")

    if shutil.which("git-cliff") is None:
        warn("git-cliff not installed, skipping changelog generation.")
        return

    if dry_run:
        info(f"  [DRY-RUN] Would run: git-cliff --tag v{new} -o CHANGELOG.md")
        return

    result = run(["git-cliff", "--tag", f"v{new}", "-o", str(CHANGELOG_MD)])
    if result.returncode != 0:
        warn(f"git-cliff failed: {result.stderr.strip()}")
    else:
        success("  CHANGELOG.md generated.")


# ---------------------------------------------------------------------------
# Step 9: Build binaries
# ---------------------------------------------------------------------------
def build_binaries(dry_run: bool) -> None:
    """Run pss_build.py --all. Warn on failure but do not abort."""
    info("Building binaries...")

    if dry_run:
        info("  [DRY-RUN] Would run: pss_build.py --all")
        return

    result = run(["uv", "run", "python", str(BUILD_SCRIPT), "--all"])
    if result.returncode != 0:
        warn(f"Build failed (non-blocking): {result.stderr.strip()}")
    else:
        success("  Binaries built successfully.")


# ---------------------------------------------------------------------------
# Step 10: Commit
# ---------------------------------------------------------------------------
def git_commit(old: str, new: str) -> None:
    """Stage versioned files and commit."""
    info("Committing changes...")

    files_to_add = [
        str(CARGO_TOML),
        str(MAIN_RS),
        str(PLUGIN_JSON),
        str(PYPROJECT_TOML),
        str(README_MD),
    ]

    # Add CHANGELOG.md if it exists
    if CHANGELOG_MD.exists():
        files_to_add.append(str(CHANGELOG_MD))

    # Add built binaries directory if it exists
    if BIN_DIR.exists():
        files_to_add.append(str(BIN_DIR))

    result = run(["git", "add"] + files_to_add)
    if result.returncode != 0:
        fatal(f"git add failed: {result.stderr.strip()}")

    # Use the arrow character in the commit message
    commit_msg = f"bump: version {old} \u2192 {new}"
    result = run(["git", "commit", "-m", commit_msg])
    if result.returncode != 0:
        fatal(f"git commit failed: {result.stderr.strip()}")

    success(f"  Committed: {commit_msg}")


# ---------------------------------------------------------------------------
# Step 11: Tag
# ---------------------------------------------------------------------------
def git_tag(new: str) -> None:
    """Create a git tag for the new version."""
    info(f"Tagging v{new}...")
    tag = f"v{new}"
    result = run(["git", "tag", tag])
    if result.returncode != 0:
        fatal(f"git tag failed: {result.stderr.strip()}")
    success(f"  Tagged: {tag}")


# ---------------------------------------------------------------------------
# Step 12: Push
# ---------------------------------------------------------------------------
def git_push() -> None:
    """Push commits and tags to remote."""
    info("Pushing to remote...")

    result = run(["git", "push"])
    if result.returncode != 0:
        fatal(f"git push failed: {result.stderr.strip()}")

    result = run(["git", "push", "--tags"])
    if result.returncode != 0:
        fatal(f"git push --tags failed: {result.stderr.strip()}")

    success("  Pushed commits and tags.")
    info(
        "Marketplace notification will trigger automatically via notify-marketplace.yml"
    )


# ---------------------------------------------------------------------------
# Step 13: Summary
# ---------------------------------------------------------------------------
def print_summary(old: str, new: str, args: argparse.Namespace) -> None:
    """Print a summary table of what was done."""
    print()
    print(f"{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  Release Summary{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")
    print(f"  Version:       {old} -> {new}")
    print(f"  Dry run:       {'yes' if args.dry_run else 'no'}")
    print(f"  Tests:         {'skipped' if args.skip_tests else 'passed'}")
    print("  Lint:          passed")
    print("  Files bumped:  4 (Cargo.toml, main.rs, plugin.json, pyproject.toml)")
    print("  README badge:  updated")
    changelog_status = (
        "generated"
        if shutil.which("git-cliff")
        else "skipped (git-cliff not installed)"
    )
    print(f"  Changelog:     {changelog_status}")
    if args.skip_build:
        print("  Build:         skipped")
    elif args.dry_run:
        print("  Build:         dry-run")
    else:
        print("  Build:         attempted")
    if args.version_only or args.dry_run:
        print("  Git commit:    skipped")
        print("  Git tag:       skipped")
        print("  Git push:      skipped")
    else:
        print(f"  Git commit:    bump: version {old} \u2192 {new}")
        print(f"  Git tag:       v{new}")
        print("  Git push:      done")
    print(f"{BOLD}{'=' * 60}{RESET}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="PSS Release Pipeline: test -> lint -> bump -> changelog -> build -> commit -> tag -> push",
    )
    parser.add_argument(
        "--bump",
        choices=["patch", "minor", "major"],
        default=None,
        help="Version bump type. If omitted, prompts interactively.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making any changes.",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip binary compilation step.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip test step.",
    )
    parser.add_argument(
        "--version-only",
        action="store_true",
        help="Only bump version in files, no build/commit/push.",
    )

    args = parser.parse_args()

    print()
    print(f"{BOLD}{CYAN}PSS Release Pipeline{RESET}")
    print(f"{CYAN}{'=' * 40}{RESET}")
    print()

    # Step 1: Pre-flight checks
    preflight_checks(
        skip_build=args.skip_build or args.version_only,
        dry_run=args.dry_run,
    )

    # Step 2: Run tests (unless --skip-tests)
    if not args.skip_tests:
        run_tests()
    else:
        warn("Tests skipped (--skip-tests).")

    # Step 3: Run linter
    run_linter()

    # Step 4: Read current version
    old_version = read_current_version()

    # Step 5: Compute new version
    new_version = compute_new_version(old_version, args.bump)

    # Step 6: Bump version in 4 files
    bump_versions(old_version, new_version, args.dry_run)

    # Step 7: Update README badge
    update_readme_badge(old_version, new_version, args.dry_run)

    # Step 8: Generate changelog
    generate_changelog(new_version, args.dry_run)

    # Step 9: Build binaries (unless --skip-build or --version-only)
    if not args.skip_build and not args.version_only:
        build_binaries(args.dry_run)
    elif args.skip_build:
        warn("Build skipped (--skip-build).")
    elif args.version_only:
        warn("Build skipped (--version-only).")

    # Step 10-12: Commit, tag, push (unless --version-only or --dry-run)
    if not args.version_only and not args.dry_run:
        git_commit(old_version, new_version)
        git_tag(new_version)
        git_push()
    elif args.dry_run:
        info("[DRY-RUN] Would commit, tag v{}, and push.".format(new_version))
    elif args.version_only:
        warn("Commit/tag/push skipped (--version-only).")

    # Step 13: Summary
    print_summary(old_version, new_version, args)

    success(f"Release v{new_version} complete!")


if __name__ == "__main__":
    main()
