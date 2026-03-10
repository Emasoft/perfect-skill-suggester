#!/usr/bin/env python3
"""PSS Paths — Canonical path resolution for Claude's user directory.

All PSS scripts must use these functions instead of hardcoding ~/.claude.
Single source of truth: $HOME/.claude/
"""

from pathlib import Path


def get_claude_config_dir() -> Path:
    """Get Claude's config directory ($HOME/.claude)."""
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
