#!/usr/bin/env python3
"""
PSS Setup Script - Complete setup and verification for Perfect Skill Suggester

Usage:
    python scripts/pss_setup.py           # Run full setup
    python scripts/pss_setup.py --verify  # Verify installation only
    python scripts/pss_setup.py --build   # Build binary only
    python scripts/pss_setup.py --index   # Generate skill index only
"""

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def get_plugin_root() -> Path:
    """Get the plugin root directory."""
    return Path(__file__).parent.parent.resolve()


def get_rust_dir() -> Path:
    """Get the Rust project directory."""
    return get_plugin_root() / "rust" / "skill-suggester"


def get_bin_dir() -> Path:
    """Get the binary output directory."""
    return get_rust_dir() / "bin"


def detect_platform() -> tuple[str, str]:
    """Detect current platform and architecture."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    if machine in ("aarch64",):
        machine = "arm64"
    elif machine in ("amd64",):
        machine = "x86_64"

    return system, machine


def get_binary_name() -> str:
    """Get the binary filename for current platform."""
    system, machine = detect_platform()
    ext = ".exe" if system == "windows" else ""
    return f"pss-{system}-{machine}{ext}"


def print_header(text: str):
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def print_step(text: str):
    """Print a step."""
    print(f"\n>> {text}")


def print_ok(text: str):
    """Print success message."""
    print(f"   [OK] {text}")


def print_fail(text: str):
    """Print failure message."""
    print(f"   [FAIL] {text}")


def print_warn(text: str):
    """Print warning message."""
    print(f"   [WARN] {text}")


def check_python_version() -> bool:
    """Check Python version is 3.8+."""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        print_ok(f"Python {version.major}.{version.minor}.{version.micro}")
        return True
    print_fail(f"Python {version.major}.{version.minor} (need 3.8+)")
    return False


def check_rust_installed() -> bool:
    """Check Rust toolchain."""
    try:
        result = subprocess.run(
            ["cargo", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            print_ok(f"Rust: {version}")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    print_fail("Rust not installed (https://rustup.rs/)")
    return False


def check_binary_exists() -> bool:
    """Check if binary exists for current platform."""
    binary_name = get_binary_name()
    binary_path = get_bin_dir() / binary_name

    if binary_path.exists():
        # Verify it runs
        try:
            result = subprocess.run(
                [str(binary_path), "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                print_ok(f"Binary: {binary_name} ({version})")
                return True
        except (subprocess.TimeoutExpired, OSError) as e:
            print_fail(f"Binary exists but fails to run: {e}")
            return False

    print_warn(f"Binary not found: {binary_name}")
    return False


def check_skill_index() -> bool:
    """Check if skill index exists and is valid."""
    index_path = Path.home() / ".claude" / "cache" / "skill-index.json"

    if not index_path.exists():
        print_warn("Skill index not found (run /pss-reindex-skills)")
        return False

    try:
        data = json.loads(index_path.read_text())
        skills_count = len(data.get("skills", {}))
        version = data.get("version", "unknown")
        method = data.get("method", "unknown")
        print_ok(f"Skill index: {skills_count} skills (v{version}, {method})")
        return True
    except (json.JSONDecodeError, OSError) as e:
        print_fail(f"Skill index invalid: {e}")
        return False


def check_hooks_configured() -> bool:
    """Check if hooks are configured."""
    hooks_file = get_plugin_root() / "hooks" / "hooks.json"

    if not hooks_file.exists():
        print_fail("hooks/hooks.json not found")
        return False

    try:
        data = json.loads(hooks_file.read_text())
        hooks = data.get("hooks", {})
        if "UserPromptSubmit" in hooks:
            print_ok("Hooks configured (UserPromptSubmit)")
            return True
        print_warn("UserPromptSubmit hook not configured")
        return False
    except (json.JSONDecodeError, OSError) as e:
        print_fail(f"hooks.json invalid: {e}")
        return False


def check_scripts_executable() -> bool:
    """Check if Python scripts are executable."""
    scripts_dir = get_plugin_root() / "scripts"
    all_ok = True

    for script in scripts_dir.glob("*.py"):
        import os
        if os.access(script, os.X_OK):
            pass  # Don't print each one
        else:
            print_warn(f"Script not executable: {script.name}")
            all_ok = False

    if all_ok:
        py_count = len(list(scripts_dir.glob("*.py")))
        print_ok(f"All {py_count} scripts executable")

    return all_ok


def build_binary() -> bool:
    """Build the Rust binary."""
    print_step("Building Rust binary...")

    rust_dir = get_rust_dir()
    bin_dir = get_bin_dir()

    if not rust_dir.exists():
        print_fail(f"Rust project not found: {rust_dir}")
        return False

    bin_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["cargo", "build", "--release"],
        cwd=rust_dir
    )

    if result.returncode != 0:
        print_fail("Cargo build failed")
        return False

    # Copy to bin directory
    system, _ = detect_platform()
    binary_name = get_binary_name()

    source = rust_dir / "target" / "release" / "skill-suggester"
    if system == "windows":
        source = source.with_suffix(".exe")

    dest = bin_dir / binary_name

    if source.exists():
        shutil.copy2(source, dest)
        if system != "windows":
            dest.chmod(0o755)
        print_ok(f"Binary installed: {binary_name}")
        return True
    print_fail(f"Built binary not found: {source}")
    return False


def make_scripts_executable():
    """Make all Python scripts executable."""
    print_step("Making scripts executable...")

    scripts_dir = get_plugin_root() / "scripts"
    count = 0

    for script in scripts_dir.glob("*.py"):
        script.chmod(0o755)
        count += 1

    print_ok(f"Made {count} scripts executable")


def run_validation() -> bool:
    """Run plugin validation."""
    print_step("Running plugin validation...")

    validator = get_plugin_root() / "scripts" / "pss_validate_plugin.py"

    result = subprocess.run(
        [sys.executable, str(validator)],
        cwd=get_plugin_root()
    )

    return result.returncode == 0


def verify_installation() -> bool:
    """Verify complete installation."""
    print_header("Verifying PSS Installation")

    checks = [
        ("Python version", check_python_version),
        ("Rust toolchain", check_rust_installed),
        ("PSS binary", check_binary_exists),
        ("Skill index", check_skill_index),
        ("Hook configuration", check_hooks_configured),
        ("Script permissions", check_scripts_executable),
    ]

    results = []
    for name, check_fn in checks:
        print_step(f"Checking {name}...")
        results.append(check_fn())

    print_header("Summary")
    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"\n  All {total} checks passed!")
        return True
    print(f"\n  {passed}/{total} checks passed")
    print("  Run 'python scripts/pss_setup.py' to fix issues")
    return False


def full_setup() -> bool:
    """Run complete setup."""
    print_header("PSS Complete Setup")

    system, machine = detect_platform()
    print(f"\n  Platform: {system}-{machine}")
    print(f"  Plugin root: {get_plugin_root()}")

    # Step 1: Check Python
    print_step("Checking Python version...")
    if not check_python_version():
        print_fail("Python 3.8+ required")
        return False

    # Step 2: Check Rust
    print_step("Checking Rust toolchain...")
    if not check_rust_installed():
        print("\n  Install Rust from: https://rustup.rs/")
        return False

    # Step 3: Build binary
    if not check_binary_exists():
        if not build_binary():
            return False
    else:
        print_step("Binary already exists, skipping build")

    # Step 4: Make scripts executable
    make_scripts_executable()

    # Step 5: Validate plugin
    if not run_validation():
        print_warn("Validation had issues, check output above")

    # Step 6: Final verification
    return verify_installation()


def main():
    parser = argparse.ArgumentParser(
        description="Setup and verify Perfect Skill Suggester plugin"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify installation only"
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build binary only"
    )

    args = parser.parse_args()

    if args.verify:
        return 0 if verify_installation() else 1

    if args.build:
        if not check_rust_installed():
            return 1
        return 0 if build_binary() else 1

    # Full setup
    return 0 if full_setup() else 1


if __name__ == "__main__":
    sys.exit(main())
