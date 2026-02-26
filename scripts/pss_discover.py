#!/usr/bin/env python3
"""
Perfect Skill Suggester - Element Discovery Script.

Find ALL Claude Code elements (skills, agents, commands, rules, MCP servers,
LSP servers) available across ALL projects.

This script discovers element locations from:
- User-level elements (~/.claude/{skills,agents,commands,rules}/)
- All projects registered in ~/.claude.json
- Plugin caches and local plugins
- MCP server configs (~/.claude.json mcpServers, .mcp.json)
- LSP servers enabled in ~/.claude/settings.json

This script ONLY discovers element locations. It does NOT analyze or extract keywords.
Keyword/phrase extraction is done by the agent reading each element.

Usage:
    python3 pss_discover.py [--json] [--project-only] [--user-only]
    python3 pss_discover.py --checklist [--batch-size 10] [--output FILE]
    python3 pss_discover.py --all-projects
    python3 pss_discover.py --type skill,agent  # Filter to specific types

Output Modes:
    Default: List of element paths with metadata (name, path, source, type)
    --json: JSON format for programmatic use
    --checklist: Markdown checklist with batches for parallel agent processing

Checklist Format:
    The checklist divides elements into batches (default 10 per batch) for parallel
    agent processing. Each batch can be assigned to a different haiku subagent.
"""

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def get_home_dir() -> Path:
    """Get user home directory."""
    return Path.home()


def get_cwd() -> Path:
    """Get current working directory."""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        return Path(project_dir)
    return Path.cwd()


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
        config_data = json.loads(config_path.read_text(encoding="utf-8"))
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
    except Exception as e:
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
) -> list[tuple[str, str, Path]]:
    """Get all locations where Claude Code elements can be found.

    Returns: list of (source, element_type, dir_path) tuples.
    element_type is one of: "skill", "agent", "command", "rule"

    Args:
        scan_all_projects: If True, scan all projects registered in ~/.claude.json
        element_types: If provided, only scan these types (e.g., ["skill", "agent"]).
                       None means scan all types.
    """
    # Determine which subdirectories to scan
    if element_types:
        # Map type names back to subdirectory names
        type_set = set(element_types)
        subdirs_to_scan = {k: v for k, v in ELEMENT_SUBDIRS.items() if v in type_set}
    else:
        subdirs_to_scan = ELEMENT_SUBDIRS

    locations: list[tuple[str, str, Path]] = []
    home = get_home_dir()
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
    _add_element_dirs(home / ".claude", "user", include_rules=True)

    # 2. Current project-level elements: .claude/{skills,agents,commands,rules}/
    _add_element_dirs(cwd / ".claude", "project", include_rules=True)

    # 3. Plugin cache: ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/
    plugin_cache = home / ".claude" / "plugins" / "cache"
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
                    plugin_source = f"plugin:{marketplace.name}/{plugin.name}"
                    # Scan for element subdirectories in the plugin version dir
                    _add_element_dirs(version, plugin_source, include_rules=False)
                    # Legacy layout (SKILL.md directly in version dir) is NOT supported
                    # for multi-type indexing because the version number becomes the skill name.
                    # Plugins should use the skills/ subdirectory layout instead.

    # 4. Local plugins: ~/.claude/plugins/<plugin>/
    user_plugins = home / ".claude" / "plugins"
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


