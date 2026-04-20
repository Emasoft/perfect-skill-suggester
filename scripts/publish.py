#!/usr/bin/env python3
"""
PSS Publish — Unified release pipeline and pre-push gate for Perfect Skill Suggester.

MANDATORY GATES (no bypass allowed):
  1. Lint (ruff)        — must pass with 0 errors
  2. Tests (pytest)     — must pass with 0 failures
  3. Validation (CPV)   — must pass with 0 CRITICAL/MAJOR/MINOR
  4. Bump version       — auto via `git cliff --bumped-version`, or manual --bump
  5. Changelog          — regenerated via `git cliff --bump --unreleased --tag`
  6. Commit + tag + push
  7. GitHub release     — `gh release create` with git-cliff-generated notes

Required tools: uv, uvx, rustup, git-cliff, gh

Modes:
    publish.py --gate             # pre-push hook mode (.git/hooks/pre-push)
    publish.py                    # auto-bump from conventional commits
    publish.py --bump patch       # manual bump override
    publish.py --dry-run          # preview — all checks still run, nothing pushed
    publish.py --install-hook     # install pre-push hook into .git/hooks/
"""

import argparse
import re
import shutil
import subprocess
import sys
import time
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
NLP_SRC_DIR = ROOT / "rust" / "negation-detector" / "src"
BUILD_ALL_SCRIPT = ROOT / "scripts" / "pss_build_all.py"
README_MD = ROOT / "README.md"
CHANGELOG_MD = ROOT / "CHANGELOG.md"
BUILD_SCRIPT = ROOT / "scripts" / "pss_build.py"
BIN_DIR = ROOT / "bin"
HOOK_SOURCE = ROOT / "git-hooks" / "pre-push"
HOOK_TARGET = ROOT / ".git" / "hooks" / "pre-push"

# -- Report housekeeping --
# reports/ is tracked (current/relevant reports). reports_dev/ is gitignored
# (*_dev/ wildcard). At release time, rotate files older than REPORTS_MAX_AGE_HOURS
# from reports/ into reports_dev/ so the tracked tree stays small.
REPORTS_DIR = ROOT / "reports"
REPORTS_DEV_DIR = ROOT / "reports_dev"
REPORTS_MAX_AGE_HOURS = 24

