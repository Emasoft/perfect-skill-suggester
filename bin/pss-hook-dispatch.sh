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
# Resolve binary path. Search order (TRDD-YC51I1C0 phase 3 — the fetched
# store now WINS over the plugin/repo copy):
#   1. $PSS_BINARY_DIR          operator escape hatch
#   2. ~/.claude/cache/pss-bin/current   the fetched store — a CONSTANT path,
#      deliberately not CLAUDE_PLUGIN_DATA-derived: sh cannot mirror the
#      Python get_data_dir() conditional without a 3rd copy of a rule that
#      has already drifted once. The fetcher writes to this same constant.
#   3. $CLAUDE_PLUGIN_ROOT/bin  the plugin install — transitional: a fresh
#      install has nothing here, so the store above is what users hit
#   4. the script's own dir     local dev fallback (repo bin/)
# stat only — this shim must NEVER fetch (hot path, ~3 ms budget).
# ──────────────────────────────────────────────────────────────────────────
# [ -n "$BIN_NAME" ] is load-bearing: on an unsupported platform BIN_NAME is
# empty, and `[ -x "$PSS_BINARY_DIR/"` is true for any searchable directory —
# exec'ing it would exit 126 and break the session (review fork 2026-09-28).
# The same guard protects the store early-exec below.
if [ -n "$BIN_NAME" ] && [ -n "${PSS_BINARY_DIR:-}" ] && [ -x "$PSS_BINARY_DIR/$BIN_NAME" ]; then
    exec "$PSS_BINARY_DIR/$BIN_NAME" --format hook --top 5 --min-score 0.5
fi

# 2. The fetched store — phase 3 flip: it now beats the plugin/repo copy.
if [ -n "$BIN_NAME" ] && [ -x "$HOME/.claude/cache/pss-bin/current/$BIN_NAME" ]; then
    exec "$HOME/.claude/cache/pss-bin/current/$BIN_NAME" --format hook --top 5 --min-score 0.5
fi

if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    BIN_DIR="$CLAUDE_PLUGIN_ROOT/bin"
else
    # POSIX-portable $0 dirname. shellcheck SC2015: explicit if/else instead
    # of `cd && pwd || dirname $0` so we never silently fall through to
    # `dirname` when `cd` succeeded but `pwd` failed (extremely unlikely
    # but the linter is right that the && || pattern isn't a clean
    # if-then-else).
    SCRIPT_DIR=""
    if cd "$(dirname "$0")" 2>/dev/null; then
        SCRIPT_DIR="$(pwd)"
    fi
    if [ -z "$SCRIPT_DIR" ]; then
        SCRIPT_DIR="$(dirname "$0")"
    fi
    BIN_DIR="$SCRIPT_DIR"
fi

if [ -n "$BIN_NAME" ] && [ -x "$BIN_DIR/$BIN_NAME" ]; then
    :
else
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
