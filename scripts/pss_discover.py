#!/usr/bin/env python3
"""
Perfect Skill Suggester - Element Discovery Script.

Find ALL Claude Code elements (skills, agents, commands, rules, MCP servers,
LSP servers) available across ALL projects.

This script discovers element locations from:
- User-level elements (~/.claude/{skills,agents,commands,rules}/)
- All projects registered in ~/.claude.json
- Plugin caches and local plugins
- Marketplace plugins (~/.claude/plugins/marketplaces/*/) — recursive scan
- MCP server configs (~/.claude.json mcpServers, .mcp.json)
- LSP servers enabled in ~/.claude/settings.json

This script ONLY discovers element locations. It does NOT analyze or extract keywords.
Keyword/phrase extraction is done by the agent reading each element.

Usage:
    python3 pss_discover.py [--json] [--project-only] [--user-only]
    python3 pss_discover.py --jsonl  # One JSON object per line
    python3 pss_discover.py --checklist [--batch-size 10] [--output FILE]
    python3 pss_discover.py --all-projects
    python3 pss_discover.py --type skill,agent  # Filter to specific types
    python3 pss_discover.py --exclude-inactive-plugins  # Skip disabled plugins

Output Modes:
    Default: List of element paths with metadata (name, path, source, type)
    --json: JSON format for programmatic use
    --jsonl: One JSON object per line (name, type, source, path, description)
    --checklist: Markdown checklist with batches for parallel agent processing

Checklist Format:
    The checklist divides elements into batches (default 10 per batch) for parallel
    agent processing. Each batch can be assigned to a different sonnet subagent.
"""

import argparse
import json
import math
import os
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def get_home_dir() -> Path:
    """Get user home directory."""
    return Path.home()


def get_claude_dir() -> Path:
    """Get Claude's user directory ($HOME/.claude)."""
    return Path.home() / ".claude"


def get_cwd() -> Path:
    """Get current working directory."""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        return Path(project_dir)
    return Path.cwd()


# ---------------------------------------------------------------------------
# Safe-name boundary check (audit 20260514 SEC-4).
#
# Plugin / marketplace / element names that arrive from external manifests
# (plugin.json, marketplace.json, installed_plugins.json, known_marketplaces.json)
# MUST flow through _safe_name() before being stored as element identifiers,
# used in CozoDB keys, hash inputs, or composite paths. A malicious upstream
# plugin can ship `name = "../..<sensitive-system-file>"` and rely on a downstream consumer
# treating the field as a path component — _safe_name closes that hole at the
# import boundary.
#
# Whitelist is permissive enough to accept legacy snake_case / PascalCase /
# dotted names (some real plugins use them), but rejects:
#   - non-strings, empty, whitespace-only
#   - length > 64
#   - any character outside [A-Za-z0-9_.\\-]
#   - leading dot (hidden-file confusion / dotfile path-traversal trick)
#   - leading dash (looks like a CLI flag to downstream tools)
# ---------------------------------------------------------------------------
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
_SAFE_NAME_MAX_LEN = 64


def _safe_name(value: Any) -> str | None:
    """Return value if it passes the manifest-name safety whitelist, else None.

    None signals "skip this element entirely" — callers MUST check.
    """
    if not isinstance(value, str):
        return None
    name = value.strip()
    if not name or len(name) > _SAFE_NAME_MAX_LEN:
        return None
    if name.startswith(".") or name.startswith("-"):
        return None
    if not _SAFE_NAME_RE.match(name):
        return None
    return name


def _safe_plugin_id(value: Any) -> str | None:
    """Validate a composite '<plugin-name>@<marketplace-name>' identifier.

    Returns the original string if BOTH halves pass _safe_name, else None.
    Used at the installed_plugins.json read boundary where the JSON key is
    the composite id.
    """
    if not isinstance(value, str):
        return None
    parts = value.split("@", 1)
    if len(parts) != 2:
        return None
    plugin, marketplace = parts
    if _safe_name(plugin) is None or _safe_name(marketplace) is None:
        return None
    return value


# ---------------------------------------------------------------------------
# Bounded file reads (audit 20260514 HP-1).
#
# Discovery iterates every SKILL.md / agent / command / README it finds in
# ~/.claude/{skills,agents,commands,rules,plugins}/* and every project's
# .claude/. A multi-GB file dropped into any of those trees (a video, a
# core dump, a runaway log) would OOM the discovery process via Path.read_text.
#
# Every read_text() call in this module MUST flow through _safe_read_text.
# Files over the cap are logged to stderr and skipped (returns None) — the
# discovery loop continues without crashing.
#
# Caps per file kind:
#   - SKILL.md / agent.md / command.md content reads:   4 MB  (DEFAULT_CAP)
#   - JSON manifests (plugin.json, settings.json, etc): 1 MB  (MANIFEST_CAP)
# ---------------------------------------------------------------------------
DEFAULT_READ_CAP = 4 * 1024 * 1024  # 4 MB for SKILL/agent/README content
MANIFEST_READ_CAP = 1 * 1024 * 1024  # 1 MB for JSON manifests


def _safe_read_text(
    path: Path,
    max_bytes: int = DEFAULT_READ_CAP,
    encoding: str = "utf-8",
    errors: str = "strict",
) -> str | None:
    """Read text file with size cap. Returns None and logs to stderr on:
      - stat() failure (broken symlink, permission)
      - file size > max_bytes (logged + skipped per HP-1)
      - read() OSError (mid-read failure)

    Callers MUST check `if content is None: continue` to skip files that
    failed the cap or read.
    """
    try:
        size = path.stat().st_size
    except OSError as exc:
        print(
            f"[pss-discover] WARN: stat failed for {path}: {exc}",
            file=sys.stderr,
        )
        return None
    if size > max_bytes:
        print(
            f"[pss-discover] WARN: skipping {path} — size {size} bytes "
            f"> cap {max_bytes} (per HP-1 audit-20260514)",
            file=sys.stderr,
        )
        return None
    try:
        return path.read_text(encoding=encoding, errors=errors)
    except OSError as exc:
        print(
            f"[pss-discover] WARN: read failed for {path}: {exc}",
            file=sys.stderr,
        )
        return None


def _load_inactive_plugin_ids() -> tuple[set[str], set[str]]:
    """Load inactive plugin identifiers from settings.json.

    Returns:
        (inactive_ids, disabled_marketplaces) where:
        - inactive_ids: set of 'plugin@marketplace' strings explicitly disabled
        - disabled_marketplaces: set of marketplace names where ALL plugins are disabled
          (used as fallback for marketplaces without .claude-plugin/plugin.json)

    Plugins not in enabledPlugins are considered active (included by default).
    """
    settings_path = get_claude_dir() / "settings.json"
    if not settings_path.exists():
        return set(), set()
    try:
        data = json.loads(_safe_read_text(settings_path, max_bytes=MANIFEST_READ_CAP) or "")
        enabled_map = data.get("enabledPlugins", {})
        inactive_ids = {k for k, v in enabled_map.items() if v is False}

        # Group by marketplace to find fully-disabled marketplaces
        mp_statuses: dict[str, list[bool]] = {}
        for plugin_id, is_active in enabled_map.items():
            parts = plugin_id.split("@")
            if len(parts) == 2:
                mp_statuses.setdefault(parts[1], []).append(bool(is_active))
        disabled_marketplaces = {
            mp for mp, statuses in mp_statuses.items() if statuses and not any(statuses)
        }

        return inactive_ids, disabled_marketplaces
    except (json.JSONDecodeError, OSError):
        return set(), set()


def _build_marketplace_plugin_map(marketplace_root: Path) -> dict[Path, str]:
    """Build mapping from plugin directory to 'plugin-name@marketplace-name'.

    Scans for .claude-plugin/plugin.json files to identify plugin boundaries.
    Each plugin.json's parent dir (.claude-plugin/) parent is the plugin root.
    """
    plugin_map: dict[Path, str] = {}
    if not marketplace_root.exists():
        return plugin_map
    for marketplace_dir in marketplace_root.iterdir():
        if not marketplace_dir.is_dir() or marketplace_dir.name.startswith("."):
            continue
        # Sanitize the marketplace name at the source-directory boundary so
        # a maliciously-named directory like '..<sensitive-system-file>' is skipped.
        safe_mp_name = _safe_name(marketplace_dir.name)
        if safe_mp_name is None:
            continue
        for plugin_json in marketplace_dir.rglob(".claude-plugin/plugin.json"):
            try:
                data = json.loads(_safe_read_text(plugin_json, max_bytes=MANIFEST_READ_CAP) or "")
            except (json.JSONDecodeError, OSError):
                continue
            # SEC-4: sanitize plugin name from external manifest. A poisoned
            # plugin.json with name='../..<sensitive-system-file>' previously survived
            # discovery and seeded a composite id used in CozoDB keys.
            safe_plugin_name = _safe_name(data.get("name", ""))
            if safe_plugin_name is None:
                continue
            # Plugin dir is the parent of .claude-plugin/
            plugin_dir = plugin_json.parent.parent
            plugin_map[plugin_dir] = f"{safe_plugin_name}@{safe_mp_name}"
    return plugin_map