# -- CPV remote execution via uvx (no local script sync needed) --
CPV_REPO = "Emasoft/claude-plugins-validation"
CPV_UVX_FROM = f"git+https://github.com/{CPV_REPO}"

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
    try:
        return subprocess.run(
            cmd,
            cwd=cwd or ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        # Return a synthetic failed result instead of crashing
        return subprocess.CompletedProcess(
            args=cmd, returncode=124, stdout="", stderr=f"Timed out after {timeout}s"
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
    """Run CPV validation via uvx remote execution (no local scripts needed)."""
    info("Running plugin validation (uvx remote)...")

    if not shutil.which("uvx"):
        fatal("'uvx' not found. Install uv — validation is mandatory, no bypass allowed.")

    result = run(
        [
            "uvx",
            "--from", CPV_UVX_FROM,
            "--with", "pyyaml",
            "cpv-remote-validate", "plugin", ".",
        ],
        timeout=180,
    )

    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)

    return result.returncode


def run_tests() -> bool:
    """Run pytest and return True if passed.

    Uses `--extra dev` so the project venv (with pycozo) is active, not the
    uv-tool pytest that would run outside the venv. Phase B tests need
    pycozo to open the CozoDB — without --extra dev they'd hit
    ModuleNotFoundError and fail with no tests collected.
    """
    info("Running tests...")
    result = run(
        ["uv", "run", "--extra", "dev", "pytest", "tests/", "-q"],
        timeout=120,
    )
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


def preflight_checks(dry_run: bool = False) -> None:
    """Verify git working tree is clean and required tools are available."""
    info("Pre-flight checks...")

    # Git working tree must be clean (tolerated only in dry-run)
    result = run(["git", "status", "--porcelain"])
    if result.returncode != 0:
        fatal(f"git status failed: {result.stderr.strip()}")
    if result.stdout.strip() and not dry_run:
        fatal("Git working tree is dirty. Commit or stash changes before releasing.")

    # Mandatory tools — no bypass allowed
    required_tools = {
        "uv": "Python package manager",
        "uvx": "Used for CPV remote validation",
        "rustup": "Required for Rust binary builds",
        "git-cliff": "Required for changelog generation and version bumping",
        "gh": "Required for GitHub release publishing",
    }
    missing = [tool for tool in required_tools if shutil.which(tool) is None]
    if missing:
        details = ", ".join(f"{t} ({required_tools[t]})" for t in missing)
        fatal(f"Missing required tools: {details}")

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
    """Compute the next version.

    If bump_type is None, uses `git cliff --bumped-version` to auto-compute from
    conventional commits since the last tag. Otherwise applies manual patch/minor/major bump.
    """
    if bump_type is None:
        info("Computing next version via git-cliff (conventional commits)...")
        result = run(["git-cliff", "--bumped-version"], timeout=30)
        if result.returncode != 0:
            fatal(f"git-cliff --bumped-version failed: {result.stderr.strip()}")
        bumped = result.stdout.strip().lstrip("v")
        if not bumped:
            fatal("git-cliff returned empty version. Nothing to release.")
        if not re.match(r"^\d+\.\d+\.\d+$", bumped):
            fatal(f"git-cliff returned invalid version: '{bumped}'")
        if bumped == current:
            fatal(
                f"git-cliff reports no releasable changes since v{current}. "
                "Nothing to release. Make conventional commits (feat/fix/perf/refactor) "
                "or use --bump to force a version bump."
            )
        info(f"New version (git-cliff auto-bump): {BOLD}{bumped}{RESET}")
        return bumped

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
    """Run git-cliff to regenerate CHANGELOG.md with the new release entry. MANDATORY.

    Uses FULL regeneration (walks all tags since the beginning of time) rather
    than `--bump --unreleased -o` which would WIPE prior entries. This was a
    real bug discovered in the v2.9.34/2.9.35/2.9.36 release series: every
    release overwrote CHANGELOG.md with only its own entry, erasing the full
    historical record. Full regen produces a changelog with entries for every
    tagged release, so users see the complete version history.

    `chore(release)` commits are skipped by cliff.toml commit_parsers, so
    git-cliff sees the real content commits at each tag boundary.
    """
    info("Generating changelog (git-cliff)...")

    if dry_run:
        info(f"  [DRY-RUN] Would run: git-cliff --tag v{new} -o CHANGELOG.md")
        return

    result = run([
        "git-cliff", "--tag", f"v{new}", "-o", str(CHANGELOG_MD),
    ])
    if result.returncode != 0:
        fatal(f"git-cliff failed: {result.stderr.strip()}")
    success("  CHANGELOG.md generated (full history).")


def generate_release_notes(new: str) -> str:
    """Generate release notes for the current version only (for GitHub release body).

    Uses `--latest` which returns ONLY the most recent tag's commit entries.
    This runs AFTER git_tag creates the new tag (see main() pipeline ordering),
    so "latest" == the just-created tag == `v{new}`. `--strip header` drops the
    top-level "# Changelog" header while preserving the per-release body with
    commit entries grouped by conventional-commit type.

    Previously we used `--current` which always returned the most-recently
    *released* tag, ignoring the `--tag` argument entirely. `--latest` correctly
    tracks the just-tagged version.
    """
    result = run([
        "git-cliff", "--latest", "--strip", "header",
    ])
    if result.returncode != 0:
        fatal(f"git-cliff release notes failed: {result.stderr.strip()}")
    notes = result.stdout.strip()
    # Sanity check: `--latest` should match the new version we just tagged.
    expected_header = f"## [{new}]"
    if notes and expected_header not in notes:
        warn(
            f"git-cliff --latest did not produce notes for v{new}; "
            f"got: {notes.splitlines()[0] if notes else '(empty)'}"
        )
    return notes


def create_github_release(new: str, dry_run: bool) -> None:
    """Publish a GitHub release with changelog-generated notes. MANDATORY."""
    info("Publishing GitHub release...")

    if dry_run:
        info(f"  [DRY-RUN] Would run: gh release create v{new} ...")
        return

    notes = generate_release_notes(new)
    # Write notes to a temp file (avoids shell escaping issues with multiline notes)
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".md", delete=False
    ) as tmp:
        tmp.write(notes if notes else f"Release v{new}")
        notes_path = tmp.name

    try:
        result = run([
            "gh", "release", "create", f"v{new}",
            "--title", f"v{new}",
            "--notes-file", notes_path,
        ], timeout=60)
        if result.returncode != 0:
            fatal(f"gh release create failed: {result.stderr.strip()}")
        success(f"  GitHub release v{new} published.")
    finally:
        Path(notes_path).unlink(missing_ok=True)


