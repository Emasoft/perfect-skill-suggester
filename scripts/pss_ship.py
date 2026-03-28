#!/usr/bin/env python3
"""
PSS Ship — Unified release pipeline and pre-push gate for Perfect Skill Suggester.

Two modes:
  --gate           Pre-push hook mode: lint + validate + test. Blocks on CRITICAL/MAJOR/MINOR.
  (default)        Full release: lint + validate + test + bump + changelog + build + commit + tag + push.

Gate mode (used by .git/hooks/pre-push):
    pss_ship.py --gate

Release mode:
    pss_ship.py --bump patch           # non-interactive
    pss_ship.py                        # interactive: prompts for bump type
    pss_ship.py --dry-run              # preview only
    pss_ship.py --sync-cpv             # also sync CPV scripts from GitHub

Utilities:
    pss_ship.py --install-hook         # install pre-push hook into .git/hooks/
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
VERSION_FILE = ROOT / "VERSION"
CARGO_TOML = ROOT / "rust" / "skill-suggester" / "Cargo.toml"
MAIN_RS = ROOT / "rust" / "skill-suggester" / "src" / "main.rs"
PLUGIN_JSON = ROOT / ".claude-plugin" / "plugin.json"
PYPROJECT_TOML = ROOT / "pyproject.toml"
UV_LOCK = ROOT / "uv.lock"
RUST_SRC_DIR = ROOT / "rust" / "skill-suggester" / "src"
README_MD = ROOT / "README.md"
CHANGELOG_MD = ROOT / "CHANGELOG.md"
BUILD_SCRIPT = ROOT / "scripts" / "pss_build.py"
BIN_DIR = ROOT / "bin"
VALIDATE_SCRIPT = ROOT / "scripts" / "validate_plugin.py"
HOOK_SOURCE = ROOT / "git-hooks" / "pre-push"
HOOK_TARGET = ROOT / ".git" / "hooks" / "pre-push"

# -- CPV sync: upstream GitHub repo and script filenames --
CPV_REPO = "Emasoft/claude-plugins-validation"
CPV_SCRIPTS = [
    "cpv_validation_common.py",
    "validate_agent.py",
    "validate_command.py",
    "validate_documentation.py",
    "validate_encoding.py",
    "validate_enterprise.py",
    "validate_hook.py",
    "validate_lsp.py",
    "validate_marketplace.py",
    "validate_marketplace_pipeline.py",
    "validate_mcp.py",
    "validate_plugin.py",
    "validate_rules.py",
    "validate_scoring.py",
    "validate_security.py",
    "validate_skill.py",
    "validate_skill_comprehensive.py",
    "validate_xref.py",
]

# -- ANSI color helpers --
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BLUE = "\033[34m"
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


def run(
    cmd: list[str], cwd: Path | None = None, timeout: int = 300
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command and return the result (check=False)."""
    return subprocess.run(
        cmd,
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


# ===========================================================================
# Shared steps (used by both gate and release modes)
# ===========================================================================


def run_linter() -> bool:
    """Run ruff check on scripts/ and tests/. Returns True if passed."""
    info("Running linter (ruff check)...")
    result = run(["uv", "run", "ruff", "check", "scripts/", "tests/"])
    if result.returncode != 0:
        error(result.stdout.strip() if result.stdout else "")
        error(result.stderr.strip() if result.stderr else "")
        error("Lint failed.")
        return False
    success("Lint passed.")
    return True


def run_validation() -> int:
    """Run validate_plugin.py and return its exit code."""
    info("Running plugin validation...")
    if not VALIDATE_SCRIPT.exists():
        error(f"Validation script not found: {VALIDATE_SCRIPT}")
        return 1

    # Use --with pyyaml since validate_plugin.py needs it
    if shutil.which("uv"):
        result = run(
            ["uv", "run", "--with", "pyyaml", "python", str(VALIDATE_SCRIPT), "."],
            timeout=120,
        )
    else:
        result = run([sys.executable, str(VALIDATE_SCRIPT), "."], timeout=120)

    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)

    return result.returncode


def run_tests() -> bool:
    """Run pytest and return True if passed."""
    info("Running tests...")
    result = run(["uv", "run", "pytest", "tests/", "-q"], timeout=120)
    if result.returncode != 0:
        error(result.stdout.strip() if result.stdout else "")
        error(result.stderr.strip() if result.stderr else "")
        error("Tests failed.")
        return False
    success("Tests passed.")
    return True