def _get_plugin_id_for_path(path: Path, plugin_map: dict[Path, str]) -> str | None:
    """Find which plugin a given path belongs to by walking up the tree."""
    current = path
    while current != current.parent:
        if current in plugin_map:
            return plugin_map[current]
        current = current.parent
    return None


def get_all_projects_from_claude_config() -> list[tuple[str, Path]]:
    """Read all project paths from ~/.claude.json.

    The ~/.claude.json file contains a 'projects' object where keys are
    absolute paths to project directories. This function extracts all
    paths and validates that they still exist on disk.

    Returns:
        List of tuples: (project_name, project_path) for existing projects
    """
    config_path = get_home_dir() / ".claude.json"
    projects: list[tuple[str, Path]] = []

    if not config_path.exists():
        print(f"Warning: {config_path} not found", file=sys.stderr)
        return projects

    try:
        config_data = json.loads(_safe_read_text(config_path, max_bytes=MANIFEST_READ_CAP) or "")
        projects_dict = config_data.get("projects", {})

        for project_path_str in projects_dict.keys():
            project_path = Path(project_path_str)

            # Check if project still exists (could have been deleted)
            if not project_path.exists():
                print(
                    f"Warning: Project no longer exists: {project_path}",
                    file=sys.stderr,
                )
                continue

            if not project_path.is_dir():
                print(
                    f"Warning: Project path is not a directory: {project_path}",
                    file=sys.stderr,
                )
                continue

            # Extract project name from path (last component)
            project_name = project_path.name
            projects.append((project_name, project_path))

        return projects

    except json.JSONDecodeError as e:
        print(f"Error parsing {config_path}: {e}", file=sys.stderr)
        return projects
    except OSError as e:
        print(f"Error reading {config_path}: {e}", file=sys.stderr)
        return projects


# Valid element subdirectory names (mapped to their type string)
ELEMENT_SUBDIRS = {
    "skills": "skill",
    "agents": "agent",
    "commands": "command",
    "rules": "rule",
}


def get_all_element_locations(
    scan_all_projects: bool = False,
    element_types: list[str] | None = None,
    exclude_inactive_plugins: bool = False,
) -> list[tuple[str, str, Path]]:
    """Get all locations where Claude Code elements can be found.

    Returns: list of (source, element_type, dir_path) tuples.
    element_type is one of: "skill", "agent", "command", "rule"

    Args:
        scan_all_projects: If True, scan all projects registered in ~/.claude.json
        element_types: If provided, only scan these types (e.g., ["skill", "agent"]).
                       None means scan all types.
        exclude_inactive_plugins: If True, skip plugins disabled in settings.json
                                  enabledPlugins map.
    """
    # Determine which subdirectories to scan
    if element_types:
        # Map type names back to subdirectory names
        type_set = set(element_types)
        subdirs_to_scan = {k: v for k, v in ELEMENT_SUBDIRS.items() if v in type_set}
    else:
        subdirs_to_scan = ELEMENT_SUBDIRS

    # Load inactive plugin set when filtering is requested
    inactive_ids: set[str] = set()
    disabled_marketplaces: set[str] = set()
    marketplace_plugin_map: dict[Path, str] = {}
    if exclude_inactive_plugins:
        inactive_ids, disabled_marketplaces = _load_inactive_plugin_ids()
        marketplace_root = get_claude_dir() / "plugins" / "marketplaces"
        marketplace_plugin_map = _build_marketplace_plugin_map(marketplace_root)

    locations: list[tuple[str, str, Path]] = []
    cwd = get_cwd()

    def _add_element_dirs(
        parent: Path, source: str, include_rules: bool = True
    ) -> None:
        """Scan parent directory for element subdirectories and add them."""
        for subdir_name, elem_type in subdirs_to_scan.items():
            # Rules are NOT in plugins, only at user/project level
            if elem_type == "rule" and not include_rules:
                continue
            elem_dir = parent / subdir_name
            if elem_dir.exists() and elem_dir.is_dir():
                locations.append((source, elem_type, elem_dir))

    # 1. User-level elements: ~/.claude/{skills,agents,commands,rules}/
    _add_element_dirs(get_claude_dir(), "user", include_rules=True)

    # 1b. Cross-client skills from known AI tools (AgentSkills open standard).
    # These AI clients create ~/.<client>/skills/ following the AgentSkills
    # convention. Only scan explicitly known clients to avoid false positives
    # from non-AI software that uses "skills" with other meanings.
    _KNOWN_AI_CLIENTS = [
        "agents",       # agentskills.io cross-client convention
        "codex",        # OpenAI Codex
        "copilot",      # GitHub Copilot
        "gemini",       # Google Gemini
        "kiro",         # Kiro
        "roo",          # Roo
        "trae",         # Trae
        "trae-cn",      # Trae CN
        "qwen",         # Alibaba Qwen
        "qoder",        # Qoder
        "openhands",    # OpenHands
        "mux",          # Mux
        "vibe",         # Vibe
        "kode",         # Kode
        "kilocode",     # KiloCode
        "iflow",        # iFlow
        "junie",        # JetBrains Junie
        "codebuddy",    # CodeBuddy
        "openclaw",     # OpenClaw
        "antigravity",  # Antigravity
        "mcpjam",       # MCP Jam
        "adal",         # Adal
        "pochi",        # Pochi
        "neovate",      # Neovate
        "zencoder",     # Zencoder
        "pi",           # Pi
    ]
    home = Path.home()
    for client_name in _KNOWN_AI_CLIENTS:
        client_dir = home / f".{client_name}"
        if client_dir.is_dir() and (client_dir / "skills").is_dir():
            _add_element_dirs(
                client_dir, f"user:{client_name}", include_rules=False
            )

    # 2. Current project-level elements: .claude/{skills,agents,commands,rules}/
    _add_element_dirs(cwd / ".claude", "project", include_rules=True)

    # 2b. Cross-client project skills: .agents/skills/ (AgentSkills open standard)
    agents_project = cwd / ".agents"
    if agents_project.exists() and agents_project.is_dir():
        _add_element_dirs(agents_project, "project:agentskills", include_rules=False)

    # 3. Plugin cache: ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/
    plugin_cache = get_claude_dir() / "plugins" / "cache"
    if plugin_cache.exists():
        for marketplace in plugin_cache.iterdir():
            if not marketplace.is_dir():
                continue
            for plugin in marketplace.iterdir():
                if not plugin.is_dir():
                    continue
                # Skip plugins disabled in settings.json
                if inactive_ids:
                    plugin_id = f"{plugin.name}@{marketplace.name}"
                    if plugin_id in inactive_ids:
                        continue
                for version in plugin.iterdir():
                    if not version.is_dir():
                        continue
                    plugin_source = f"plugin:{marketplace.name}/{plugin.name}"
                    # Scan for element subdirectories in the plugin version dir
                    _add_element_dirs(version, plugin_source, include_rules=False)
                    # Legacy layout (SKILL.md directly in version dir) is NOT supported
                    # for multi-type indexing because the version number becomes the skill name.
                    # Plugins should use the skills/ subdirectory layout instead.

    # 4. Local plugins: ~/.claude/plugins/<plugin>/
    user_plugins = get_claude_dir() / "plugins"
    if user_plugins.exists():
        for plugin_dir in user_plugins.iterdir():
            if not plugin_dir.is_dir():
                continue
            if plugin_dir.name in ("cache", "_disabled", "repos", "marketplaces"):
                continue
            _add_element_dirs(
                plugin_dir, f"plugin:{plugin_dir.name}", include_rules=False
            )

    # 5. Current project plugins: .claude/plugins/*/
    project_plugins = cwd / ".claude" / "plugins"
    if project_plugins.exists():
        for plugin_dir in project_plugins.iterdir():
            if plugin_dir.is_dir():
                _add_element_dirs(
                    plugin_dir, f"plugin:{plugin_dir.name}", include_rules=False
                )

    # 5b. Marketplace plugins: ~/.claude/plugins/marketplaces/*/
    # Marketplaces contain thousands of elements at variable directory depth.
    # We recursively find all skills/, agents/, commands/ directories and add them.
    # This is essential for agent profiling which needs ALL available elements,
    # not just the ones currently active in the user's Claude Code instance.
    _SKIP_DIRS = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".cache",
        ".tox",
        ".mypy_cache",
    }
    marketplace_root = get_claude_dir() / "plugins" / "marketplaces"
    if marketplace_root.exists():
        for marketplace_dir in marketplace_root.iterdir():
            if not marketplace_dir.is_dir():
                continue
            if marketplace_dir.name.startswith("."):
                continue
            # Walk the marketplace directory tree to find element subdirectories
            # at any depth (structure varies: some have skills/ at depth 1,
            # others nest inside plugin-name/skills/ or plugin/version/skills/)
            for dirpath, dirnames, _ in os.walk(marketplace_dir, followlinks=False):
                # Prune directories we should never descend into
                dirnames[:] = [
                    d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
                ]
                dp = Path(dirpath)
                dir_name = dp.name
                # Check if this directory IS a recognized element subdirectory
                if dir_name in subdirs_to_scan:
                    elem_type = subdirs_to_scan[dir_name]
                    # Derive source label from marketplace name + relative path
                    rel = dp.relative_to(marketplace_root)
                    # rel looks like: marketplace-name/subpath/skills
                    # source = "marketplace:<marketplace-name>"
                    mp_name = rel.parts[0]

                    # Skip elements from inactive plugins
                    if inactive_ids:
                        pid = _get_plugin_id_for_path(dp, marketplace_plugin_map)
                        if pid and pid in inactive_ids:
                            dirnames.clear()
                            continue
                        # Fallback: if plugin can't be identified (no .claude-plugin/
                        # plugin.json) but ALL plugins from this marketplace are
                        # disabled, skip the entire marketplace
                        if not pid and mp_name in disabled_marketplaces:
                            dirnames.clear()
                            continue

                    source_label = f"marketplace:{mp_name}"
                    locations.append((source_label, elem_type, dp))
                    # Do not descend into the element dir itself (no nested
                    # skills/skills/ etc.), prune it from further walking
                    dirnames.clear()

    # 6. All projects from ~/.claude.json (comprehensive indexing)
    if scan_all_projects:
        seen_project_paths: set[Path] = {cwd}

        all_projects = get_all_projects_from_claude_config()
        for project_name, project_path in all_projects:
            if project_path in seen_project_paths:
                continue
            seen_project_paths.add(project_path)

            # 6a. Project-level elements
            _add_element_dirs(
                project_path / ".claude",
                f"project:{project_name}",
                include_rules=True,
            )

            # 6b. Project plugins
            proj_plugins = project_path / ".claude" / "plugins"
            if proj_plugins.exists():
                for plugin_dir in proj_plugins.iterdir():
                    if plugin_dir.is_dir():
                        source = f"project:{project_name}/plugin:{plugin_dir.name}"
                        _add_element_dirs(plugin_dir, source, include_rules=False)

    return locations