def rust_source_changed() -> bool:
    """Check if any .rs files in the main skill-suggester crate changed since the last tag."""
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


def nlp_source_changed() -> bool:
    """Check if any .rs files in negation-detector changed since the last tag.

    Used to decide whether to rebuild pss-nlp-* binaries. Unlike the main
    skill-suggester crate, negation-detector changes rarely, so the binaries
    normally don't need rebuilding per release.
    """
    result = run(["git", "describe", "--tags", "--abbrev=0"])
    last_tag = result.stdout.strip() if result.returncode == 0 else ""
    if not last_tag:
        return True
    diff_result = run(
        ["git", "diff", "--name-only", last_tag, "HEAD", "--", str(NLP_SRC_DIR)],
    )
    return bool(diff_result.stdout.strip())


def build_pss_nlp(dry_run: bool, force_build: bool = False) -> None:
    """Conditionally rebuild pss-nlp-* binaries when negation-detector source changed.

    pss-nlp is a separate Rust crate (rust/negation-detector/) that PSS calls
    via subprocess for negation detection. It ships its own 5 platform binaries
    (pss-nlp-darwin-arm64, etc.). Because the crate changes rarely, we only
    rebuild when there are actual source diffs since the last tag.

    Uses scripts/pss_build_all.py --nlp-only which handles all 5 targets.
    Build failures are FATAL — if pss-nlp source changed, it must rebuild
    successfully or the release aborts.
    """
    info("Checking pss-nlp (negation-detector) binaries...")

    if not force_build and not nlp_source_changed():
        info("  No negation-detector source changes since last tag — skipping pss-nlp rebuild.")
        return

    if dry_run:
        info("  [DRY-RUN] Would run: pss_build_all.py --nlp-only")
        return

    info("  negation-detector source changed — rebuilding pss-nlp-* binaries...")
    result = run(
        ["uv", "run", "python", str(BUILD_ALL_SCRIPT), "--nlp-only"],
        timeout=2700,
    )
    if result.returncode != 0:
        stderr_tail = result.stderr.strip()[-2000:] if result.stderr else ""
        stdout_tail = result.stdout.strip()[-2000:] if result.stdout else ""
        fatal(
            "pss-nlp build failed — release aborted. Last stderr:\n"
            f"{stderr_tail}\nLast stdout:\n{stdout_tail}\n"
            "Fix the build environment and re-run publish.py."
        )
    success("  pss-nlp binaries built successfully.")