# ===========================================================================
# Gate mode (pre-push hook)
# ===========================================================================


def detect_plugin_changes() -> bool:
    """Check if plugin files changed in the commits being pushed.

    Reads push info from stdin (git pre-push protocol).
    Returns True if plugin-relevant files changed.
    """
    # When called via git pre-push hook, stdin has ref info.
    # When called directly (testing), assume changes exist.
    if sys.stdin.isatty():
        # Called directly from terminal, not from git hook — assume changes
        info("Not running inside git hook, assuming plugin files changed.")
        return True

    # Read push info from stdin (git pre-push protocol sends ref lines)
    got_any_line = False
    for line in sys.stdin:
        got_any_line = True
        parts = line.strip().split()
        if len(parts) < 4:
            continue

        local_sha = parts[1]
        remote_sha = parts[3]

        # Branch deletion — no validation needed
        if local_sha == "0" * 40:
            info("Branch deletion detected. No validation needed.")
            return False

        # Get changed files
        if remote_sha == "0" * 40:
            # New branch — check recent commits on this branch
            result = run(
                ["git", "diff", "--name-only", "HEAD~10", local_sha],
            )
            if result.returncode != 0:
                # Fallback: list all files in the branch (conservative)
                result = run(
                    ["git", "ls-tree", "-r", "--name-only", local_sha],
                )
        else:
            result = run(
                ["git", "diff", "--name-only", f"{remote_sha}..{local_sha}"],
            )

        if result.returncode != 0:
            warn("Could not determine changed files, running validation anyway.")
            return True

        # Check if any plugin-relevant files changed
        plugin_patterns = (
            ".claude-plugin/",
            "agents/",
            "commands/",
            "skills/",
            "hooks/",
            "scripts/",
            ".mcp.json",
        )
        for changed_file in result.stdout.strip().splitlines():
            if any(
                changed_file.startswith(p) or changed_file.endswith(p)
                for p in plugin_patterns
            ):
                return True

    # Defensive fallback: if stdin was piped but produced no valid lines,
    # assume changes exist (safe default — run validation rather than skip it)
    if not got_any_line and not sys.stdin.isatty():
        warn("No ref info received on stdin, running validation anyway.")
        return True

    info("No plugin files changed. Skipping validation.")
    return False


def _ensure_submodule_pushed() -> None:
    """Push the rust/ submodule if the parent references an unpushed commit.

    Called by the pre-push gate so that manual 'git push' from the root
    also pushes the submodule — preventing 'not our ref' clone failures.
    """
    rust_submodule = ROOT / "rust"
    if not (rust_submodule / ".git").exists():
        return
    # Get the submodule commit the parent index references
    ref_result = run(["git", "ls-tree", "HEAD", "rust"])
    if ref_result.returncode != 0 or not ref_result.stdout.strip():
        return
    # Format: "160000 commit <sha>\trust"
    parts = ref_result.stdout.strip().split()
    if len(parts) < 3:
        return
    parent_ref = parts[2]
    # Check if this commit exists on the submodule remote
    fetch_check = run(
        ["git", "-C", str(rust_submodule), "fetch", "--dry-run", "origin", parent_ref],
        timeout=30,
    )
    if fetch_check.returncode == 0:
        return  # Already on remote, nothing to do
    # Submodule commit not on remote — push it
    info(f"  Submodule ref {parent_ref[:12]} not on remote, pushing rust/...")
    push_result = run(["git", "-C", str(rust_submodule), "push"])
    if push_result.returncode != 0:
        # MUST block the parent push — otherwise 'not our ref' on clone
        fatal(
            f"Submodule push failed: {push_result.stderr.strip()}\n"
            "  Run 'git -C rust push' manually before retrying."
        )
    success(f"  Submodule rust/ pushed ({parent_ref[:12]}).")