def get_all_skill_locations(scan_all_projects: bool = False) -> list[tuple[str, Path]]:
    """Get all locations where skills can be found.

    BACKWARD-COMPATIBLE WRAPPER: Returns (source, path) tuples for skills only.
    Used by pss_cleanup.py.
    """
    element_locs = get_all_element_locations(
        scan_all_projects=scan_all_projects,
        element_types=["skill"],
    )
    # Convert (source, element_type, path) -> (source, path)
    return [(source, path) for source, _, path in element_locs]


def _find_readme_in_plugin(plugin_dir: Path) -> str | None:
    """Find the most relevant README.md for an MCP server in a plugin directory."""
    candidates = [
        plugin_dir / "README.md",
        plugin_dir.parent / "README.md",
    ]
    # Also check .claude-plugin subdirectory
    claude_plugin_dir = plugin_dir / ".claude-plugin"
    if claude_plugin_dir.exists():
        candidates.insert(0, claude_plugin_dir / "README.md")

    for c in candidates:
        if c.is_file():
            try:
                content = _safe_read_text(c, errors="replace") or ""
                if len(content) > 100:
                    return content[:8000]
            except OSError:
                continue
    return None


def _find_tool_names_in_source(plugin_dir: Path) -> list[str]:
    """Search for tool/function names in MCP server source code."""
    tool_patterns = [
        r'name:\s*["\']([^"\']+)["\']',
        r'server\.tool\(\s*["\']([^"\']+)["\']',
        r'\.addTool\(\s*["\']([^"\']+)["\']',
        r'@tool\s*\(\s*["\']([^"\']+)["\']',
        r'"name":\s*"([^"]+)".*?"description"',
    ]
    tools_found: set[str] = set()
    skip_dirs = {"node_modules", ".git", "dist", "build", "__pycache__", ".next"}

    for root, dirs, files in os.walk(plugin_dir, followlinks=False):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if not fname.endswith((".ts", ".py", ".js")):
                continue
            fpath = Path(root) / fname
            try:
                content = _safe_read_text(fpath, errors="replace") or ""
                for pattern in tool_patterns:
                    for match in re.finditer(pattern, content):
                        tool_name = match.group(1).strip()
                        if 2 < len(tool_name) < 60 and " " not in tool_name:
                            tools_found.add(tool_name)
            except OSError:
                continue
    return sorted(tools_found)[:30]


def _build_mcp_descriptor(
    name: str,
    config: dict[str, Any],
    config_path: Path,
    plugin_dir: Path,
    marketplace: str,
    descriptor_dir: Path,
) -> Path:
    """Build a markdown descriptor file for an MCP server for indexer agent consumption.

    Returns path to the descriptor .md file in the provided descriptor directory.
    The caller must create descriptor_dir using tempfile.mkdtemp() to avoid
    predictable temp paths (security: unpredictable per-run directory).
    """

    command = config.get("command", "unknown")
    args = config.get("args", [])
    args_str = " ".join(str(a) for a in args) if isinstance(args, list) else str(args)

    lines = [
        f"# MCP Server: {name}",
        "",
        "**Type**: MCP server",
        f"**Command**: `{command} {args_str}`",
        f"**Marketplace**: {marketplace}",
        f"**Config path**: {config_path}",
        "",
    ]

    # Add README content if available
    readme = _find_readme_in_plugin(plugin_dir)
    if readme:
        lines.append("## README Content")
        lines.append("")
        lines.append(readme[:4000])
        lines.append("")

    # Add discovered tool names from source code
    tools = _find_tool_names_in_source(plugin_dir)
    if tools:
        lines.append("## Discovered Tool Names")
        lines.append("")
        lines.append(", ".join(tools))
        lines.append("")

    # If no README and no tools, add inference note for indexer agent
    if not readme and not tools:
        lines.append("## No README or source code found")
        lines.append("")
        lines.append(
            f"Infer the MCP server's purpose from its name '{name}' and command '{command} {args_str}'."
        )
        lines.append("The package name in the command often reveals the purpose.")
        lines.append("")

    safe_name = re.sub(r'[\\/:*?"<>|]', '_', name)
    out_file = descriptor_dir / f"{safe_name}.md"
    out_file.write_text("\n".join(lines))
    return out_file