def build_binaries(dry_run: bool, force_build: bool = False) -> None:
    """Run pss_build.py --all. Skip if no .rs source changes (unless forced).

    FATAL on failure — a release must ship with ALL platform binaries. When
    cross/zigbuild fail on any target (e.g. stale Docker image, expired
    toolchain, missing mingw), publish.py stops and the operator must fix
    the build environment before re-running. Previously this was a warning
    and v2.9.35 shipped with a 1-month-stale windows binary as a result.
    """
    info("Building binaries...")

    if not force_build and not rust_source_changed():
        info("  No Rust source changes since last tag, skipping build.")
        info("  Use --force-build to override.")
        return

    if dry_run:
        info("  [DRY-RUN] Would run: pss_build.py --all")
        return

    # Record the build start timestamp BEFORE running the subprocess.
    # The post-build verification uses this to check "was this binary rebuilt
    # during THIS run?" — previously we used a 30-minute wall-clock window,
    # which falsely flagged the first binary (darwin-arm64, built at t=2min)
    # as stale when a 45-min full cross build finished verification at t=47min.
    # Using build_started_at makes the check wall-clock-independent.
    build_started_at = time.time() - 2  # 2s slack for filesystem mtime granularity

    # 45-minute timeout. Cross builds can pull Docker images on first run
    # (ghcr.io/cross-rs/* containers are 500MB+ each) and nlprule_build
    # downloads the English model inside each target container. Total
    # wall-clock for a cold build of all 5 targets is typically ~15-20 min;
    # 45 min is a generous safety net.
    result = run(
        ["uv", "run", "python", str(BUILD_SCRIPT), "--all"],
        timeout=2700,
    )
    if result.returncode != 0:
        stderr_tail = result.stderr.strip()[-2000:] if result.stderr else ""
        stdout_tail = result.stdout.strip()[-2000:] if result.stdout else ""
        fatal(
            "Binary build failed — release aborted. Last stderr:\n"
            f"{stderr_tail}\nLast stdout:\n{stdout_tail}\n"
            "Fix the build environment (Docker running? cross installed? "
            "rustup toolchain up to date?) and re-run publish.py."
        )
    success("  Binaries built successfully.")

    # Sanity check: verify all 5 platform binaries were actually produced
    # and rebuilt DURING this run (mtime >= build_started_at). This catches
    # silent failures where pss_build.py exits 0 but a target was skipped.
    required_binaries = {
        "pss-darwin-arm64",
        "pss-darwin-x86_64",
        "pss-linux-arm64",
        "pss-linux-x86_64",
        "pss-windows-x86_64.exe",
    }
    bin_dir = ROOT / "bin"
    now = time.time()
    stale: list[str] = []
    missing: list[str] = []
    for bname in required_binaries:
        bpath = bin_dir / bname
        if not bpath.exists():
            missing.append(bname)
            continue
        mtime = bpath.stat().st_mtime
        if mtime < build_started_at:
            stale.append(
                f"{bname} (mtime {int(now - mtime)}s ago, before build_started)"
            )
    if missing or stale:
        details = ""
        if missing:
            details += f"\n  Missing: {', '.join(missing)}"
        if stale:
            details += f"\n  Stale (not rebuilt this run): {', '.join(stale)}"
        fatal(
            "Post-build verification failed — publish.py refuses to ship "
            "a release with missing or stale platform binaries.\n"
            f"Expected all 5 binaries in bin/ to be rebuilt just now:{details}"
        )
    info("  Verified: all 5 platform binaries present and fresh.")


def git_commit(_old: str, new: str) -> None:
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
        sub_msg = f"chore(release): {new}"
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

    commit_msg = f"chore(release): {new}"
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
    info("  Hook will run 'publish.py --gate' before every push.")


# ===========================================================================
# Release pipeline orchestrator
# ===========================================================================


