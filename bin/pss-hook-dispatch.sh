#!/bin/sh
# PSS hook dispatch shim — PERF-1 (audit 20260514).
#
# Replaces the legacy `uv run --quiet --script pss_hook.py` invocation in
# hooks.json for UserPromptSubmit. The Python wrapper added ~130 ms of pure
# startup overhead per prompt (uv resolve + Python startup + pycozo import +
# subprocess fork to call the native binary). This shim is plain POSIX sh,
# adds ~3 ms of startup, and exec's the right native binary directly.
#
# SessionStart still uses pss_hook.py because that path spawns the
# background reindex when the DB is missing — that's a one-time cost where
# startup latency isn't critical. The hot UserPromptSubmit path is what
# needs to be fast.
#
# The native binary handles missing-DB gracefully (returns empty HookOutput,
# no error). Auto-reindex runs from SessionStart, so by the time prompts
# start arriving the DB is populated.

set -eu

# ──────────────────────────────────────────────────────────────────────────
# Platform / arch detection — mirrors scripts/pss_hook.py:detect_platform()
# ──────────────────────────────────────────────────────────────────────────
SYSTEM="$(uname -s 2>/dev/null || echo unknown)"
MACHINE="$(uname -m 2>/dev/null || echo unknown)"

# Normalize architecture names
case "$MACHINE" in
    aarch64) MACHINE="arm64" ;;
    amd64)   MACHINE="x86_64" ;;
esac

case "$SYSTEM" in
    Darwin)
        case "$MACHINE" in
            arm64)  BIN_NAME="pss-darwin-arm64" ;;
            x86_64) BIN_NAME="pss-darwin-x86_64" ;;
            *)      BIN_NAME="" ;;
        esac
        ;;
    Linux)
        # Detect Android/Termux — reports as linux arm64 but uses linux-arm64 binary
        case "$MACHINE" in
            arm64)  BIN_NAME="pss-linux-arm64" ;;
            x86_64) BIN_NAME="pss-linux-x86_64" ;;
            *)      BIN_NAME="" ;;
        esac
        ;;
    MINGW*|MSYS*|CYGWIN*|Windows*)
        BIN_NAME="pss-windows-x86_64.exe"
        ;;
    *)
        BIN_NAME=""
        ;;
esac

# ──────────────────────────────────────────────────────────────────────────
# Resolve binary path. CC sets CLAUDE_PLUGIN_ROOT to the plugin install dir.
# When testing locally without that env var, fall back to the script's own
# directory (so `./bin/pss-hook-dispatch.sh` works in development).
# ──────────────────────────────────────────────────────────────────────────
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    BIN_DIR="$CLAUDE_PLUGIN_ROOT/bin"
else
    # POSIX-portable $0 dirname (handles symlinks via cd+pwd if available)
    SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd || dirname "$0")"
    BIN_DIR="$SCRIPT_DIR"
fi

# Empty BIN_NAME means unsupported platform → emit empty hook output and exit
# 0 so the user's session doesn't break.
if [ -z "$BIN_NAME" ] || [ ! -x "$BIN_DIR/$BIN_NAME" ]; then
    printf '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":""}}\n'
    exit 0
fi

# ──────────────────────────────────────────────────────────────────────────
# Exec the native binary. Args mirror pss_hook.py's `argv` (line 823):
#   --format hook   pretty hook-format output (skills only, not full result)
#   --top 5         cap at 5 suggestions (= MAX_SUGGESTIONS)
#   --min-score 0.5 filter low-confidence matches (= MIN_SCORE)
# stdin is passed through unchanged — the binary parses HookInput itself.
# ──────────────────────────────────────────────────────────────────────────
exec "$BIN_DIR/$BIN_NAME" --format hook --top 5 --min-score 0.5