def _discover_marketplace_mcps(
    seen_names: set[str],
    inactive_plugin_ids: set[str] | None = None,
    disabled_marketplaces: set[str] | None = None,
    plugin_map: dict[Path, str] | None = None,
) -> list[dict[str, Any]]:
    """Scan all marketplace plugins for MCP server configurations.

    Searches ~/.claude/plugins/marketplaces/ for:
    - .mcp.json files with mcpServers
    - plugin.json files with mcpServers
    - mcp.json files

    Deduplicates by server name. Builds descriptor files for each MCP.
    Optionally filters out MCPs from inactive plugins.
    """
    servers: list[dict[str, Any]] = []
    marketplaces_dir = get_claude_dir() / "plugins" / "marketplaces"
    if not marketplaces_dir.exists():
        return servers

    # Use a unique temp dir per run to avoid TOCTOU race on predictable paths.
    # Clean up stale dirs from previous runs (older than 1 hour) to prevent
    # disk accumulation on repeated manual runs.
    tmp_base = Path(tempfile.gettempdir())
    for old_dir in tmp_base.glob("pss-mcp-*"):
        try:
            if old_dir.is_dir() and (time.time() - old_dir.stat().st_mtime) > 3600:
                shutil.rmtree(old_dir, ignore_errors=True)
        except OSError:
            pass
    descriptor_dir = Path(tempfile.mkdtemp(prefix="pss-mcp-"))

    skip_dirs = {"node_modules", ".git", "dist", "build", "__pycache__"}
    config_filenames = {".mcp.json", "mcp.json", "plugin.json"}

    for root, dirs, files in os.walk(marketplaces_dir, followlinks=False):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if fname not in config_filenames:
                continue
            fpath = Path(root) / fname
            try:
                # Skip MCPs from inactive plugins
                if inactive_plugin_ids:
                    root_path = Path(root)
                    pid = (
                        _get_plugin_id_for_path(root_path, plugin_map)
                        if plugin_map
                        else None
                    )
                    if pid and pid in inactive_plugin_ids:
                        continue
                    # Fallback: check if entire marketplace is disabled
                    if not pid and disabled_marketplaces:
                        rel = str(fpath).replace(str(marketplaces_dir) + "/", "")
                        mp = rel.split("/")[0]
                        if mp in disabled_marketplaces:
                            continue

                data = json.loads(_safe_read_text(fpath, max_bytes=MANIFEST_READ_CAP) or "")
                mcp_servers = data.get("mcpServers", data.get("mcp_servers", {}))
                if not isinstance(mcp_servers, dict) or not mcp_servers:
                    continue

                # Determine marketplace name from relative path
                rel = str(fpath).replace(str(marketplaces_dir) + "/", "")
                marketplace = rel.split("/")[0]

                for mcp_name, config in mcp_servers.items():
                    if mcp_name in seen_names:
                        continue
                    # Handle string configs (just a URL or command)
                    if isinstance(config, str):
                        config = {"command": config}
                    elif not isinstance(config, dict):
                        continue

                    seen_names.add(mcp_name)

                    # Build descriptor file for indexer agent consumption
                    descriptor_path = _build_mcp_descriptor(
                        mcp_name, config, fpath, Path(root), marketplace, descriptor_dir
                    )

                    # Extract basic description from README
                    description = ""
                    readme = _find_readme_in_plugin(Path(root))
                    if readme:
                        for line in readme.split("\n"):
                            line = line.strip()
                            if line and not line.startswith("#") and len(line) > 20:
                                description = line[:200]
                                break

                    server_data: dict[str, Any] = {
                        "name": mcp_name,
                        "type": "mcp",
                        "source": f"marketplace:{marketplace}",
                        "path": str(descriptor_path),
                        "description": description,
                        "preview": json.dumps(config, indent=2)[:500],
                        "server_type": config.get("type", "stdio"),
                        "server_command": config.get("command", ""),
                        "server_args": config.get("args", []),
                    }
                    servers.append(server_data)

            except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                continue

    return servers


def parse_frontmatter(content: str) -> dict[str, Any]:
    """Parse YAML frontmatter from markdown content using PyYAML."""
    if not content.startswith("---"):
        return {}

    end_idx = content.find("\n---", 3)
    if end_idx == -1:
        return {}

    frontmatter_text = content[3:end_idx].strip()
    try:
        import yaml

        parsed = yaml.safe_load(frontmatter_text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def discover_mcp_servers(
    scan_all_projects: bool = False,
    exclude_inactive_plugins: bool = False,
) -> list[dict[str, Any]]:
    """Discover MCP servers from JSON config files.

    Sources:
    1. ~/.claude.json -> mcpServers key (user-level)
    2. .mcp.json in current project (project-level)
    3. (if scan_all_projects) Each project's .mcp.json
    4. Marketplace plugins (optionally filtered by active status)
    """
    servers: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    home = get_home_dir()
    cwd = get_cwd()

    def _extract_servers(config_path: Path, source: str) -> None:
        """Extract MCP server entries from a JSON config file."""
        if not config_path.exists():
            return
        try:
            data = json.loads(_safe_read_text(config_path, max_bytes=MANIFEST_READ_CAP) or "")
            mcp_servers = data.get("mcpServers", {})
            for name, config in mcp_servers.items():
                if name in seen_names:
                    continue
                seen_names.add(name)

                # Try to get description from README.md in servers dir
                description = ""
                server_dir = get_claude_dir() / "servers" / name
                readme = server_dir / "README.md"
                if readme.exists():
                    try:
                        readme_text = _safe_read_text(readme) or ""
                        # First non-empty line after any heading
                        for line in readme_text.split("\n"):
                            line = line.strip()
                            if line and not line.startswith("#"):
                                description = line[:200]
                                break
                    except (OSError, UnicodeDecodeError):
                        pass

                # Also check project-level server README
                if not description:
                    project_server_dir = get_cwd() / ".claude" / "servers" / name
                    project_readme = project_server_dir / "README.md"
                    if project_readme.exists():
                        try:
                            readme_text = _safe_read_text(project_readme) or ""
                            for line in readme_text.split("\n"):
                                line = line.strip()
                                if line and not line.startswith("#"):
                                    description = line[:200]
                                    break
                        except (OSError, UnicodeDecodeError):
                            pass

                server_data: dict[str, Any] = {
                    "name": name,
                    "type": "mcp",
                    "source": source,
                    "path": f"{config_path}#mcpServers.{name}",
                    "description": description,
                    "preview": json.dumps(config, indent=2)[:500],
                    "server_type": config.get("type", "stdio"),
                    "server_command": config.get("command", ""),
                    "server_args": config.get("args", []),
                }
                servers.append(server_data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"Warning: Error parsing {config_path}: {e}", file=sys.stderr)
        except OSError as e:
            print(f"Warning: Cannot read {config_path}: {e}", file=sys.stderr)

    # 1. User-level: ~/.claude.json
    _extract_servers(home / ".claude.json", "user")

    # 2. Project-level: .mcp.json
    _extract_servers(cwd / ".mcp.json", "project")

    # 3. All projects (if requested)
    if scan_all_projects:
        seen_paths: set[Path] = {cwd}
        for _, project_path in get_all_projects_from_claude_config():
            if project_path in seen_paths:
                continue
            seen_paths.add(project_path)
            _extract_servers(project_path / ".mcp.json", f"project:{project_path.name}")

    # 4. Marketplace plugins: ~/.claude/plugins/marketplaces/**/
    mcp_inactive_ids: set[str] | None = None
    mcp_disabled_mps: set[str] | None = None
    mp_plugin_map: dict[Path, str] | None = None
    if exclude_inactive_plugins:
        mcp_inactive_ids, mcp_disabled_mps = _load_inactive_plugin_ids()
        mp_root = get_claude_dir() / "plugins" / "marketplaces"
        mp_plugin_map = _build_marketplace_plugin_map(mp_root)
    marketplace_mcps = _discover_marketplace_mcps(
        seen_names, mcp_inactive_ids, mcp_disabled_mps, mp_plugin_map
    )
    servers.extend(marketplace_mcps)

    return servers


# Known LSP servers from claude-plugins-official
LSP_REGISTRY: dict[str, dict[str, Any]] = {
    "pyright-lsp": {
        "description": "Python language server providing type checking, diagnostics, and autocomplete",
        "language_ids": ["python"],
        "keywords": [
            "python",
            "type checking",
            "pyright",
            "lsp",
            "diagnostics",
            "autocomplete",
            "lint",
        ],
        "category": "code-quality",
        "intents": ["type-check", "lint", "autocomplete", "diagnose"],
    },
    "typescript-lsp": {
        "description": "TypeScript/JavaScript language server for type checking and diagnostics",
        "language_ids": ["typescript", "javascript"],
        "keywords": [
            "typescript",
            "javascript",
            "type checking",
            "lsp",
            "diagnostics",
            "ts",
            "js",
        ],
        "category": "code-quality",
        "intents": ["type-check", "lint", "autocomplete", "diagnose"],
    },
    "gopls-lsp": {
        "description": "Go language server for code navigation, diagnostics, and formatting",
        "language_ids": ["go"],
        "keywords": ["go", "golang", "gopls", "lsp", "diagnostics", "formatting"],
        "category": "code-quality",
        "intents": ["type-check", "lint", "format", "diagnose"],
    },
    "rust-analyzer-lsp": {
        "description": "Rust language server for code analysis, diagnostics, and refactoring",
        "language_ids": ["rust"],
        "keywords": ["rust", "rust-analyzer", "cargo", "lsp", "diagnostics"],
        "category": "code-quality",
        "intents": ["type-check", "lint", "autocomplete", "diagnose"],
    },
    "jdtls-lsp": {
        "description": "Java language server for Eclipse JDT-based diagnostics and refactoring",
        "language_ids": ["java"],
        "keywords": [
            "java",
            "jdtls",
            "eclipse",
            "lsp",
            "diagnostics",
            "maven",
            "gradle",
        ],
        "category": "code-quality",
        "intents": ["type-check", "lint", "autocomplete", "diagnose"],
    },
    "clangd-lsp": {
        "description": "C/C++ language server for code completion, diagnostics, and navigation",
        "language_ids": ["c", "cpp", "objective-c"],
        "keywords": ["c", "c++", "cpp", "clangd", "lsp", "diagnostics", "objective-c"],
        "category": "code-quality",
        "intents": ["type-check", "lint", "autocomplete", "diagnose"],
    },
    "swift-lsp": {
        "description": "Swift language server for iOS/macOS development diagnostics",
        "language_ids": ["swift"],
        "keywords": [
            "swift",
            "ios",
            "macos",
            "sourcekit",
            "lsp",
            "diagnostics",
            "xcode",
        ],
        "category": "code-quality",
        "intents": ["type-check", "lint", "autocomplete", "diagnose"],
    },
    "csharp-lsp": {
        "description": "C# language server for .NET development diagnostics",
        "language_ids": ["csharp"],
        "keywords": [
            "csharp",
            "c#",
            "dotnet",
            ".net",
            "lsp",
            "diagnostics",
            "omnisharp",
        ],
        "category": "code-quality",
        "intents": ["type-check", "lint", "autocomplete", "diagnose"],
    },
}


def discover_lsp_servers() -> list[dict[str, Any]]:
    """Discover enabled LSP servers from settings.json using hardcoded registry.

    Source: ~/.claude/settings.json -> enabledPlugins entries matching *-lsp@*
    Only includes LSPs that are enabled (value=true) in settings.
    """
    servers: list[dict[str, Any]] = []
    settings_path = get_claude_dir() / "settings.json"

    if not settings_path.exists():
        return servers

    try:
        data = json.loads(_safe_read_text(settings_path, max_bytes=MANIFEST_READ_CAP) or "")
        enabled_plugins = data.get("enabledPlugins", {})

        for plugin_id, enabled in enabled_plugins.items():
            if not enabled:
                continue
            # Match pattern: *-lsp@* (e.g., "pyright-lsp@claude-plugins-official")
            if "-lsp@" not in plugin_id:
                continue

            # Extract LSP name from plugin ID (everything before @)
            lsp_name = plugin_id.split("@")[0]

            registry_entry = LSP_REGISTRY.get(lsp_name)
            if not registry_entry:
                # Unknown LSP -- still include with minimal metadata
                servers.append(
                    {
                        "name": lsp_name,
                        "type": "lsp",
                        "source": "built-in",
                        "path": f"{settings_path}#enabledPlugins.{plugin_id}",
                        "description": f"{lsp_name} language server",
                        "preview": "",
                        "language_ids": [],
                    }
                )
                continue

            servers.append(
                {
                    "name": lsp_name,
                    "type": "lsp",
                    "source": "built-in",
                    "path": f"{settings_path}#enabledPlugins.{plugin_id}",
                    "description": registry_entry["description"],
                    "preview": "",
                    "language_ids": registry_entry["language_ids"],
                }
            )

    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"Warning: Error parsing {settings_path}: {e}", file=sys.stderr)
    except OSError as e:
        print(f"Warning: Cannot read {settings_path}: {e}", file=sys.stderr)

    return servers