def release_pipeline(args: argparse.Namespace) -> None:
    """Full release pipeline with MANDATORY gates — no bypass allowed.

    Order:
      1. Pre-flight: required tools + clean working tree
      2. Lint (ruff)            — must pass, 0 errors
      3. Tests (pytest)         — must pass, 0 failures
      4. Validation (CPV)       — must pass, 0 CRITICAL/MAJOR/MINOR
      5. Bump version           — auto via git-cliff, or manual --bump
      6. git-cliff              — regenerate CHANGELOG.md
      7. uv lock + README badge + binary build
      8. Commit + tag + push    — only after all gates pass
      9. GitHub release         — gh release create with auto-generated notes

    Any failure aborts the release. No --skip-* flags exist.
    """
    print()
    print(f"{BOLD}{CYAN}PSS Release Pipeline{RESET}")
    print(f"{CYAN}{'=' * 50}{RESET}")
    print()

    # Step 1: Pre-flight checks (required tools + clean tree)
    # Report rotation is NOT part of the release pipeline: reports/ and
    # reports_dev/ are both gitignored (they contain private data), so
    # rotating produces no tracked-file change and no commit. Users who
    # want to clean up stale reports run `publish.py --rotate-reports`
    # manually.
    preflight_checks(dry_run=args.dry_run)

    # Step 2: Lint (MANDATORY)
    if not run_linter():
        fatal("Lint failed. Fix all errors before releasing. No exceptions.")

    # Step 3: Tests (MANDATORY)
    if not run_tests():
        fatal("Tests failed. Fix all failures before releasing. No exceptions.")

    # Step 4: Plugin validation (MANDATORY)
    val_exit = run_validation()
    if val_exit == 0:
        success("Plugin validation passed.")
    elif val_exit == 4:
        warn("Plugin validation: NIT issues found (non-blocking).")
    elif val_exit in (1, 2, 3):
        severity = {1: "CRITICAL", 2: "MAJOR", 3: "MINOR"}
        fatal(
            f"Plugin validation: {severity.get(val_exit, 'UNKNOWN')} issues found. "
            "Fix all issues before releasing. No exceptions."
        )
    else:
        fatal(f"Plugin validation failed with exit code {val_exit}.")

    # Step 5: Compute version (auto via git-cliff, or manual --bump)
    old_version = read_current_version()
    new_version = compute_new_version(old_version, args.bump)

    # Step 6: Bump version in 4 files (VERSION, Cargo.toml, plugin.json, pyproject.toml)
    bump_versions(old_version, new_version, args.dry_run)

    # Step 7: Sync uv.lock after pyproject.toml version change
    if not args.dry_run and UV_LOCK.exists():
        result = run(["uv", "lock"], timeout=60)
        if result.returncode != 0:
            fatal(f"uv lock failed: {result.stderr.strip()}")

    # Step 8: Update README badge
    update_readme_badge(old_version, new_version, args.dry_run)

    # Step 9: Regenerate CHANGELOG.md via git-cliff (MANDATORY)
    generate_changelog(new_version, args.dry_run)

    # Step 10: Build binaries (auto-skipped if no .rs changes, unless --force-build)
    build_binaries(args.dry_run, force_build=args.force_build)

    # Step 10b: Conditionally rebuild pss-nlp (only when negation-detector changed)
    build_pss_nlp(args.dry_run, force_build=args.force_build)

    # Step 11-13: Commit + tag + push (only after all gates pass)
    if not args.dry_run:
        git_commit(old_version, new_version)
        git_tag(new_version)
        git_push()
    else:
        info(f"[DRY-RUN] Would commit, tag v{new_version}, and push.")

    # Step 14: Publish GitHub release (MANDATORY)
    create_github_release(new_version, args.dry_run)

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
    print("  Lint:          passed")
    print("  Tests:         passed")
    print("  Validation:    passed")
    print("  Files bumped:  4 (VERSION, Cargo.toml, plugin.json, pyproject.toml)")
    print("  README badge:  updated")
    print("  Changelog:     generated")
    print(f"  Build:         {'dry-run' if args.dry_run else 'attempted'}")
    if args.dry_run:
        print("  Git commit:    skipped")
        print("  Git tag:       skipped")
        print("  Git push:      skipped")
        print("  GH release:    skipped")
    else:
        print(f"  Git commit:    chore(release): {new}")
        print(f"  Git tag:       v{new}")
        print("  Git push:      done")
        print(f"  GH release:    published v{new}")
    print(f"{BOLD}{'=' * 60}{RESET}")
    print()


# ===========================================================================
# Report rotation (reports/ -> reports_dev/)
# ===========================================================================


def rotate_old_reports(
    max_age_hours: int = REPORTS_MAX_AGE_HOURS, dry_run: bool = False
) -> tuple[int, int]:
    """Move files older than max_age_hours from reports/ to reports_dev/.

    reports/ is git-tracked; reports_dev/ is gitignored via *_dev/. Old LLM
    analysis output (batch_check_*, code_task_*, etc.) accumulates over time
    and bloats the tracked tree. This rotates the stale files out while
    keeping the directory structure intact under reports_dev/.

    Returns (moved_count, total_bytes). Silent when reports/ is absent.
    """
    if not REPORTS_DIR.exists() or not REPORTS_DIR.is_dir():
        return (0, 0)

    cutoff = time.time() - max_age_hours * 3600
    moved = 0
    total_bytes = 0

    for src in REPORTS_DIR.rglob("*"):
        if not src.is_file():
            continue
        try:
            mtime = src.stat().st_mtime
        except OSError:
            continue
        if mtime >= cutoff:
            continue  # Still fresh — leave it in reports/

        rel = src.relative_to(REPORTS_DIR)
        dst = REPORTS_DEV_DIR / rel
        size = src.stat().st_size

        if dry_run:
            info(f"  [rotate] would move ({size} B): {rel}")
            moved += 1
            total_bytes += size
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            src.replace(dst)  # atomic on same filesystem
        except OSError as e:
            warn(f"  [rotate] FAILED to move {rel}: {e}")
            continue
        moved += 1
        total_bytes += size

    # Prune now-empty subdirectories under reports/ (but keep reports/ itself)
    if not dry_run:
        for d in sorted(REPORTS_DIR.rglob("*"), reverse=True):
            if d.is_dir() and d != REPORTS_DIR:
                try:
                    d.rmdir()  # only succeeds if empty
                except OSError:
                    pass

    return (moved, total_bytes)