def gate_pipeline() -> int:
    """Pre-push gate: lint + validate + test. Returns exit code."""
    print(f"\n{BLUE}{'=' * 50}{RESET}")
    print(f"{BLUE}  PSS Pre-Push Gate{RESET}")
    print(f"{BLUE}{'=' * 50}{RESET}\n")

    # Step 0: Ensure submodule is pushed (prevents 'not our ref' on clone)
    _ensure_submodule_pushed()

    # Step 1: Check if plugin files changed
    if not detect_plugin_changes():
        success("No plugin files changed. Push allowed.")
        return 0

    blocked = False

    # Step 2: Lint
    if not run_linter():
        blocked = True

    # Step 3: Plugin validation
    val_exit = run_validation()
    if val_exit == 0:
        success("Plugin validation passed.")
    elif val_exit == 4:
        # NIT only — treated as warning, does NOT block
        warn("Plugin validation: NIT issues found (non-blocking).")
    elif val_exit in (1, 2, 3):
        severity = {1: "CRITICAL", 2: "MAJOR", 3: "MINOR"}
        error(f"Plugin validation: {severity.get(val_exit, 'UNKNOWN')} issues found.")
        blocked = True
    else:
        error(f"Plugin validation failed with unexpected exit code {val_exit}.")
        blocked = True

    # Step 4: Tests
    if not run_tests():
        blocked = True

    # Final verdict
    print()
    if blocked:
        print(f"{RED}{'=' * 50}{RESET}")
        print(f"{RED}  BLOCKED: Fix issues before pushing.{RESET}")
        print(f"{RED}{'=' * 50}{RESET}")
        return 1
    else:
        print(f"{GREEN}{'=' * 50}{RESET}")
        print(f"{GREEN}  PASSED: Push allowed.{RESET}")
        print(f"{GREEN}{'=' * 50}{RESET}")
        return 0


# ===========================================================================
# Release mode
# ===========================================================================


def preflight_checks(skip_build: bool, dry_run: bool = False) -> None:
    """Verify git working tree is clean and required tools are available."""
    info("Pre-flight checks...")

    # Git working tree must be clean (skip for dry-run)
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


def read_current_version() -> str:
    """Read current version from VERSION file (single source of truth)."""
    if not VERSION_FILE.exists():
        fatal(f"VERSION file not found at {VERSION_FILE}")
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        fatal(f"Invalid version format in VERSION file: '{version}'")
    info(f"Current version: {BOLD}{version}{RESET}")
    return version


def compute_new_version(current: str, bump_type: str | None) -> str:
    """Compute the next version based on bump type."""
    if bump_type is None:
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


def bump_file(
    filepath: Path,
    pattern: str,
    replacement: str,
    dry_run: bool,
    label: str,
) -> None:
    """Replace exactly one occurrence of pattern in file."""
    content = filepath.read_text(encoding="utf-8")
    new_content, count = re.subn(pattern, replacement, content, count=1)

    if count == 0:
        fatal(f"No match for version pattern in {filepath.relative_to(ROOT)} ({label})")

    if dry_run:
        info(f"  [DRY-RUN] Would update {filepath.relative_to(ROOT)} ({label})")
    else:
        filepath.write_text(new_content, encoding="utf-8")
        success(f"  Updated {filepath.relative_to(ROOT)} ({label})")


def bump_versions(old: str, new: str, dry_run: bool) -> None:
    """Bump version string in all 4 source files (VERSION, Cargo.toml, plugin.json, pyproject.toml)."""
    info("Bumping versions...")
    old_re = re.escape(old)

    # VERSION file — simple overwrite (source of truth for display version)
    if dry_run:
        info(f"  [DRY-RUN] Would update VERSION ({old} -> {new})")
    else:
        VERSION_FILE.write_text(f"{new}\n", encoding="utf-8")
        success(f"  Updated VERSION ({old} -> {new})")

    bump_file(
        CARGO_TOML,
        rf'(version\s*=\s*"){old_re}(")',
        rf"\g<1>{new}\2",
        dry_run,
        label="Cargo.toml [package].version",
    )
    bump_file(
        PLUGIN_JSON,
        rf'("version"\s*:\s*"){old_re}(")',
        rf"\g<1>{new}\2",
        dry_run,
        label="plugin.json version",
    )
    bump_file(
        PYPROJECT_TOML,
        rf'(version\s*=\s*"){old_re}(")',
        rf"\g<1>{new}\2",
        dry_run,
        label="pyproject.toml version",
    )


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


def rust_source_changed() -> bool:
    """Check if any .rs files changed since the last git tag."""
    result = run(["git", "describe", "--tags", "--abbrev=0"])
    last_tag = result.stdout.strip() if result.returncode == 0 else ""
    if not last_tag:
        # No tags exist yet — assume source changed
        return True
    # Only check .rs files — Cargo.toml version changes don't trigger recompilation
    diff_result = run(
        ["git", "diff", "--name-only", last_tag, "HEAD", "--", str(RUST_SRC_DIR)],
    )
    return bool(diff_result.stdout.strip())