def _hash_short(payload: str) -> str:
    """Short stable hash used as a suffix for hook element names.

    Hooks merge across scopes per CC settings precedence
    (https://code.claude.com/docs/en/settings.md), so each hook entry needs a
    deterministic name that survives reordering. We hash the canonical
    (event_type, matcher, command) triple — the same triple Claude Code uses
    to dedupe array settings — so a hook keeps the same element_id across
    scans even if its index in the source array shifts.
    """
    import hashlib

    return hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()[:10]


def discover_hooks(scan_all_projects: bool = False) -> list[dict[str, Any]]:
    """Discover hook entries from settings.json files and plugin hooks.json.

    Per https://code.claude.com/docs/en/settings.md array settings (hooks)
    MERGE across scopes — they do not override. Each hook entry is therefore
    its own element. The element name is derived from
    (event_type, matcher, command) so reorders within a settings file do
    not produce spurious "removed + installed" event pairs.

    Sources:
    1. ~/.claude/settings.json hooks.<EventName>[]
    2. .claude/settings.json (project)
    3. .claude/settings.local.json (local — gitignored)
    4. <plugin-root>/hooks.json (top-level plugin layout)
    5. <plugin-root>/hooks/hooks.json (subfolder layout)
    """
    elements: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _emit(source: str, settings_path: Path, event_name: str, idx: int,
              matcher: str, hook_entry: dict[str, Any]) -> None:
        cmd = str(hook_entry.get("command", ""))
        htype = str(hook_entry.get("type", "command"))
        canonical = f"{event_name}|{matcher}|{cmd}"
        short = _hash_short(canonical)
        name = f"{event_name}.{short}"
        dedup_key = f"hook:{source}:{name}"
        if dedup_key in seen:
            return
        seen.add(dedup_key)
        # Synthetic path uses a JSON-pointer-like fragment so the path
        # round-trips through size/hash logic without errors (the file
        # exists, even if the inner array index is part of the locator).
        path_locator = (
            f"{settings_path}#hooks.{event_name}[{idx}]"
        )
        description = f"{htype} hook on {event_name}"
        if matcher:
            description += f" (matcher: {matcher})"
        if cmd:
            preview_cmd = cmd if len(cmd) <= 200 else cmd[:200] + "..."
        else:
            preview_cmd = ""
        elements.append({
            "name": name,
            "type": "hook",
            "source": source,
            "path": path_locator,
            "description": description[:200],
            "preview": preview_cmd,
            "hook_event": event_name,
            "hook_matcher": matcher,
            "hook_type": htype,
            "hook_command": cmd[:500],
        })

    def _scan_settings(settings_path: Path, source: str) -> None:
        if not settings_path.exists():
            return
        try:
            data = json.loads(_safe_read_text(settings_path, max_bytes=MANIFEST_READ_CAP) or "")
        except (json.JSONDecodeError, OSError):
            return
        hooks_obj = data.get("hooks")
        if not isinstance(hooks_obj, dict):
            return
        for event_name, entries in hooks_obj.items():
            if not isinstance(entries, list):
                continue
            for idx, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                matcher = str(entry.get("matcher", ""))
                inner_hooks = entry.get("hooks", [])
                if not isinstance(inner_hooks, list):
                    continue
                for inner in inner_hooks:
                    if isinstance(inner, dict):
                        _emit(source, settings_path, event_name, idx, matcher, inner)

    def _scan_plugin_hooks(hooks_json: Path, source: str) -> None:
        if not hooks_json.exists():
            return
        try:
            data = json.loads(_safe_read_text(hooks_json, max_bytes=MANIFEST_READ_CAP) or "")
        except (json.JSONDecodeError, OSError):
            return
        hooks_obj = data.get("hooks")
        if not isinstance(hooks_obj, dict):
            return
        for event_name, entries in hooks_obj.items():
            if not isinstance(entries, list):
                continue
            for idx, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                matcher = str(entry.get("matcher", ""))
                inner_hooks = entry.get("hooks", [])
                if not isinstance(inner_hooks, list):
                    continue
                for inner in inner_hooks:
                    if isinstance(inner, dict):
                        _emit(source, hooks_json, event_name, idx, matcher, inner)

    # 1. User-level settings
    _scan_settings(get_claude_dir() / "settings.json", "user")

    # 2. Project settings (current cwd)
    cwd = get_cwd()
    _scan_settings(cwd / ".claude" / "settings.json", "project")
    _scan_settings(cwd / ".claude" / "settings.local.json", "local")

    # 3. All projects
    if scan_all_projects:
        seen_paths: set[Path] = {cwd}
        for proj_name, project_path in get_all_projects_from_claude_config():
            if project_path in seen_paths:
                continue
            seen_paths.add(project_path)
            _scan_settings(
                project_path / ".claude" / "settings.json",
                f"project:{proj_name}",
            )
            _scan_settings(
                project_path / ".claude" / "settings.local.json",
                f"local:{proj_name}",
            )

    # 4. Plugin-shipped hooks (cache + marketplaces)
    plugin_cache = get_claude_dir() / "plugins" / "cache"
    if plugin_cache.exists():
        for marketplace in plugin_cache.iterdir():
            if not marketplace.is_dir():
                continue
            for plugin in marketplace.iterdir():
                if not plugin.is_dir():
                    continue
                for version in plugin.iterdir():
                    if not version.is_dir():
                        continue
                    src = f"plugin:{marketplace.name}/{plugin.name}"
                    _scan_plugin_hooks(version / "hooks.json", src)
                    _scan_plugin_hooks(version / "hooks" / "hooks.json", src)
    return elements


