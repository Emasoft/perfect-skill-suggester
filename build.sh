#!/usr/bin/env bash
# Build script wrapper required by the CPV (Claude Plugins Validation) standard,
# which scans for canonical names (build.sh / install.sh / Makefile) when a
# plugin ships Rust sources. The real build pipeline lives in
# scripts/pss_build.py (multi-target cross-compilation, cargo-zigbuild fallback,
# Docker-cross integration). This wrapper just delegates.
#
# Usage:
#   ./build.sh                     # native target (darwin-arm64 by default)
#   ./build.sh --all               # all 5 release targets
#   ./build.sh --target linux-x86_64
#
# See scripts/pss_build.py --help for the full option set.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec uv run --script "${SCRIPT_DIR}/scripts/pss_build.py" "$@"