def build_binaries(dry_run: bool, force_build: bool = False) -> None:
    """Run pss_build.py --all. Skip if no .rs source changes (unless forced)."""
    info("Building binaries...")

    if not force_build and not rust_source_changed():
        info("  No Rust source changes since last tag, skipping build.")
        info("  Use --force-build to override.")
        return

    if dry_run:
        info("  [DRY-RUN] Would run: pss_build.py --all")
        return

    result = run(
        ["uv", "run", "python", str(BUILD_SCRIPT), "--all"],
        timeout=600,
    )
    if result.returncode != 0:
        warn(f"Build failed (non-blocking): {result.stderr.strip()}")
    else:
        success("  Binaries built successfully.")


def git_commit(old: str, new: str) -> None:
    """Stage versioned files and commit.

    Handles Cargo.toml inside the rust/ git submodule: commits the version
    bump inside the submodule first, then stages the submodule ref in the
    parent repo alongside the other version files.
    """
    info("Committing changes...")

    # -- Submodule handling: Cargo.toml lives inside rust/ submodule --
    rust_submodule = ROOT / "rust"
    cargo_is_submodule = (rust_submodule / ".git").exists()

    if cargo_is_submodule:
        # Commit Cargo.toml AND Cargo.lock inside the submodule.
        # Cargo.lock is modified by build_binaries() (cargo build --release)
        # and must be committed alongside the version bump to keep the
        # submodule ref clean — otherwise the dirty lockfile causes manual
        # fixup commits that can desync the submodule remote.
        info("  Committing Cargo.toml + Cargo.lock inside rust/ submodule...")
        cargo_lock = rust_submodule / "Cargo.lock"
        files_to_stage = [str(CARGO_TOML)]
        if cargo_lock.exists():
            files_to_stage.append(str(cargo_lock))
        result = run(
            ["git", "-C", str(rust_submodule), "add"] + files_to_stage,
        )
        if result.returncode != 0:
            fatal(f"submodule git add failed: {result.stderr.strip()}")
        sub_msg = f"bump: version {old} \u2192 {new}"
        result = run(
            ["git", "-C", str(rust_submodule), "commit", "-m", sub_msg],
        )
        if result.returncode != 0:
            fatal(f"submodule git commit failed: {result.stderr.strip()}")
        success("  Submodule rust/ committed.")

    # -- Parent repo: stage version files --
    files_to_add = [
        str(VERSION_FILE),
        str(PLUGIN_JSON),
        str(PYPROJECT_TOML),
        str(README_MD),
    ]

    if CHANGELOG_MD.exists():
        files_to_add.append(str(CHANGELOG_MD))
    if UV_LOCK.exists():
        files_to_add.append(str(UV_LOCK))
    if BIN_DIR.exists():
        files_to_add.append(str(BIN_DIR))

    # Stage the submodule ref (updated commit pointer) instead of Cargo.toml directly
    if cargo_is_submodule:
        files_to_add.append(str(rust_submodule))
    else:
        files_to_add.append(str(CARGO_TOML))

    result = run(["git", "add"] + files_to_add)
    if result.returncode != 0:
        fatal(f"git add failed: {result.stderr.strip()}")

    commit_msg = f"bump: version {old} \u2192 {new}"
    result = run(["git", "commit", "-m", commit_msg])
    if result.returncode != 0:
        fatal(f"git commit failed: {result.stderr.strip()}")

    success(f"  Committed: {commit_msg}")


def git_tag(new: str) -> None:
    """Create a git tag for the new version."""
    info(f"Tagging v{new}...")
    tag = f"v{new}"
    result = run(["git", "tag", tag])
    if result.returncode != 0:
        fatal(f"git tag failed: {result.stderr.strip()}")
    success(f"  Tagged: {tag}")