def discover_plugins() -> list[dict[str, Any]]:
    """Discover installed plugins from ~/.claude/plugins/installed_plugins.json.

    Per CC v2.1.69 the file is version 2 — root has {"version": 2, "plugins":
    {"<name>@<marketplace>": [{scope, installPath, version, ...}, ...]}}.
    Each (plugin_id, scope) tuple becomes a separate element (a plugin can
    be installed in user AND project scope independently).
    """
    elements: list[dict[str, Any]] = []
    plugins_file = get_claude_dir() / "plugins" / "installed_plugins.json"
    if not plugins_file.exists():
        return elements
    try:
        data = json.loads(_safe_read_text(plugins_file, max_bytes=MANIFEST_READ_CAP) or "")
    except (json.JSONDecodeError, OSError):
        return elements
    # HP-2 (audit 20260514): CC v2.1.69+ uses installed_plugins.json v2.
    # Silently reading a v1-format file produces wrong elements (different
    # layout) — surface the mismatch instead of corrupting the index.
    if not isinstance(data, dict):
        print(
            f"[pss-discover] ERROR: installed_plugins.json at {plugins_file} "
            f"is not a JSON object — skipping plugin discovery.",
            file=sys.stderr,
        )
        return elements
    version = data.get("version")
    if version != 2:
        print(
            f"[pss-discover] ERROR: installed_plugins.json at {plugins_file} "
            f"has version {version!r}, expected 2 (CC v2.1.69+ uses v2). "
            f"Skipping plugin discovery; run /pss-reindex-skills after CC "
            f"upgrades the file.",
            file=sys.stderr,
        )
        return elements
    plugins_obj = data.get("plugins", {})
    if not isinstance(plugins_obj, dict):
        return elements
    for plugin_id, installs in plugins_obj.items():
        # SEC-4: validate composite '<plugin-name>@<marketplace-name>' id
        # before any downstream consumer treats it as a path or db key.
        safe_id = _safe_plugin_id(plugin_id)
        if safe_id is None:
            continue
        if not isinstance(installs, list):
            continue
        for entry in installs:
            if not isinstance(entry, dict):
                continue
            scope = str(entry.get("scope", "user"))
            install_path = str(entry.get("installPath", ""))
            version = str(entry.get("version", ""))
            installed_at = str(entry.get("installedAt", ""))
            git_sha = str(entry.get("gitCommitSha", ""))
            description = (
                f"Plugin {safe_id} v{version} installed at {scope} scope"
            )
            elements.append({
                "name": safe_id,
                "type": "plugin",
                "source": scope,
                "path": install_path or f"{plugins_file}#plugins.{safe_id}",
                "description": description[:200],
                "preview": json.dumps(entry, indent=2)[:500],
                "plugin_version": version,
                "plugin_installed_at": installed_at,
                "plugin_git_sha": git_sha,
            })
    return elements


def discover_marketplaces() -> list[dict[str, Any]]:
    """Discover known marketplaces from ~/.claude/plugins/known_marketplaces.json.

    Each top-level key is a marketplace name. Each entry has source.{source,
    repo|url}, installLocation, lastUpdated, autoUpdate.
    """
    elements: list[dict[str, Any]] = []
    mp_file = get_claude_dir() / "plugins" / "known_marketplaces.json"
    if not mp_file.exists():
        return elements
    try:
        data = json.loads(_safe_read_text(mp_file, max_bytes=MANIFEST_READ_CAP) or "")
    except (json.JSONDecodeError, OSError):
        return elements
    if not isinstance(data, dict):
        return elements
    for mp_name, entry in data.items():
        # SEC-4: sanitize marketplace name from external manifest.
        safe_mp = _safe_name(mp_name)
        if safe_mp is None:
            continue
        if not isinstance(entry, dict):
            continue
        src_obj = entry.get("source", {})
        repo_or_url = ""
        src_kind = ""
        if isinstance(src_obj, dict):
            src_kind = str(src_obj.get("source", ""))
            repo_or_url = str(src_obj.get("repo") or src_obj.get("url") or "")
        install_location = str(entry.get("installLocation", ""))
        description = (
            f"Marketplace {safe_mp} ({src_kind}: {repo_or_url})"
            if repo_or_url else f"Marketplace {safe_mp}"
        )
        elements.append({
            "name": safe_mp,
            "type": "marketplace",
            "source": "user",
            "path": install_location or f"{mp_file}#{safe_mp}",
            "description": description[:200],
            "preview": json.dumps(entry, indent=2)[:500],
            "marketplace_kind": src_kind,
            "marketplace_repo": repo_or_url,
        })
    return elements


def discover_monitors() -> list[dict[str, Any]]:
    """Discover monitor declarations from plugin manifests.

    Per CC v2.1.105+ a plugin may declare top-level `monitors`; per v2.1.129
    these moved under `experimental.monitors`. We accept either form. Each
    named monitor becomes one element.
    """
    elements: list[dict[str, Any]] = []
    seen: set[str] = set()
    plugin_cache = get_claude_dir() / "plugins" / "cache"
    if not plugin_cache.exists():
        return elements
    for marketplace in plugin_cache.iterdir():
        if not marketplace.is_dir():
            continue
        for plugin in marketplace.iterdir():
            if not plugin.is_dir():
                continue
            for version in plugin.iterdir():
                if not version.is_dir():
                    continue
                manifest = version / ".claude-plugin" / "plugin.json"
                if not manifest.exists():
                    continue
                try:
                    data = json.loads(_safe_read_text(manifest, max_bytes=MANIFEST_READ_CAP) or "")
                except (json.JSONDecodeError, OSError):
                    continue
                monitors_obj = data.get("monitors")
                if not isinstance(monitors_obj, dict):
                    experimental = data.get("experimental", {})
                    if isinstance(experimental, dict):
                        monitors_obj = experimental.get("monitors")
                if not isinstance(monitors_obj, dict):
                    continue
                src = f"plugin:{marketplace.name}/{plugin.name}"
                for monitor_name, mon_cfg in monitors_obj.items():
                    dedup_key = f"monitor:{src}:{monitor_name}"
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    description = ""
                    if isinstance(mon_cfg, dict):
                        description = str(mon_cfg.get("description", ""))[:200]
                    elements.append({
                        "name": monitor_name,
                        "type": "monitor",
                        "source": src,
                        "path": str(manifest),
                        "description": description or f"Monitor declared by {plugin.name}",
                        "preview": (
                            json.dumps(mon_cfg, indent=2)[:500]
                            if isinstance(mon_cfg, (dict, list))
                            else str(mon_cfg)[:500]
                        ),
                    })
    return elements


def _discover_styled_files_in_dir(
    parent: Path, source: str, subdir: str, elem_type: str,
    extensions: tuple[str, ...], seen: set[str],
) -> list[dict[str, Any]]:
    """Helper: scan parent/<subdir>/ for files matching extensions."""
    out: list[dict[str, Any]] = []
    target = parent / subdir
    if not target.exists() or not target.is_dir():
        return out
    try:
        entries = sorted(target.iterdir())
    except OSError:
        return out
    for f in entries:
        if not f.is_file():
            continue
        if not any(f.name.endswith(ext) for ext in extensions):
            continue
        name = f.stem
        dedup_key = f"{elem_type}:{source}:{name}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        # Best-effort description from .md frontmatter or .json "description"
        description = ""
        try:
            content = _safe_read_text(f) or ""
            if f.suffix == ".md":
                fm = parse_frontmatter(content)
                description = str(fm.get("description", ""))[:200]
            elif f.suffix == ".json":
                fdata = json.loads(content)
                if isinstance(fdata, dict):
                    description = str(fdata.get("description", ""))[:200]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
        out.append({
            "name": name,
            "type": elem_type,
            "source": source,
            "path": str(f),
            "description": description,
            "preview": "",
        })
    return out


def discover_output_styles() -> list[dict[str, Any]]:
    """Discover output styles (per https://code.claude.com/docs/en/output-styles.md).

    Locations:
    - ~/.claude/output-styles/<name>.md (user)
    - .claude/output-styles/<name>.md (project)
    - <plugin-root>/output-styles/<name>.md (plugin-shipped)
    """
    elements: list[dict[str, Any]] = []
    seen: set[str] = set()
    cwd = get_cwd()
    elements.extend(_discover_styled_files_in_dir(
        get_claude_dir(), "user", "output-styles", "output-style", (".md",), seen
    ))
    elements.extend(_discover_styled_files_in_dir(
        cwd / ".claude", "project", "output-styles", "output-style", (".md",), seen
    ))
    plugin_cache = get_claude_dir() / "plugins" / "cache"
    if plugin_cache.exists():
        for marketplace in plugin_cache.iterdir():
            if not marketplace.is_dir():
                continue
            for plugin in marketplace.iterdir():
                if not plugin.is_dir():
                    continue
                for version in plugin.iterdir():
                    if not version.is_dir():
                        continue
                    src = f"plugin:{marketplace.name}/{plugin.name}"
                    elements.extend(_discover_styled_files_in_dir(
                        version, src, "output-styles", "output-style",
                        (".md",), seen
                    ))
    return elements


