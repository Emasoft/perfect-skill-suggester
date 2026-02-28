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
    "wasm32": "wasm32-wasip1",
}

# Darwin targets must use cargo directly (cross has no macOS Docker images)
DARWIN_TARGETS = {"darwin-arm64", "darwin-x86_64"}


def resolve_cargo() -> str:
    """Resolve cargo path, preferring rustup over Homebrew.

    Homebrew's cargo cannot cross-compile (no rustup target support).
    When Homebrew cargo is detected, use rustup's cargo directly and
    also set RUSTC env var so cargo invokes rustup's rustc (not Homebrew's).
    """
    import os

    cargo_path = shutil.which("cargo")
    if cargo_path and "/homebrew/" in cargo_path.lower():
        # Homebrew cargo detected — use rustup's cargo + rustc directly
        rustup_cargo = Path.home() / ".rustup/toolchains/stable-aarch64-apple-darwin/bin/cargo"
        rustup_rustc = Path.home() / ".rustup/toolchains/stable-aarch64-apple-darwin/bin/rustc"
        if rustup_cargo.exists():
            print("  Note: Using rustup cargo (Homebrew cargo in PATH lacks cross targets)")
            # CRITICAL: also set RUSTC so cargo uses rustup's rustc, not Homebrew's
            if rustup_rustc.exists():
                os.environ["RUSTC"] = str(rustup_rustc)
            return str(rustup_cargo)
        # Try finding any stable toolchain
        rustup_dir = Path.home() / ".rustup/toolchains"
        if rustup_dir.exists():
            for toolchain in sorted(rustup_dir.iterdir()):
                candidate = toolchain / "bin" / "cargo"
                candidate_rustc = toolchain / "bin" / "rustc"
                if candidate.exists() and "stable" in toolchain.name:
                    print(f"  Note: Using rustup cargo from {toolchain.name}")
                    if candidate_rustc.exists():
                        os.environ["RUSTC"] = str(candidate_rustc)
                    return str(candidate)
        print(
            "Warning: Homebrew cargo detected but no rustup toolchain found.",
            file=sys.stderr,
        )
    return "cargo"


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
                "Fix: Run 'source $HOME/.cargo/env'"
                " or add $HOME/.cargo/bin to your PATH.",
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

    # Build command (use rustup's cargo to avoid Homebrew conflicts)
    cargo = resolve_cargo()
    cmd = [cargo, "build"]
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
            "Error: 'rustup' not found."
            " WASM builds require rustup (not Homebrew Rust).",
            file=sys.stderr,
        )
        print(
            "Install: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh",
            file=sys.stderr,
        )
        return False

    bin_dir.mkdir(parents=True, exist_ok=True)

    # Use rustup's cargo for WASM builds (Homebrew cargo may lack targets)
    cargo = resolve_cargo()
    cmd = [cargo, "build", "--target", rust_target]
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
            "  2. Code uses platform-specific APIs"
            ' not gated with #[cfg(not(target_arch = "wasm32"))]',
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