def git_push() -> None:
    """Push commits and tags to remote. Never skips pre-push hook.

    Also pushes the rust/ submodule if it exists, so the parent repo's
    submodule ref stays resolvable on the remote.  After pushing, verifies
    the submodule ref is actually reachable on the remote — this catches the
    case where the push silently succeeded but the commit was rejected.
    """
    info("Pushing to remote...")

    # Push rust/ submodule first (so parent's ref is resolvable on remote)
    rust_submodule = ROOT / "rust"
    if (rust_submodule / ".git").exists():
        info("  Pushing rust/ submodule...")
        result = run(["git", "-C", str(rust_submodule), "push"])
        if result.returncode != 0:
            fatal(f"submodule push failed: {result.stderr.strip()}")
        success("  Submodule rust/ pushed.")

        # Verify the exact commit the parent references (not submodule HEAD,
        # which may differ if extra commits were made in the submodule).
        ref_result = run(["git", "ls-tree", "HEAD", "rust"])
        if ref_result.returncode == 0 and ref_result.stdout.strip():
            parts = ref_result.stdout.strip().split()
            sha = parts[2] if len(parts) >= 3 else ""
            if sha:
                # fetch --dry-run checks reachability without downloading
                fetch_check = run(
                    ["git", "-C", str(rust_submodule), "fetch", "--dry-run", "origin", sha],
                    timeout=30,
                )
                if fetch_check.returncode != 0:
                    fatal(
                        f"Submodule commit {sha[:12]} was pushed but is NOT reachable on "
                        f"the remote. The parent push would break 'git clone --recurse-submodules'. "
                        f"Push the submodule manually: git -C rust push"
                    )
                success(f"  Submodule ref {sha[:12]} verified on remote.")

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


# ===========================================================================
# CPV sync
# ===========================================================================


def sync_cpv_scripts(dry_run: bool = False) -> None:
    """Fetch latest CPV validation scripts from GitHub using gh CLI."""
    info("Syncing CPV validation scripts from GitHub...")

    if shutil.which("gh") is None:
        warn("'gh' CLI not installed. Cannot sync CPV scripts.")
        return

    # Get the default branch (usually 'main')
    branch_result = run(
        ["gh", "api", f"repos/{CPV_REPO}", "--jq", ".default_branch"],
    )
    if branch_result.returncode != 0:
        warn(f"Could not query CPV repo: {branch_result.stderr.strip()}")
        return
    default_branch = branch_result.stdout.strip() or "main"

    scripts_dir = ROOT / "scripts"
    updated = 0
    failed = 0

    for script_name in CPV_SCRIPTS:
        # Fetch raw file content from GitHub
        url = f"https://raw.githubusercontent.com/{CPV_REPO}/{default_branch}/scripts/{script_name}"
        fetch_result = run(["curl", "-sS", "-f", url], timeout=30)

        if fetch_result.returncode != 0:
            warn(f"  Could not fetch {script_name}: {fetch_result.stderr.strip()}")
            failed += 1
            continue

        new_content = fetch_result.stdout
        target = scripts_dir / script_name

        # Compare with existing content
        if target.exists():
            existing = target.read_text(encoding="utf-8")
            if existing == new_content:
                continue  # No change

        if dry_run:
            info(f"  [DRY-RUN] Would update {script_name}")
        else:
            target.write_text(new_content, encoding="utf-8")
            success(f"  Updated {script_name}")
        updated += 1

    if updated == 0 and failed == 0:
        success("  All CPV scripts are up to date.")
    elif dry_run:
        info(f"  [DRY-RUN] Would update {updated} scripts.")
    else:
        success(f"  Synced {updated} scripts ({failed} failed).")


# ===========================================================================
# Hook installation
# ===========================================================================


def install_hook() -> None:
    """Install pre-push hook into .git/hooks/."""
    info("Installing pre-push hook...")

    git_dir = ROOT / ".git"
    if not git_dir.exists():
        fatal("Not a git repository (no .git directory found).")

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    if not HOOK_SOURCE.exists():
        fatal(f"Hook source not found: {HOOK_SOURCE}")

    # Copy hook file
    shutil.copy2(HOOK_SOURCE, HOOK_TARGET)
    # Make executable
    HOOK_TARGET.chmod(0o755)

    success(f"  Installed pre-push hook: {HOOK_TARGET}")
    info("  Hook will run 'pss_ship.py --gate' before every push.")


# ===========================================================================
# Release pipeline orchestrator
# ===========================================================================


