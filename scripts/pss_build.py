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
    "linux-arm64": "aarch64-unknown-linux-musl",
    "linux-x86_64": "x86_64-unknown-linux-musl",
    "windows-x86_64": "x86_64-pc-windows-gnu",
    "windows-arm64": "aarch64-pc-windows-gnullvm",
    "android-arm64": "aarch64-linux-android",
    "wasm32": "wasm32-wasip1",
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
    if system == "wasm32":
        return "pss-wasm32.wasm"
    ext = ".exe" if system == "windows" else ""
    return f"pss-{system}-{machine}{ext}"


def check_rust_installed() -> bool:
    """Check if Rust toolchain is installed via rustup (not Homebrew)."""
    try:
        result = subprocess.run(
            ["cargo", "--version"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Cargo not found - check if rustup exists but cargo isn't in PATH
    try:
        rustup_result = subprocess.run(
            ["rustup", "show"], capture_output=True, text=True, timeout=10
        )
        if rustup_result.returncode == 0:
            print(
                "Error: rustup is installed but 'cargo' is not in PATH.",
                file=sys.stderr,
            )
            print(
                "Fix: Run 'source $HOME/.cargo/env' or add $HOME/.cargo/bin to your PATH.",
                file=sys.stderr,
            )
            return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    print("Error: Rust toolchain not found.", file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "PSS requires the Rust toolchain installed via rustup (NOT Homebrew).",
        file=sys.stderr,
    )
    print(
        "Homebrew's Rust lacks 'rustup' and cannot add cross-compilation targets.",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    print("To install:", file=sys.stderr)
    print(
        "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh",
        file=sys.stderr,
    )
    print("  source $HOME/.cargo/env", file=sys.stderr)
    print("", file=sys.stderr)
    print("If you have Homebrew Rust installed, remove it first:", file=sys.stderr)
    print("  brew uninstall rust", file=sys.stderr)
    return False


def check_cross_installed() -> bool:
    """Check if cross-compilation tool and Docker are available."""
    # Check Docker first (cross requires it)
    try:
        docker_result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=15
        )
        if docker_result.returncode != 0:
            print("Error: Docker is not running.", file=sys.stderr)
            print(
                "'cross' requires Docker to run cross-compilation containers.",
                file=sys.stderr,
            )
            print("", file=sys.stderr)
            print("Start Docker Desktop, or run:", file=sys.stderr)
            print("  open -a Docker  # macOS", file=sys.stderr)
            print("  sudo systemctl start docker  # Linux", file=sys.stderr)
            return False
    except FileNotFoundError:
        print("Error: Docker is not installed.", file=sys.stderr)
        print("'cross' requires Docker for cross-compilation.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Install Docker:", file=sys.stderr)
        print("  macOS: brew install --cask docker", file=sys.stderr)
        print("  Linux: https://docs.docker.com/engine/install/", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print("Error: Docker is not responding (timed out).", file=sys.stderr)
        print(
            "Ensure Docker Desktop is fully started before building.", file=sys.stderr
        )
        return False

    # Check cross
    try:
        result = subprocess.run(
            ["cross", "--version"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    print("Error: 'cross' is not installed.", file=sys.stderr)
    print(
        "'cross' is a Rust tool that uses Docker to cross-compile for other platforms.",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    print("Install with:", file=sys.stderr)
    print(
        "  cargo install cross --git https://github.com/cross-rs/cross", file=sys.stderr
    )
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
        print("Error: Native build failed.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Common causes:", file=sys.stderr)
        print("  1. Missing Rust toolchain: cargo --version", file=sys.stderr)
        print(
            "  2. Compilation errors in source: check Cargo.toml dependencies",
            file=sys.stderr,
        )
        print(
            f"  3. Try cleaning build cache: cargo clean (in {rust_dir})",
            file=sys.stderr,
        )
        return False

    # Copy binary to bin directory
    system, machine = detect_platform()
    binary_name = get_binary_name(system, machine)

    target_subdir = "release" if release else "debug"
    source = rust_dir / "target" / target_subdir / "pss"
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


def build_wasm(release: bool = True) -> bool:
    """Build for WASM target (does not require cross or Docker)."""
    rust_dir = get_rust_dir()
    bin_dir = get_bin_dir()
    rust_target = TARGETS["wasm32"]

    # Check if wasm target is installed
    try:
        check_result = subprocess.run(
            ["rustup", "target", "list", "--installed"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if rust_target not in check_result.stdout:
            print(
                f"Error: Rust target '{rust_target}' is not installed.", file=sys.stderr
            )
            print("", file=sys.stderr)
            print("Install with:", file=sys.stderr)
            print(f"  rustup target add {rust_target}", file=sys.stderr)
            return False
    except FileNotFoundError:
        print(
            "Error: 'rustup' not found. WASM builds require rustup (not Homebrew Rust).",
            file=sys.stderr,
        )
        print(
            "Install: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh",
            file=sys.stderr,
        )
        return False

    bin_dir.mkdir(parents=True, exist_ok=True)

    cmd = ["cargo", "build", "--target", rust_target]
    if release:
        cmd.append("--release")

    print(f"Building WASM binary ({rust_target})...")
    print(f"  Directory: {rust_dir}")
    print(f"  Command: {' '.join(cmd)}")

    build_result = subprocess.run(cmd, cwd=rust_dir, timeout=300)

    if build_result.returncode != 0:
        print("Error: WASM build failed.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Common causes:", file=sys.stderr)
        print(
            "  1. Missing wasm target: rustup target add wasm32-wasip1", file=sys.stderr
        )
        print(
            '  2. Code uses platform-specific APIs not gated with #[cfg(not(target_arch = "wasm32"))]',
            file=sys.stderr,
        )
        return False

    target_subdir = "release" if release else "debug"
    source = rust_dir / "target" / rust_target / target_subdir / "pss.wasm"
    dest = bin_dir / "pss-wasm32.wasm"

    if source.exists():
        shutil.copy2(source, dest)
        print(f"WASM binary installed: {dest}")
        return True
    print(f"Error: Built WASM binary not found at {source}", file=sys.stderr)
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
        print(
            f"Error: Cross-compilation failed for {target_key} ({rust_target}).",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        print("Common causes:", file=sys.stderr)
        print(
            "  1. Docker not running: open -a Docker (macOS) or sudo systemctl start docker (Linux)",
            file=sys.stderr,
        )
        print(
            "  2. First build for this target: Docker needs to pull the cross image (may take minutes)",
            file=sys.stderr,
        )
        print(
            "  3. Network error: Docker needs internet to pull cross-rs images from ghcr.io",
            file=sys.stderr,
        )
        return False

    # Copy binary to bin directory
    system, machine = target_key.split("-")
    binary_name = get_binary_name(system, machine)

    target_subdir = "release" if release else "debug"
    source = rust_dir / "target" / rust_target / target_subdir / "pss"
    if "windows" in target_key:
        source = source.with_suffix(".exe")
    elif target_key == "wasm32":
        source = source.with_suffix(".wasm")

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
                timeout=5,
            )
            if result.returncode == 0:
                print(f"Version: {result.stdout.strip()}")
        except (subprocess.TimeoutExpired, OSError):
            pass
        return True
    print(f"Binary not found: {binary_path}")
    print("Run 'python scripts/pss_build.py' to build it")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build PSS Rust binary for Claude Code plugin"
    )
    parser.add_argument(
        "--release",
        action="store_true",
        default=True,
        help="Build optimized release binary (default)",
    )
    parser.add_argument("--debug", action="store_true", help="Build debug binary")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Build for all supported platforms (requires cross)",
    )
    parser.add_argument(
        "--target",
        choices=list(TARGETS.keys()),
        help="Build for specific target platform",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if binary exists for current platform",
    )
    parser.add_argument(
        "--list-targets", action="store_true", help="List all supported build targets"
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
        return 1  # check_rust_installed already prints detailed error

    release = not args.debug

    # Handle --all (requires cross for non-WASM targets)
    if args.all:
        if not check_cross_installed():
            print(
                "Error: 'cross' is required for --all (except WASM).", file=sys.stderr
            )
            return 1

        success = True
        for target in TARGETS:
            if target == "wasm32":
                if not build_wasm(release):
                    success = False
            else:
                if not build_cross(target, release):
                    success = False

        return 0 if success else 1

    # Handle --target (WASM uses cargo directly, others may need cross)
    if args.target:
        if args.target == "wasm32":
            return 0 if build_wasm(release) else 1

        system, machine = detect_platform()
        native_target = f"{system}-{machine}"

        if args.target == native_target:
            return 0 if build_native(release) else 1
        if not check_cross_installed():
            print(
                f"Error: 'cross' is required to build for {args.target} (non-native target).",
                file=sys.stderr,
            )
            print(
                "Install: cargo install cross --git https://github.com/cross-rs/cross",
                file=sys.stderr,
            )
            print("Requires: Docker running", file=sys.stderr)
            return 1
        return 0 if build_cross(args.target, release) else 1

    # Default: build for current platform
    return 0 if build_native(release) else 1


if __name__ == "__main__":
    sys.exit(main())