# ===========================================================================
# Rotate-reports standalone mode
# ===========================================================================


def rotate_reports_mode(args: argparse.Namespace) -> int:
    """Standalone report rotation: move stale files from reports/ to reports_dev/.

    Both reports/ and reports_dev/ are gitignored (reports often carry private
    data), so rotation produces no git changes — this is purely a filesystem
    housekeeping chore to keep the active reports/ folder browsable.
    """
    moved, bytes_moved = rotate_old_reports(dry_run=args.dry_run)
    if moved == 0:
        info(f"No files older than {REPORTS_MAX_AGE_HOURS} hours under reports/ — nothing to rotate.")
        return 0
    action = "would move" if args.dry_run else "moved"
    info(f"Report rotation: {action} {moved} file(s) ({bytes_moved / 1024:.1f} KB) "
         f"older than {REPORTS_MAX_AGE_HOURS} hours from reports/ -> reports_dev/.")
    return 0


# ===========================================================================
# Clean mode (wraps scripts/pss_clean.py for disk-artifact cleanup)
# ===========================================================================


def clean_mode(args: argparse.Namespace) -> int:
    """Invoke pss_clean.py with pass-through flags. Explicit opt-in only.

    Intentionally shells out rather than importing: scripts/ is not a package
    (no __init__.py) and adding one would affect every other consumer. The
    subprocess hop costs <50ms and preserves pss_clean.py's self-contained
    safety guards (PROJECT_ROOT containment, protected-name list, workspace
    dedup for cargo clean).

    Output is streamed live to the terminal — cleanup reports per-step sizes
    and the user needs to see them, so we do NOT use the capturing run()
    helper here.
    """
    cmd = [sys.executable, str(ROOT / "scripts" / "pss_clean.py")]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.rust_only:
        cmd.append("--rust-only")
    if args.docker:
        cmd.append("--docker")
    result = subprocess.run(cmd, cwd=ROOT, check=False, timeout=600)
    return result.returncode


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
        help="Manual bump type override. Default: auto via `git cliff --bumped-version`.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without committing or pushing. All checks still run.",
    )
    parser.add_argument(
        "--force-build",
        action="store_true",
        help="Force binary rebuild even if no .rs source files changed.",
    )

    # Clean mode (explicit opt-in — never runs automatically as part of release
    # because it busts cargo incremental cache and slows subsequent dev cycles).
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove regenerable build artifacts (rust/target, orphan src targets, "
             ".venv, .mypy_cache). Standalone mode: runs cleanup and exits.",
    )
    parser.add_argument(
        "--rust-only",
        action="store_true",
        help="With --clean: only clean Rust build artifacts (skip .venv, .mypy_cache).",
    )
    parser.add_argument(
        "--docker",
        action="store_true",
        help="With --clean: also prune stale cross-rs/super-linter Docker images.",
    )

    # Report rotation (reports/ -> reports_dev/) — also runs automatically
    # at the start of every release; this flag is for manual invocation.
    parser.add_argument(
        "--rotate-reports",
        action="store_true",
        help=f"Standalone: move files in reports/ older than "
             f"{REPORTS_MAX_AGE_HOURS} hours into reports_dev/ and exit. "
             "Also runs automatically at release start.",
    )
    args = parser.parse_args()

    # Dispatch to the right mode
    if args.clean:
        sys.exit(clean_mode(args))
    elif args.rotate_reports:
        sys.exit(rotate_reports_mode(args))
    elif args.gate:
        sys.exit(gate_pipeline())
    elif args.install_hook:
        install_hook()
    else:
        release_pipeline(args)


if __name__ == "__main__":
    main()