def release_pipeline(args: argparse.Namespace) -> None:
    """Full release pipeline: lint + validate + test + bump + build + commit + push."""
    print()
    print(f"{BOLD}{CYAN}PSS Release Pipeline{RESET}")
    print(f"{CYAN}{'=' * 50}{RESET}")
    print()

    # Step 1: Pre-flight checks
    preflight_checks(
        skip_build=args.skip_build or args.version_only,
        dry_run=args.dry_run,
    )

    # Step 2: Lint
    if not args.skip_validate:
        if not run_linter():
            fatal("Lint failed, aborting release.")
    else:
        warn("Lint skipped (--skip-validate).")

    # Step 3: Plugin validation
    if not args.skip_validate:
        val_exit = run_validation()
        if val_exit == 0:
            success("Plugin validation passed.")
        elif val_exit == 4:
            warn("Plugin validation: NIT issues found (non-blocking).")
        elif val_exit in (1, 2, 3):
            severity = {1: "CRITICAL", 2: "MAJOR", 3: "MINOR"}
            fatal(
                f"Plugin validation: {severity.get(val_exit, 'UNKNOWN')} issues found. "
                "Fix before releasing."
            )
        else:
            fatal(f"Plugin validation failed with exit code {val_exit}.")
    else:
        warn("Plugin validation skipped (--skip-validate).")

    # Step 4: Tests
    if not args.skip_tests:
        if not run_tests():
            fatal("Tests failed, aborting release.")
    else:
        warn("Tests skipped (--skip-tests).")

    # Step 5: Sync CPV scripts (if requested)
    if args.sync_cpv:
        sync_cpv_scripts(dry_run=args.dry_run)

    # Step 6: Read current version and compute new
    old_version = read_current_version()
    new_version = compute_new_version(old_version, args.bump)

    # Step 7: Bump version in 4 files
    bump_versions(old_version, new_version, args.dry_run)

    # Step 7b: Sync uv.lock after pyproject.toml version change.
    # uv.lock only updates when uv resolves; if the build step is skipped
    # (no .rs changes), no uv command runs after the bump, leaving uv.lock stale.
    if not args.dry_run and UV_LOCK.exists():
        result = run(["uv", "lock"], timeout=60)
        if result.returncode != 0:
            warn(f"uv lock failed (non-blocking): {result.stderr.strip()}")

    # Step 8: Update README badge
    update_readme_badge(old_version, new_version, args.dry_run)

    # Step 9: Generate changelog
    generate_changelog(new_version, args.dry_run)

    # Step 10: Build binaries (skipped automatically if no .rs changes, unless --force-build)
    if not args.skip_build and not args.version_only:
        build_binaries(args.dry_run, force_build=args.force_build)
    elif args.skip_build:
        warn("Build skipped (--skip-build).")
    elif args.version_only:
        warn("Build skipped (--version-only).")

    # Step 11-13: Commit, tag, push
    if not args.version_only and not args.dry_run:
        git_commit(old_version, new_version)
        git_tag(new_version)
        git_push()
    elif args.dry_run:
        info(f"[DRY-RUN] Would commit, tag v{new_version}, and push.")
    elif args.version_only:
        warn("Commit/tag/push skipped (--version-only).")

    # Summary
    print_summary(old_version, new_version, args)
    success(f"Release v{new_version} complete!")


def print_summary(old: str, new: str, args: argparse.Namespace) -> None:
    """Print a summary table of what was done."""
    print()
    print(f"{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  Release Summary{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")
    print(f"  Version:       {old} -> {new}")
    print(f"  Dry run:       {'yes' if args.dry_run else 'no'}")
    print(f"  Tests:         {'skipped' if args.skip_tests else 'passed'}")
    print(f"  Lint:          {'skipped' if args.skip_validate else 'passed'}")
    print(f"  Validation:    {'skipped' if args.skip_validate else 'passed'}")
    print("  Files bumped:  4 (VERSION, Cargo.toml, plugin.json, pyproject.toml)")
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
    if args.sync_cpv:
        print("  CPV sync:      done")
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


# ===========================================================================
# Main
# ===========================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PSS Ship: unified release pipeline and pre-push gate.",
    )

    # Mode selection
    parser.add_argument(
        "--gate",
        action="store_true",
        help="Pre-push gate mode: lint + validate + test. Blocks on issues.",
    )
    parser.add_argument(
        "--install-hook",
        action="store_true",
        help="Install pre-push hook into .git/hooks/.",
    )

    # Release options
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
        "--force-build",
        action="store_true",
        help="Force binary rebuild even if no .rs source files changed.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip test step.",
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="Skip plugin validation step (escape hatch).",
    )
    parser.add_argument(
        "--version-only",
        action="store_true",
        help="Only bump version in files, no build/commit/push.",
    )
    parser.add_argument(
        "--sync-cpv",
        action="store_true",
        help="Sync CPV validation scripts from GitHub before release.",
    )

    args = parser.parse_args()

    # Dispatch to the right mode
    if args.gate:
        sys.exit(gate_pipeline())
    elif args.install_hook:
        install_hook()
    else:
        release_pipeline(args)


if __name__ == "__main__":
    main()
