#!/usr/bin/env python3
"""PSS Paths — Canonical path resolution for plugin data and Claude's user directory.

All PSS scripts must use these functions instead of hardcoding ~/.claude.

Priority order for data storage:
  1. $CLAUDE_PLUGIN_DATA — but ONLY if it is scoped to PSS itself
     (CC sets this env var to the invoking plugin's data dir — when the
     user runs /pss-reindex-skills from a session that has a different
     plugin's context loaded, $CLAUDE_PLUGIN_DATA leaks through to PSS
     and points at the wrong directory). CC v2.1.78+.
  2. $HOME/.claude/cache   — deterministic legacy fallback used by the hook
"""

import os
from pathlib import Path

# Name fragment that identifies PSS's own plugin data directory. CC composes
# the directory as ~/.claude/plugins/data/<plugin-identifier>/ where
# plugin-identifier embeds the plugin name. Treating $CLAUDE_PLUGIN_DATA as
# trusted only when the basename matches avoids writing PSS state into
# another plugin's scope. Verified 2026-04-16: the bug that prompted this
# check dropped 1,641 elements (including a just-installed tailwind-4-docs
# skill) into codex-openai-codex/skill-index.json instead of PSS's cache.
_PSS_PLUGIN_MARKER = "perfect-skill-suggester"


def get_claude_config_dir() -> Path:
    """Get Claude's config directory ($HOME/.claude)."""
    return Path.home() / ".claude"


def get_data_dir() -> Path:
    """Get the PSS data directory for persistent state (DB, index, locks).

    Uses $CLAUDE_PLUGIN_DATA (CC v2.1.78+) ONLY when it is scoped to PSS —
    verified by checking the basename contains "perfect-skill-suggester".
    If the env var is unset, empty, non-absolute, or points at a foreign
    plugin's data dir, falls back to ~/.claude/cache — which is the path
    that scripts/pss_hook.py uses at runtime when $CLAUDE_PLUGIN_DATA is
    not PSS-scoped (the same guard runs there).
    """
    plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA", "").strip()
    if plugin_data and Path(plugin_data).is_absolute():
        # Only trust $CLAUDE_PLUGIN_DATA when it is scoped to PSS itself.
        # CC populates this env var with the invoking plugin's data dir —
        # during a /pss-reindex-skills call triggered from another plugin's
        # session context, the variable leaks and would cause PSS to write
        # its index into a foreign plugin's directory, invisible to the
        # hook. Matching on the plugin-name marker restores the invariant
        # that read-path and write-path resolve to the same directory.
        if _PSS_PLUGIN_MARKER in Path(plugin_data).name.lower():
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
