#!/usr/bin/env python3
"""
PSS Hook Script - Multiplatform binary caller for Perfect Skill Suggester
Replaces hook.sh and hook.ps1 with unified Python implementation
"""

import json
import platform
import subprocess
import sys
from pathlib import Path


def detect_platform():
    """Detect platform and architecture, return binary name."""
    system = platform.system().lower()
    machine = platform.machine().lower()

    # Normalize architecture names
    if machine in ('aarch64',):
        machine = 'arm64'
    elif machine in ('amd64',):
        machine = 'x86_64'

    # Map to binary names
    if system == 'darwin':
        if machine == 'arm64':
            return 'pss-darwin-arm64'
        elif machine == 'x86_64':
            return 'pss-darwin-x86_64'
    elif system == 'linux':
        if machine == 'arm64':
            return 'pss-linux-arm64'
        elif machine == 'x86_64':
            return 'pss-linux-x86_64'
    elif system == 'windows':
        # Windows is typically x86_64
        return 'pss-windows-x86_64.exe'

    # Unsupported platform
    raise RuntimeError(f"Unsupported platform: {system} {machine}")


def find_binary():
    """Locate the PSS binary relative to this script."""
    # This script is in: OUTPUT_SKILLS/perfect-skill-suggester/scripts/pss_hook.py
    # Binary is in: OUTPUT_SKILLS/perfect-skill-suggester/rust/skill-suggester/bin/
    script_dir = Path(__file__).parent.resolve()
    binary_name = detect_platform()
    binary_path = script_dir.parent / "rust" / "skill-suggester" / "bin" / binary_name

    if not binary_path.exists():
        raise FileNotFoundError(f"Binary not found: {binary_path}")

    return binary_path


def main():
    """Main entry point - read stdin, call binary, output result."""
    try:
        # Read JSON input from stdin
        stdin_data = sys.stdin.read()

        # Find the binary
        binary_path = find_binary()

        # Call the binary with --format hook
        result = subprocess.run(
            [str(binary_path), "--format", "hook"],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout
        )

        # Output the result
        if result.returncode == 0:
            print(result.stdout, end='')
        else:
            # On error, log to stderr and return empty JSON to stdout
            msg = f"PSS binary error (exit {result.returncode}): {result.stderr}"
            print(msg, file=sys.stderr)
            print(json.dumps({}))

        sys.exit(0)  # Always exit 0 to not block Claude

    except Exception as e:
        # On any error, log to stderr and return empty JSON to stdout
        print(f"PSS hook error: {e}", file=sys.stderr)
        print(json.dumps({}))
        sys.exit(0)


if __name__ == "__main__":
    main()