def parse_frontmatter(content: str) -> dict[str, Any]:
    """Parse YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}

    end_idx = content.find("\n---", 3)
    if end_idx == -1:
        return {}

    frontmatter_text = content[3:end_idx].strip()
    result: dict[str, Any] = {}
    for line in frontmatter_text.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            result[key] = value

    return result


def discover_mcp_servers(scan_all_projects: bool = False) -> list[dict[str, Any]]:
    """Discover MCP servers from JSON config files.

    Sources:
    1. ~/.claude.json -> mcpServers key (user-level)
    2. .mcp.json in current project (project-level)
    3. (if scan_all_projects) Each project's .mcp.json
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
            data = json.loads(config_path.read_text(encoding="utf-8"))
            mcp_servers = data.get("mcpServers", {})
            for name, config in mcp_servers.items():
                if name in seen_names:
                    continue
                seen_names.add(name)

                # Try to get description from README.md in servers dir
                description = ""
                server_dir = home / ".claude" / "servers" / name
                readme = server_dir / "README.md"
                if readme.exists():
                    try:
                        readme_text = readme.read_text(encoding="utf-8")
                        # First non-empty line after any heading
                        for line in readme_text.split("\n"):
                            line = line.strip()
                            if line and not line.startswith("#"):
                                description = line[:200]
                                break
                    except Exception:
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
        except Exception as e:
            print(f"Warning: Error reading {config_path}: {e}", file=sys.stderr)

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
    settings_path = get_home_dir() / ".claude" / "settings.json"

    if not settings_path.exists():
        return servers

    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
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

    except Exception as e:
        print(f"Warning: Error reading {settings_path}: {e}", file=sys.stderr)

    return servers


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
                    content = skill_md.read_text(encoding="utf-8")
                    frontmatter = parse_frontmatter(content)
                    # Only look for frontmatter end delimiter if content starts with frontmatter
                    if content.startswith("---"):
                        body_start = content.find("\n---", 3)
                        if body_start != -1:
                            body = content[body_start + 4 :].strip()[:500]
                        else:
                            body = content[:500]
                    else:
                        body = content[:500]
                    elements.append(
                        {
                            "name": frontmatter.get("name") or skill_path.name,
                            "path": str(skill_md),
                            "source": source,
                            "type": "skill",
                            "description": frontmatter.get("description", "")[:200],
                            "preview": body,
                        }
                    )
                    seen_names.add(dedup_key)
                except Exception as e:
                    print(f"Error reading {skill_md}: {e}", file=sys.stderr)
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
                if specific_name and elem_name != specific_name:
                    continue
                # Use type-prefixed key to avoid cross-type name collisions
                dedup_key = f"{element_type}:{elem_name}"
                if dedup_key in seen_names:
                    continue

                try:
                    content = md_file.read_text(encoding="utf-8")
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

                    # Extract body preview - only parse frontmatter delimiter if present
                    if content.startswith("---"):
                        body_start = content.find("\n---", 3)
                        if body_start != -1:
                            body = content[body_start + 4 :].strip()[:500]
                        else:
                            body = content[:500]
                    else:
                        body = content[:500]

                    elements.append(
                        {
                            "name": frontmatter.get("name") or elem_name,
                            "path": str(md_file),
                            "source": source,
                            "type": element_type,
                            "description": description,
                            "preview": body,
                        }
                    )
                    seen_names.add(dedup_key)
                except Exception as e:
                    print(f"Error reading {md_file}: {e}", file=sys.stderr)

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
        "Each batch can be assigned to a separate haiku subagent "
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
            agent_letter = chr(ord("A") + batch_num // 26 - 1) + chr(ord("A") + batch_num % 26)
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
            agent_letter = chr(ord("A") + batch_num // 26 - 1) + chr(ord("A") + batch_num % 26)
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
        "--skill", type=str, help="Only discover specific element by name"
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
    parser.add_argument(
        "--type",
        type=str,
        help="Comma-separated element types to discover (skill,agent,command,rule,mcp,lsp). Default: all",
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

    # Validate --type values against known element types
    VALID_TYPES = {"skill", "agent", "command", "rule", "mcp", "lsp"}
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
    )

    if args.project_only:
        all_locations = [(s, t, p) for s, t, p in all_locations if s == "project"]
    elif args.user_only:
        all_locations = [(s, t, p) for s, t, p in all_locations if s == "user"]

    elements = discover_elements(all_locations, args.skill)

    # Discover MCP servers (if type filter includes mcp or no filter)
    if not element_types or "mcp" in element_types:
        mcp_servers = discover_mcp_servers(scan_all_projects=scan_all_projects)
        elements.extend(mcp_servers)

    # Discover LSP servers (if type filter includes lsp or no filter)
    if not element_types or "lsp" in element_types:
        lsp_servers = discover_lsp_servers()
        elements.extend(lsp_servers)

    # Apply source filter to MCP/LSP results too
    if args.project_only:
        elements = [e for e in elements if e.get("source") == "project"]
    elif args.user_only:
        elements = [e for e in elements if e.get("source") in ("user", "built-in")]

    # Checklist mode: generate markdown checklist with batches
    if args.checklist:
        checklist_content = generate_checklist(elements, args.batch_size)

        if args.output:
            output_path = Path(args.output)
        else:
            # Default output path
            cache_dir = Path.home() / ".claude" / "cache"
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