def build_darwin_cross(target_key: str, release: bool = True) -> bool:
    """Build for a darwin target using cargo directly (cross can't do macOS)."""
    if target_key not in DARWIN_TARGETS:
        print(f"Error: {target_key} is not a darwin target", file=sys.stderr)
        return False

    rust_target = TARGETS[target_key]
    rust_dir = get_rust_dir()
    bin_dir = get_bin_dir()
    cargo = resolve_cargo()

    # Ensure the target is installed via rustup
    try:
        check_result = subprocess.run(
            ["rustup", "target", "list", "--installed"],
            capture_output=True, text=True, timeout=10,
        )
        if rust_target not in check_result.stdout:
            print(f"Installing Rust target: {rust_target}")
            subprocess.run(
                ["rustup", "target", "add", rust_target],
                timeout=60,
            )
    except FileNotFoundError:
        print("Error: rustup not found. Darwin cross-compilation requires rustup.", file=sys.stderr)
        return False

    bin_dir.mkdir(parents=True, exist_ok=True)

    cmd = [cargo, "build", "--target", rust_target]
    if release:
        cmd.append("--release")

    print(f"Building for {target_key} ({rust_target}) via cargo...")
    print(f"  Directory: {rust_dir}")
    print(f"  Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=rust_dir, timeout=300)

    if result.returncode != 0:
        print(f"Error: Darwin cross-build failed for {target_key}.", file=sys.stderr)
        return False

    # Copy binary to bin directory
    system, machine = target_key.split("-")
    binary_name = get_binary_name(system, machine)
    target_subdir = "release" if release else "debug"
    source = rust_dir / "target" / rust_target / target_subdir / "pss"
    dest = bin_dir / binary_name

    if source.exists():
        shutil.copy2(source, dest)
        dest.chmod(0o755)
        print(f"Binary installed: {dest}")
        return True
    print(f"Error: Built binary not found at {source}", file=sys.stderr)
    return False


def build_zigbuild(target_key: str, release: bool = True) -> bool:
    """Build for a specific target using cargo-zigbuild (no Docker needed)."""
    if target_key not in TARGETS:
        print(f"Error: Unknown target '{target_key}'", file=sys.stderr)
        return False

    rust_target = TARGETS[target_key]
    rust_dir = get_rust_dir()
    bin_dir = get_bin_dir()
    cargo = resolve_cargo()

    # Ensure the target stdlib is installed via rustup
    try:
        check_result = subprocess.run(
            ["rustup", "target", "list", "--installed"],
            capture_output=True, text=True, timeout=10,
        )
        if rust_target not in check_result.stdout:
            print(f"  Installing Rust target: {rust_target}")
            subprocess.run(["rustup", "target", "add", rust_target], timeout=60)
    except FileNotFoundError:
        print("Error: rustup not found. zigbuild requires rustup.", file=sys.stderr)
        return False

    zigbuild = shutil.which("cargo-zigbuild")
    if not zigbuild:
        print("Error: cargo-zigbuild not found. Install: cargo install cargo-zigbuild", file=sys.stderr)
        return False

    bin_dir.mkdir(parents=True, exist_ok=True)

    cmd = [zigbuild, "build", "--release" if release else "", "--target", rust_target]
    cmd = [c for c in cmd if c]  # remove empty strings

    print(f"Building for {target_key} ({rust_target}) via zigbuild...")
    result = subprocess.run(cmd, cwd=rust_dir, timeout=300)

    if result.returncode != 0:
        print(f"Error: zigbuild failed for {target_key}.", file=sys.stderr)
        return False

    # Copy binary to bin directory
    system, machine = target_key.split("-")
    binary_name = get_binary_name(system, machine)
    target_subdir = "release" if release else "debug"
    source = rust_dir / "target" / rust_target / target_subdir / "pss"
    if "windows" in target_key:
        source = source.with_suffix(".exe")
    dest = bin_dir / binary_name

    if source.exists():
        shutil.copy2(source, dest)
        dest.chmod(0o755)
        print(f"Binary installed: {dest}")
        return True
    print(f"Error: Built binary not found at {source}", file=sys.stderr)
    return False


def build_cross(target_key: str, release: bool = True) -> bool:
    """Build for a specific target using cross (Docker-based).

    Falls back to cargo-zigbuild if cross fails.
    """
    if target_key not in TARGETS:
        print(f"Error: Unknown target '{target_key}'", file=sys.stderr)
        print(f"Available targets: {', '.join(TARGETS.keys())}")
        return False

    rust_target = TARGETS[target_key]
    rust_dir = get_rust_dir()
    bin_dir = get_bin_dir()

    # Ensure rustup's toolchain is visible to cross (Homebrew breaks it)
    import os
    rustup_bin = Path.home() / ".rustup/toolchains/stable-aarch64-apple-darwin/bin"
    cargo_bin = Path.home() / ".cargo/bin"
    env = os.environ.copy()
    env["PATH"] = f"{rustup_bin}:{cargo_bin}:{env.get('PATH', '')}"

    # Build command
    cmd = ["cross", "build", "--target", rust_target]
    if release:
        cmd.append("--release")

    print(f"Cross-compiling for {target_key} ({rust_target})...")
    result = subprocess.run(cmd, cwd=rust_dir, timeout=600, env=env)

    if result.returncode != 0:
        # Fallback to zigbuild if cross fails (common on Apple Silicon for arm64 targets)
        print(f"  cross failed for {target_key}, trying zigbuild fallback...", file=sys.stderr)
        return build_zigbuild(target_key, release)

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

    # Handle --all (darwin via cargo, linux/windows via cross, wasm via cargo)
    if args.all:
        system, machine = detect_platform()
        native_target = f"{system}-{machine}"

        # cross is needed for linux/windows targets
        non_darwin_non_wasm = [t for t in TARGETS if t not in DARWIN_TARGETS and t != "wasm32"]
        if non_darwin_non_wasm and not check_cross_installed():
            print(
                "Error: 'cross' is required for linux/windows targets.", file=sys.stderr
            )
            return 1

        success = True
        for target in TARGETS:
            if target == "wasm32":
                if not build_wasm(release):
                    success = False
            elif target in DARWIN_TARGETS:
                # Native target uses cargo build, cross-darwin uses cargo --target
                if target == native_target:
                    if not build_native(release):
                        success = False
                else:
                    if not build_darwin_cross(target, release):
                        success = False
            else:
                # Linux/Windows targets use cross (Docker-based)
                if not build_cross(target, release):
                    success = False

        return 0 if success else 1

    # Handle --target (WASM via cargo, darwin via cargo, linux/windows via cross)
    if args.target:
        if args.target == "wasm32":
            return 0 if build_wasm(release) else 1

        system, machine = detect_platform()
        native_target = f"{system}-{machine}"

        if args.target == native_target:
            return 0 if build_native(release) else 1

        # Darwin cross-compilation uses cargo directly (no Docker needed)
        if args.target in DARWIN_TARGETS:
            return 0 if build_darwin_cross(args.target, release) else 1

        # Linux/Windows targets require cross (Docker-based)
        if not check_cross_installed():
            print(
                f"Error: 'cross' is required to build for"
                f" {args.target} (non-native target).",
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
