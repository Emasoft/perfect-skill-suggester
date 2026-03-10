"""PSS Paths — Canonical path resolution for Claude config directory.

All PSS scripts must use these functions instead of hardcoding ~/.claude.
Respects CLAUDE_CONFIG_DIR and XDG_CONFIG_HOME (matching Claude Code's behavior).
"""

import os
from pathlib import Path


def get_claude_config_dir() -> Path:
    """Resolve Claude's config directory.

    Resolution order (matches Claude Code's own behavior):
      1. CLAUDE_CONFIG_DIR env var (explicit override)
      2. XDG_CONFIG_HOME/claude (XDG standard, mainly Linux)
      3. ~/.claude (default)
    """
    env_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if env_dir:
        return Path(env_dir)
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_home:
        return Path(xdg_home) / "claude"
    return Path.home() / ".claude"


def get_cache_dir() -> Path:
    """Get the PSS cache directory (for skill-index.json, .db, etc.)."""
    return get_claude_config_dir() / "cache"


def get_index_path() -> Path:
    """Get the canonical path to skill-index.json."""
    return get_cache_dir() / "skill-index.json"


def get_lock_path() -> Path:
    """Get the canonical path to skill-index.lock."""
    return get_cache_dir() / "skill-index.lock"