def discover_themes() -> list[dict[str, Any]]:
    """Discover themes (per CC v2.1.118+ ~/.claude/themes/ and plugin themes/).

    Locations:
    - ~/.claude/themes/<name>.json (user-only — themes are global per
      claude-directory.md "themes/" section)
    - <plugin-root>/themes/<name>.json (plugin-shipped, v2.1.118+)
    """
    elements: list[dict[str, Any]] = []
    seen: set[str] = set()
    elements.extend(_discover_styled_files_in_dir(
        get_claude_dir(), "user", "themes", "theme", (".json",), seen
    ))
    plugin_cache = get_claude_dir() / "plugins" / "cache"
    if plugin_cache.exists():
        for marketplace in plugin_cache.iterdir():
            if not marketplace.is_dir():
                continue
            for plugin in marketplace.iterdir():
                if not plugin.is_dir():
                    continue
                for version in plugin.iterdir():
                    if not version.is_dir():
                        continue
                    src = f"plugin:{marketplace.name}/{plugin.name}"
                    elements.extend(_discover_styled_files_in_dir(
                        version, src, "themes", "theme", (".json",), seen
                    ))
    return elements


def _extract_body_preview(content: str, max_len: int = 500) -> str:
    """Extract body preview from markdown content, skipping YAML frontmatter."""
    if content.startswith("---"):
        end_idx = content.find("\n---", 3)
        if end_idx != -1:
            return content[end_idx + 4 :].strip()[:max_len]
    return content[:max_len]


def extract_use_context(content: str, max_len: int = 500) -> str:
    """Extract usage-context text from a matching heading section in markdown content.

    Scans for headings (# or ##) matching usage-related patterns (e.g. "When to Use",
    "Use Cases", "Usage"). Returns the body text under that heading, up to the next
    heading or end of content. Skips YAML frontmatter before scanning.

    Args:
        content: Raw markdown file content (may include YAML frontmatter).
        max_len: Maximum character length of the returned text.

    Returns:
        Extracted section text (stripped, capped at max_len), or "" if no match.
    """
    # Patterns to match against heading text (case-insensitive)
    heading_patterns = [
        "when to use",
        "use this skill",
        "use cases",
        "usage",
        "when should",
        "use this when",
        "intended for",
        "designed for",
    ]

    # Skip YAML frontmatter
    body = content
    if content.startswith("---"):
        end_idx = content.find("\n---", 3)
        if end_idx != -1:
            body = content[end_idx + 4 :]

    lines = body.split("\n")
    capturing = False
    captured: list[str] = []

    for line in lines:
        stripped = line.strip()
        # Check if this line is a heading (starts with #)
        if stripped.startswith("#"):
            if capturing:
                # Hit the next heading -- stop capturing
                break
            # Check if this heading matches any of our patterns
            # Remove leading #s and whitespace to get heading text
            heading_text = stripped.lstrip("#").strip().lower()
            for pattern in heading_patterns:
                if pattern in heading_text:
                    capturing = True
                    break
        elif capturing:
            captured.append(line)

    if not captured:
        return ""

    result = "\n".join(captured).strip()
    return result[:max_len]


def discover_elements(
    locations: list[tuple[str, str, Path]],
    specific_name: str | None = None,
) -> list[dict[str, Any]]:
    """Discover all elements in all provided locations.

    Returns basic metadata only - NO keyword extraction.

    Args:
        locations: List of (source, element_type, dir_path) tuples
        specific_name: If provided, only discover this specific element

    Returns:
        List of element metadata dictionaries
    """
    elements: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for source, element_type, elem_dir in locations:
        if not elem_dir.exists():
            continue

        if element_type == "skill":
            # Skills: <dir>/<name>/SKILL.md (subdirectory with SKILL.md)
            try:
                skill_entries = sorted(elem_dir.iterdir())
            except OSError as e:
                print(f"  Warning: Cannot read {elem_dir}: {e}", file=sys.stderr)
                continue
            for skill_path in skill_entries:
                if not skill_path.is_dir():
                    continue
                if specific_name and skill_path.name.lower() != specific_name.lower():
                    continue
                skill_md = skill_path / "SKILL.md"
                if not skill_md.exists():
                    continue
                # Use type-prefixed key to avoid cross-type name collisions
                dedup_key = f"skill:{skill_path.name}"
                if dedup_key in seen_names:
                    continue
                try:
                    content = _safe_read_text(skill_md) or ""
                    frontmatter = parse_frontmatter(content)
                    body = _extract_body_preview(content)
                    use_ctx = extract_use_context(content)
                    entry: dict[str, Any] = {
                        "name": frontmatter.get("name") or skill_path.name,
                        "path": str(skill_md),
                        "source": source,
                        "type": "skill",
                        "description": frontmatter.get("description", "")[:200],
                        "preview": body,
                        "use_context": use_ctx,
                    }
                    # AgentSkills open standard metadata (agentskills.io)
                    # Extract fields that improve indexing quality
                    if frontmatter.get("metadata"):
                        meta = frontmatter["metadata"]
                        if isinstance(meta, dict):
                            entry["agentskills_metadata"] = meta
                    if frontmatter.get("compatibility"):
                        entry["compatibility"] = str(
                            frontmatter["compatibility"]
                        )[:500]
                    elements.append(entry)
                    seen_names.add(dedup_key)
                except (OSError, UnicodeDecodeError) as e:
                    print(f"Warning: Cannot read {skill_md}: {e}", file=sys.stderr)
        else:
            # Agents, commands, rules: <dir>/<name>.md (direct .md files)
            try:
                md_entries = sorted(elem_dir.iterdir())
            except OSError as e:
                print(f"  Warning: Cannot read {elem_dir}: {e}", file=sys.stderr)
                continue
            for md_file in md_entries:
                if not md_file.is_file():
                    continue
                if not md_file.name.endswith(".md"):
                    continue
                if md_file.name.lower() in ("readme.md", "skill.md"):
                    continue

                elem_name = md_file.stem.lower()
                if specific_name and elem_name != specific_name.lower():
                    continue
                # Use type-prefixed key to avoid cross-type name collisions
                dedup_key = f"{element_type}:{elem_name}"
                if dedup_key in seen_names:
                    continue

                try:
                    content = _safe_read_text(md_file) or ""
                    frontmatter = parse_frontmatter(content)

                    # Extract description per type
                    if element_type == "rule" and not frontmatter.get("description"):
                        # Rules may lack frontmatter -- extract from first paragraph
                        body_text = content
                        if content.startswith("---"):
                            end_idx = content.find("\n---", 3)
                            if end_idx != -1:
                                body_text = content[end_idx + 4 :].strip()
                        # Skip headings, get first real paragraph
                        description = ""
                        for line in body_text.split("\n"):
                            line = line.strip()
                            if (
                                line
                                and not line.startswith("#")
                                and not line.startswith("---")
                            ):
                                description = line[:200]
                                break
                    else:
                        description = frontmatter.get("description", "")[:200]

                    body = _extract_body_preview(content)
                    use_ctx = extract_use_context(content)

                    elements.append(
                        {
                            "name": frontmatter.get("name") or elem_name,
                            "path": str(md_file),
                            "source": source,
                            "type": element_type,
                            "description": description,
                            "preview": body,
                            "use_context": use_ctx,
                        }
                    )
                    seen_names.add(dedup_key)
                except (OSError, UnicodeDecodeError) as e:
                    print(f"Warning: Cannot read {md_file}: {e}", file=sys.stderr)

    return elements


