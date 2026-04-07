#!/usr/bin/env python3
"""PSS Paths — Canonical path resolution for plugin data and Claude's user directory.

All PSS scripts must use these functions instead of hardcoding ~/.claude.

Priority order for data storage:
  1. $CLAUDE_PLUGIN_DATA — persistent plugin data dir (survives plugin updates, CC v2.1.78+)
  2. $HOME/.claude/cache   — legacy fallback
"""

import os
from pathlib import Path


def get_claude_config_dir() -> Path:
    """Get Claude's config directory ($HOME/.claude)."""
    return Path.home() / ".claude"


def get_data_dir() -> Path:
    """Get the PSS data directory for persistent state (DB, index, locks).

    Prefers $CLAUDE_PLUGIN_DATA (CC v2.1.78+) which survives plugin updates.
    Falls back to ~/.claude/cache for older CC versions or non-plugin contexts.
    """
    plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA", "").strip()
    if plugin_data and Path(plugin_data).is_absolute():
        d = Path(plugin_data)
        d.mkdir(parents=True, exist_ok=True)
        return d
    fallback = get_claude_config_dir() / "cache"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def get_cache_dir() -> Path:
    """Get the PSS cache directory — alias for get_data_dir()."""
    return get_data_dir()


def get_index_path() -> Path:
    """Get the canonical path to skill-index.json."""
    return get_data_dir() / "skill-index.json"


def get_lock_path() -> Path:
    """Get the canonical path to skill-index.lock."""
    return get_data_dir() / "skill-index.lock"
