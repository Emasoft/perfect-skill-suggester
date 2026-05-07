#!/usr/bin/env bash
# Janitor detector — emits one drift line if the PSS temporal index has
# not been reindexed within $PSS_REINDEX_INTERVAL (default 24h).
#
# Wired by the ai-maestro-janitor plugin: dispatch.sh iterates every
# script under detectors/ and surfaces stdout verbatim.
#
# Output contract:
#   - Empty stdout when fresh -> silent
#   - One line on drift, prefixed with "[pss-reindex-due]"
#
# This script is intentionally Bash + jq only — no Python, no Rust binary
# call beyond the `pss db-stats` JSON probe. Fast, zero deps beyond
# what every Claude Code user already has.
#
# See design/tasks/TRDD-152e697f-*.md §10 for the full spec.

set -euo pipefail

# Allow override via env var; default 24h (86400 seconds).
INTERVAL_SEC="${PSS_REINDEX_INTERVAL:-86400}"

# Resolve the pss binary. Prefer ${CLAUDE_PLUGIN_ROOT}/bin/<platform>/pss
# (when invoked from the plugin) otherwise fall back to PATH.
PSS_BIN="${PSS_BIN:-pss}"
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -d "${CLAUDE_PLUGIN_ROOT}/bin" ]; then
  uname_s="$(uname -s)"
  uname_m="$(uname -m)"
  case "$uname_s-$uname_m" in
    Darwin-arm64)   bin="${CLAUDE_PLUGIN_ROOT}/bin/pss-darwin-arm64" ;;
    Darwin-x86_64)  bin="${CLAUDE_PLUGIN_ROOT}/bin/pss-darwin-x86_64" ;;
    Linux-x86_64)   bin="${CLAUDE_PLUGIN_ROOT}/bin/pss-linux-x86_64" ;;
    Linux-aarch64)  bin="${CLAUDE_PLUGIN_ROOT}/bin/pss-linux-arm64" ;;
    *)              bin="" ;;
  esac
  if [ -n "$bin" ] && [ -x "$bin" ]; then
    PSS_BIN="$bin"
  fi
fi

# Probe the DB. If the binary isn't available, exit silent — not our
# problem to surface at this layer.
if ! command -v "$PSS_BIN" >/dev/null 2>&1 && [ ! -x "$PSS_BIN" ]; then
  exit 0
fi

# Pull the most-recent scan_runs.finished_at via `pss scan-log`. Empty
# array means no reindex has ever happened — emit a "first run" hint.
last_finished_at="$("$PSS_BIN" scan-log --limit 1 2>/dev/null \
  | jq -r 'if length == 0 then "" else .[0].finished_at end' 2>/dev/null \
  || echo "")"

if [ -z "$last_finished_at" ] || [ "$last_finished_at" = "null" ]; then
  echo "[pss-reindex-due] PSS temporal index has never been reindexed. Run \`pss reindex\` to seed it."
  exit 0
fi

# Convert RFC3339 → epoch via `date -d` (GNU) / `date -j -f` (BSD/macOS).
to_epoch() {
  if date -d "$1" +%s >/dev/null 2>&1; then
    date -d "$1" +%s
  else
    # macOS: try parsing as ISO 8601 with optional fractional seconds.
    # Strip fractional seconds and timezone suffix if needed.
    local clean="${1%%.*}"
    case "$clean" in
      *Z) clean="${clean%Z}+0000" ;;
    esac
    date -j -u -f "%Y-%m-%dT%H:%M:%S%z" "$clean" +%s 2>/dev/null \
      || date -j -u -f "%Y-%m-%dT%H:%M:%S" "${clean%%+*}" +%s 2>/dev/null \
      || echo "0"
  fi
}

last_epoch="$(to_epoch "$last_finished_at")"
now_epoch="$(date +%s)"

# Emit nothing (silent) if last_epoch is bogus (0). Don't pester user.
if [ "$last_epoch" = "0" ]; then
  exit 0
fi

age_sec="$((now_epoch - last_epoch))"

if [ "$age_sec" -ge "$INTERVAL_SEC" ]; then
  age_h="$((age_sec / 3600))"
  echo "[pss-reindex-due] PSS temporal index last reindexed ${age_h}h ago (>${INTERVAL_SEC}s threshold). Run \`pss reindex\` to refresh."
fi

exit 0