def generate_checklist(elements: list[dict[str, Any]], batch_size: int = 10) -> str:
    """Generate a markdown checklist with batches for parallel agent processing.

    Args:
        elements: List of discovered elements with name, path, source, type
        batch_size: Number of elements per batch (for dividing among agents)

    Returns:
        Markdown formatted checklist string
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total_elements = len(elements)
    num_batches = math.ceil(total_elements / batch_size)

    lines = [
        "# PSS Element Index Checklist",
        "",
        f"**Generated:** {now}",
        f"**Total Elements:** {total_elements}",
        f"**Batch Size:** {batch_size}",
        f"**Number of Batches:** {num_batches}",
        "",
        "---",
        "",
        "## Instructions for Parallel Processing",
        "",
        "Each batch can be assigned to a separate sonnet subagent "
        "for parallel analysis.",
        "The orchestrator should:",
        "",
        "1. Spawn N subagents (one per batch)",
        "2. Assign each subagent its batch range "
        "(e.g., Agent A → Batch 1, Agent B → Batch 2)",
        "3. Each subagent reads the element file at the given path",
        "4. Each subagent generates patterns: "
        "keywords, phrases, intents, errors, triggers",
        "5. Each subagent marks entries as complete with [x]",
        "6. Orchestrator collects all results and compiles the final index",
        "",
        "---",
        "",
    ]

    # Generate batches
    for batch_num in range(num_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, total_elements)
        batch_elements = elements[start_idx:end_idx]

        # Batch header with agent assignment suggestion
        if batch_num < 26:
            agent_letter = chr(ord("A") + batch_num)
        else:
            agent_letter = chr(ord("A") + batch_num // 26 - 1) + chr(
                ord("A") + batch_num % 26
            )
        batch_range = f"{start_idx + 1}-{end_idx}"
        lines.append(f"## Batch {batch_num + 1} ({batch_range}) - Agent {agent_letter}")
        lines.append("")
        lines.append(f"**Elements in this batch:** {len(batch_elements)}")
        lines.append("")

        # Add each element as a checkbox item
        for i, elem in enumerate(batch_elements, start=start_idx + 1):
            elem_name = elem["name"]
            elem_path = elem["path"]
            elem_source = elem["source"]
            elem_type = elem.get("type", "skill")
            lines.append(f"- [ ] **{i}.** `{elem_name}` [{elem_source}] ({elem_type})")
            lines.append(f"  - Path: `{elem_path}`")
            if elem.get("description"):
                desc = elem["description"]
                if len(desc) > 100:
                    desc = desc[:100] + "..."
                lines.append(f"  - Description: {desc}")
            lines.append("")

        lines.append("---")
        lines.append("")

    # Add summary section for results
    lines.extend(
        [
            "## Results Summary",
            "",
            "After all batches are complete, "
            "the orchestrator should compile results here:",
            "",
            "| Batch | Agent | Elements Processed | Status |",
            "|-------|-------|------------------|--------|",
        ]
    )

    for batch_num in range(num_batches):
        if batch_num < 26:
            agent_letter = chr(ord("A") + batch_num)
        else:
            agent_letter = chr(ord("A") + batch_num // 26 - 1) + chr(
                ord("A") + batch_num % 26
            )
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, total_elements)
        batch_count = end_idx - start_idx
        lines.append(
            f"| {batch_num + 1} | Agent {agent_letter} | {batch_count} | ⏳ Pending |"
        )

    lines.extend(
        [
            "",
            "---",
            "",
            "## Output Location",
            "",
            "The final compiled index should be saved to:",
            "```",
            "~/.claude/cache/skill-index.json",
            "```",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PSS - Discover ALL elements (skills, agents, commands, rules, MCP, LSP) available to Claude Code"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--jsonl",
        action="store_true",
        help="Output one JSON object per line (name, type, source, path, description)",
    )
    parser.add_argument(
        "--name", type=str, help="Only discover specific element by name"
    )
    parser.add_argument(
        "--project-only", action="store_true", help="Only scan current project elements"
    )
    parser.add_argument(
        "--user-only", action="store_true", help="Only scan user-level elements"
    )
    # All projects scanning
    parser.add_argument(
        "--all-projects",
        action="store_true",
        help="Scan ALL projects registered in ~/.claude.json (comprehensive indexing)",
    )
    # Inactive plugin filtering
    parser.add_argument(
        "--exclude-inactive-plugins",
        action="store_true",
        help="Skip plugins disabled in ~/.claude/settings.json enabledPlugins",
    )
    parser.add_argument(
        "--type",
        type=str,
        help=(
            "Comma-separated element types to discover "
            "(skill,agent,command,rule,mcp,lsp,hook,plugin,monitor,output-style,theme,marketplace). "
            "Default: all"
        ),
    )
    # Checklist mode arguments
    parser.add_argument(
        "--checklist",
        action="store_true",
        help="Generate markdown checklist with batches for parallel agent processing",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of elements per batch for checklist (default: 10)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path for checklist "
        "(default: stdout or ~/.claude/cache/skill-checklist.md)",
    )

    args = parser.parse_args()

    # Validate --batch-size is positive
    if (
        hasattr(args, "batch_size")
        and args.batch_size is not None
        and args.batch_size <= 0
    ):
        parser.error("--batch-size must be a positive integer")

    # Validate --type values against known element types.
    # Mirrors the ElementType enum in rust/skill-suggester/src/temporal.rs.
    # `channel` is intentionally absent: channels are MCP-server capabilities
    # discovered at runtime via the MCP wire protocol, not persistable
    # filesystem artifacts.
    VALID_TYPES = {
        "skill", "agent", "command", "rule", "mcp", "lsp",
        "hook", "plugin", "monitor", "output-style", "theme", "marketplace",
    }
    if args.type:
        for t in args.type.split(","):
            t = t.strip()
            if t not in VALID_TYPES:
                parser.error(
                    f"Unknown element type: {t}. Valid types: {', '.join(sorted(VALID_TYPES))}"
                )

    # Determine if we should scan all projects (comprehensive indexing)
    # Skip if --project-only or --user-only is specified
    scan_all_projects = args.all_projects and not (args.project_only or args.user_only)

    # Parse element type filter
    element_types = None
    if args.type:
        element_types = [t.strip() for t in args.type.split(",")]

    all_locations = get_all_element_locations(
        scan_all_projects=scan_all_projects,
        element_types=element_types,
        exclude_inactive_plugins=args.exclude_inactive_plugins,
    )

    if args.project_only:
        all_locations = [
            (s, t, p) for s, t, p in all_locations if s.startswith("project")
        ]
    elif args.user_only:
        all_locations = [
            (s, t, p) for s, t, p in all_locations if s.startswith("user")
        ]

    elements = discover_elements(all_locations, args.name)

    # Discover MCP servers (if type filter includes mcp or no filter)
    if not element_types or "mcp" in element_types:
        mcp_servers = discover_mcp_servers(
            scan_all_projects=scan_all_projects,
            exclude_inactive_plugins=args.exclude_inactive_plugins,
        )
        elements.extend(mcp_servers)

    # Discover LSP servers (if type filter includes lsp or no filter)
    if not element_types or "lsp" in element_types:
        lsp_servers = discover_lsp_servers()
        elements.extend(lsp_servers)

    # Phase 2 (TRDD-152e697f): the temporal index also tracks hooks, plugins,
    # monitors, output styles, themes, and marketplaces. These flow through
    # the same JSONL pipe as skills/agents so the events table picks up
    # install/remove/version-change deltas for them.
    if not element_types or "hook" in element_types:
        elements.extend(discover_hooks(scan_all_projects=scan_all_projects))
    if not element_types or "plugin" in element_types:
        elements.extend(discover_plugins())
    if not element_types or "marketplace" in element_types:
        elements.extend(discover_marketplaces())
    if not element_types or "monitor" in element_types:
        elements.extend(discover_monitors())
    if not element_types or "output-style" in element_types:
        elements.extend(discover_output_styles())
    if not element_types or "theme" in element_types:
        elements.extend(discover_themes())

    # Apply source filter to MCP/LSP results too.
    # Sources use prefixes like "project:agentskills", "user:codex", "plugin:name"
    # so we match with startswith() not strict equality.
    if args.project_only:
        elements = [
            e for e in elements
            if e.get("source", "").startswith("project")
        ]
    elif args.user_only:
        elements = [
            e for e in elements
            if e.get("source", "").startswith("user")
            or e.get("source") == "built-in"
        ]

    # JSONL mode: one JSON object per line with minimal fields
    if args.jsonl:
        for elem in elements:
            desc = elem.get("description", "") or ""
            if len(desc) > 200:
                desc = desc[:200]
            use_ctx = elem.get("use_context", "") or ""
            if len(use_ctx) > 500:
                use_ctx = use_ctx[:500]
            record = {
                "name": elem.get("name", ""),
                "type": elem.get("type", ""),
                "source": elem.get("source", ""),
                "path": elem.get("path", ""),
                "description": desc,
                "use_context": use_ctx,
            }
            print(json.dumps(record, ensure_ascii=False))
        return 0

    # Checklist mode: generate markdown checklist with batches
    if args.checklist:
        checklist_content = generate_checklist(elements, args.batch_size)

        if args.output:
            output_path = Path(args.output)
        else:
            # Default output path
            cache_dir = get_claude_dir() / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            output_path = cache_dir / "skill-checklist.md"

        output_path.write_text(checklist_content, encoding="utf-8")
        print(f"Checklist written to: {output_path}")
        num_batches = math.ceil(len(elements) / args.batch_size)
        print(f"  {len(elements)} elements in {num_batches} batches")
        return 0

    # JSON mode
    if args.json:
        print(json.dumps({"elements": elements, "count": len(elements)}, indent=2))
    else:
        # Default text mode
        print(f"Discovered {len(elements)} elements:\n")
        for elem in elements:
            print(f"  {elem['name']} [{elem['source']}] ({elem.get('type', 'skill')})")
            print(f"    Path: {elem['path']}")
            if elem.get("description"):
                desc = elem["description"]
                if len(desc) > 80:
                    desc = desc[:80] + "..."
                print(f"    Desc: {desc}")
            print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
