#!/usr/bin/env python3
"""Build all PSS + pss-nlp binaries for all platforms.

Outputs only a summary table. Full build logs go to a timestamped file.
Designed to be called by orchestrator agents with minimal context cost.

Usage:
    uv run scripts/pss_build_all.py              # All binaries, all platforms
    uv run scripts/pss_build_all.py --pss-only   # Only PSS binary
    uv run scripts/pss_build_all.py --nlp-only   # Only pss-nlp binary
    uv run scripts/pss_build_all.py --native     # Only native (darwin-arm64)
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from io import TextIOWrapper
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
PSS_RUST_DIR = REPO_ROOT / "rust" / "skill-suggester"
NLP_RUST_DIR = REPO_ROOT / "rust" / "negation-detector"
BIN_DIR = REPO_ROOT / "bin"
LOG_DIR = REPO_ROOT / "builds_dev"

# ── Targets ────────────────────────────────────────────────────────────────
TARGETS = {
    "darwin-arm64": {"triple": "aarch64-apple-darwin", "tool": "cargo"},
    "darwin-x86_64": {"triple": "x86_64-apple-darwin", "tool": "cargo-cross"},
    "linux-x86_64": {"triple": "x86_64-unknown-linux-musl", "tool": "zigbuild"},
    "linux-arm64": {"triple": "aarch64-unknown-linux-musl", "tool": "zigbuild"},
    "windows-x86_64": {"triple": "x86_64-pc-windows-gnu", "tool": "cross"},
}

# Binary name mapping: (crate_dir, binary_name, output_prefix)
BINARIES = {
    "pss": (PSS_RUST_DIR, "pss", "pss"),
    "pss-nlp": (NLP_RUST_DIR, "pss-nlp", "pss-nlp"),
}


def _has_tool(name: str) -> bool:
    """Check if a CLI tool is on PATH (cross-platform)."""
    return shutil.which(name) is not None


def _docker_running() -> bool:
    """Check if Docker daemon is responsive."""
    try:
        return subprocess.run(
            ["docker", "info"], capture_output=True, timeout=10
        ).returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _build_one(
    crate_dir: Path,
    target_name: str,
    triple: str,
    tool: str,
    log_fh: TextIOWrapper,
) -> tuple[bool, str]:
    """Build a single binary for a single target. Returns (success, error_msg)."""

    if target_name == "darwin-arm64":
        # Native build — no --target flag needed
        cmd = ["cargo", "build", "--release"]
    elif tool == "cargo-cross":
        # Darwin cross (same host OS, different arch)
        cmd = ["cargo", "build", "--release", "--target", triple]
    elif tool == "zigbuild":
        if not _has_tool("cargo-zigbuild"):
            return False, "cargo-zigbuild not installed"
        cmd = ["cargo", "zigbuild", "--release", "--target", triple]
    elif tool == "cross":
        if not _has_tool("cross"):
            # Fallback to zigbuild for cross targets if Docker unavailable
            if _has_tool("cargo-zigbuild") and "windows" not in triple:
                cmd = ["cargo", "zigbuild", "--release", "--target", triple]
                tool = "zigbuild-fallback"
            else:
                return False, "cross not installed and no zigbuild fallback"
        elif not _docker_running():
            if _has_tool("cargo-zigbuild") and "windows" not in triple:
                cmd = ["cargo", "zigbuild", "--release", "--target", triple]
                tool = "zigbuild-fallback"
            else:
                return False, "Docker not running and no zigbuild fallback"
        else:
            cmd = ["cross", "build", "--release", "--target", triple]
    else:
        return False, f"Unknown tool: {tool}"

    log_fh.write(f"\n{'=' * 60}\n")
    log_fh.write(f"CMD: {' '.join(cmd)}\n")
    log_fh.write(f"CWD: {crate_dir}\n")
    log_fh.write(f"{'=' * 60}\n")
    log_fh.flush()

    # Apple Silicon hosts must force Docker to pull linux/amd64 images for
    # cross's x86_64 containers. Without this, Docker reports
    # "no matching manifest for linux/arm64/v8" and the build fails on
    # Apple Silicon. Applies cleanly to non-ARM hosts too (ignored).
    env = os.environ.copy()
    env.setdefault("DOCKER_DEFAULT_PLATFORM", "linux/amd64")

    try:
        # 30-minute timeout — accommodates Docker image pulls and
        # nlprule_build model downloads inside the cross container.
        result = subprocess.run(
            cmd,
            cwd=crate_dir,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            timeout=1800,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return False, "build timed out after 1800s"

    if result.returncode != 0:
        return False, f"exit code {result.returncode} (tool={tool})"
    return True, ""


def _copy_binary(
    crate_dir: Path,
    binary_name: str,
    output_prefix: str,
    target_name: str,
    triple: str,
) -> Path | None:
    """Copy built binary to bin/ with platform-specific name. Returns dest path."""
    # Cargo workspace puts binaries under workspace root target/, not crate target/
    workspace_root = crate_dir.parent
    if target_name == "darwin-arm64":
        src = workspace_root / "target" / "release" / binary_name
        if not src.exists():
            src = crate_dir / "target" / "release" / binary_name
    else:
        ext = ".exe" if "windows" in triple else ""
        src = workspace_root / "target" / triple / "release" / (binary_name + ext)
        if not src.exists():
            src = crate_dir / "target" / triple / "release" / (binary_name + ext)

    if not src.exists():
        return None

    ext = ".exe" if "windows" in triple else ""
    dest = BIN_DIR / f"{output_prefix}-{target_name}{ext}"
    shutil.copy2(src, dest)
    try:
        os.chmod(dest, 0o755)
    except OSError:
        pass  # chmod not supported on all platforms
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build all PSS binaries")
    parser.add_argument("--pss-only", action="store_true", help="Only build PSS")
    parser.add_argument("--nlp-only", action="store_true", help="Only build pss-nlp")
    parser.add_argument("--native", action="store_true", help="Only darwin-arm64")
    args = parser.parse_args()

    # Determine what to build
    if args.pss_only:
        binaries = {"pss": BINARIES["pss"]}
    elif args.nlp_only:
        binaries = {"pss-nlp": BINARIES["pss-nlp"]}
    else:
        binaries = BINARIES

    if args.native:
        targets = {"darwin-arm64": TARGETS["darwin-arm64"]}
    else:
        targets = TARGETS

    # Setup log file
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"build-{timestamp}.log"

    BIN_DIR.mkdir(parents=True, exist_ok=True)

    results: list[tuple[str, str, bool, str, float, str]] = []
    total_start = time.time()

    with open(log_path, "w") as log_fh:
        log_fh.write(f"PSS Build Log — {datetime.now().isoformat()}\n")
        log_fh.write(f"Binaries: {list(binaries.keys())}\n")
        log_fh.write(f"Targets: {list(targets.keys())}\n\n")

        for bin_key, (crate_dir, binary_name, output_prefix) in binaries.items():
            for tgt_name, tgt_info in targets.items():
                triple = tgt_info["triple"]
                tool = tgt_info["tool"]
                t0 = time.time()

                log_fh.write(
                    f"\n>>> Building {bin_key} for {tgt_name} ({triple}) via {tool}\n"
                )
                log_fh.flush()

                ok, err = _build_one(crate_dir, tgt_name, triple, tool, log_fh)
                elapsed = time.time() - t0

                dest_str = ""
                if ok:
                    dest = _copy_binary(
                        crate_dir, binary_name, output_prefix, tgt_name, triple
                    )
                    if dest:
                        dest_str = dest.name
                    else:
                        ok = False
                        err = "binary not found after build"

                results.append((bin_key, tgt_name, ok, err, elapsed, dest_str))

    # ── Summary output (this is ALL the orchestrator sees) ─────────────
    total_elapsed = time.time() - total_start
    passed = sum(1 for r in results if r[2])
    failed = len(results) - passed

    # Header
    print(
        f"\n{'Binary':<10} {'Platform':<18} {'Status':<8} {'Time':>6}  {'Output / Error'}"
    )
    print(f"{'─' * 10} {'─' * 18} {'─' * 8} {'─' * 6}  {'─' * 30}")

    for bin_key, tgt_name, ok, err, elapsed, dest_str in results:
        status = "OK" if ok else "FAIL"
        detail = dest_str if ok else err
        print(f"{bin_key:<10} {tgt_name:<18} {status:<8} {elapsed:5.0f}s  {detail}")

    print(
        f"\n{passed}/{len(results)} succeeded in {total_elapsed:.0f}s — log: {log_path}"
    )

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
