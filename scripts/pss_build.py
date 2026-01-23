#!/usr/bin/env python3
"""
PSS Build Script - Cross-platform Rust binary builder.

Usage:
    python scripts/pss_build.py           # Build for current platform
    python scripts/pss_build.py --release # Build optimized release binary
    python scripts/pss_build.py --all     # Build for all platforms (needs cross)
    python scripts/pss_build.py --check   # Check if binary exists
"""

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# Supported targets for cross-compilation
TARGETS = {
    "darwin-arm64": "aarch64-apple-darwin",
    "darwin-x86_64": "x86_64-apple-darwin",
    "linux-arm64": "aarch64-unknown-linux-gnu",
    "linux-x86_64": "x86_64-unknown-linux-gnu",
    "windows-x86_64": "x86_64-pc-windows-msvc",
}


def get_script_root() -> Path:
    """Get the plugin root directory."""
    return Path(__file__).parent.parent.resolve()


def get_rust_dir() -> Path:
    """Get the Rust project directory."""
    return get_script_root() / "rust" / "skill-suggester"


def get_bin_dir() -> Path:
    """Get the binary output directory."""
    return get_rust_dir() / "bin"


def detect_platform() -> tuple[str, str]:
    """Detect current platform and architecture."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Normalize architecture names
    if machine in ("aarch64",):
        machine = "arm64"
    elif machine in ("amd64",):
        machine = "x86_64"

    return system, machine


def get_binary_name(system: str, machine: str) -> str:
    """Get the binary filename for a platform."""
    ext = ".exe" if system == "windows" else ""
    return f"pss-{system}-{machine}{ext}"


def check_rust_installed() -> bool:
    """Check if Rust toolchain is installed."""
    try:
        result = subprocess.run(
            ["cargo", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def check_cross_installed() -> bool:
    """Check if cross-compilation tool is installed."""
    try:
        result = subprocess.run(
            ["cross", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def build_native(release: bool = True) -> bool:
    """Build for the current platform."""
    rust_dir = get_rust_dir()
    bin_dir = get_bin_dir()

    if not rust_dir.exists():
        print(f"Error: Rust project not found at {rust_dir}", file=sys.stderr)
        return False

    # Ensure bin directory exists
    bin_dir.mkdir(parents=True, exist_ok=True)

    # Build command
    cmd = ["cargo", "build"]
    if release:
        cmd.append("--release")

    print("Building PSS binary...")
    print(f"  Directory: {rust_dir}")
    print(f"  Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=rust_dir, timeout=300)

    if result.returncode != 0:
        print("Error: Build failed", file=sys.stderr)
        return False

    # Copy binary to bin directory
    system, machine = detect_platform()
    binary_name = get_binary_name(system, machine)

    target_subdir = "release" if release else "debug"
    source = rust_dir / "target" / target_subdir / "skill-suggester"
    if system == "windows":
        source = source.with_suffix(".exe")

    dest = bin_dir / binary_name

    if source.exists():
        shutil.copy2(source, dest)
        # Make executable on Unix
        if system != "windows":
            dest.chmod(0o755)
        print(f"Binary installed: {dest}")
        return True
    print(f"Error: Built binary not found at {source}", file=sys.stderr)
    return False


def build_cross(target_key: str, release: bool = True) -> bool:
    """Build for a specific target using cross."""
    if target_key not in TARGETS:
        print(f"Error: Unknown target '{target_key}'", file=sys.stderr)
        print(f"Available targets: {', '.join(TARGETS.keys())}")
        return False

    rust_target = TARGETS[target_key]
    rust_dir = get_rust_dir()
    bin_dir = get_bin_dir()

    # Build command
    cmd = ["cross", "build", "--target", rust_target]
    if release:
        cmd.append("--release")

    print(f"Cross-compiling for {target_key} ({rust_target})...")
    result = subprocess.run(cmd, cwd=rust_dir, timeout=600)

    if result.returncode != 0:
        print(f"Error: Cross-compilation failed for {target_key}", file=sys.stderr)
        return False

    # Copy binary to bin directory
    system, machine = target_key.split("-")
    binary_name = get_binary_name(system, machine)

    target_subdir = "release" if release else "debug"
    source = rust_dir / "target" / rust_target / target_subdir / "skill-suggester"
    if system == "windows":
        source = source.with_suffix(".exe")

    dest = bin_dir / binary_name

    if source.exists():
        shutil.copy2(source, dest)
        dest.chmod(0o755)
        print(f"Binary installed: {dest}")
        return True
    print(f"Error: Built binary not found at {source}", file=sys.stderr)
    return False


def check_binary() -> bool:
    """Check if binary exists for current platform."""
    system, machine = detect_platform()
    binary_name = get_binary_name(system, machine)
    binary_path = get_bin_dir() / binary_name

    if binary_path.exists():
        print(f"Binary found: {binary_path}")
        # Try to get version
        try:
            result = subprocess.run(
                [str(binary_path), "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"Version: {result.stdout.strip()}")
        except (subprocess.TimeoutExpired, OSError):
            pass
        return True
    print(f"Binary not found: {binary_path}")
    print("Run 'python scripts/pss_build.py' to build it")
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Build PSS Rust binary for Claude Code plugin"
    )
    parser.add_argument(
        "--release",
        action="store_true",
        default=True,
        help="Build optimized release binary (default)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Build debug binary"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Build for all supported platforms (requires cross)"
    )
    parser.add_argument(
        "--target",
        choices=list(TARGETS.keys()),
        help="Build for specific target platform"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if binary exists for current platform"
    )
    parser.add_argument(
        "--list-targets",
        action="store_true",
        help="List all supported build targets"
    )

    args = parser.parse_args()

    # Handle --list-targets
    if args.list_targets:
        print("Supported build targets:")
        for key, rust_target in TARGETS.items():
            print(f"  {key:20} -> {rust_target}")
        return 0

    # Handle --check
    if args.check:
        return 0 if check_binary() else 1

    # Check Rust is installed
    if not check_rust_installed():
        print("Error: Rust toolchain not found", file=sys.stderr)
        print("Install from: https://rustup.rs/")
        return 1

    release = not args.debug

    # Handle --all (requires cross)
    if args.all:
        if not check_cross_installed():
            print("Error: 'cross' not installed", file=sys.stderr)
            print("Install with: cargo install cross")
            return 1

        success = True
        for target in TARGETS:
            if not build_cross(target, release):
                success = False

        return 0 if success else 1

    # Handle --target (requires cross for non-native)
    if args.target:
        system, machine = detect_platform()
        native_target = f"{system}-{machine}"

        if args.target == native_target:
            return 0 if build_native(release) else 1
        if not check_cross_installed():
            print("Error: 'cross' required for non-native targets")
            print("Install with: cargo install cross")
            return 1
        return 0 if build_cross(args.target, release) else 1

    # Default: build for current platform
    return 0 if build_native(release) else 1


if __name__ == "__main__":
    sys.exit(main())
