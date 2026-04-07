#!/usr/bin/env python3
"""Add standalone elements to existing Claude Code plugins.

Usage:
    uv run python scripts/pss_add_element.py --plugin <path> --type <type> --source <path> [--validate] [--dry-run] [--force]

Element types:
    skill        - Directory containing SKILL.md (+ references/, scripts/)
    agent        - Agent definition .md file with frontmatter
    command      - Command definition .md file with frontmatter (+ optional subdir)
    hook         - hooks.json file (merged into existing hooks)
    rule         - Rule .md file (copied to rules/ dir)
    mcp-server   - JSON file with MCP server config
    lsp-server   - JSON file with LSP server config
    output-style - JSON file with output style config

Exit codes:
    0 - Element added successfully
    1 - Error (duplicate, incompatible, validation failure, etc.)
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

ELEMENT_TYPES = [
    "skill",
    "agent",
    "command",
    "hook",
    "rule",
    "mcp-server",
    "lsp-server",
    "output-style",
]

# ANSI colors
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"
BOLD = "\033[1m"


def info(msg: str) -> None:
    print(f"{CYAN}[INFO]{RESET}  {msg}", file=sys.stderr)


def success(msg: str) -> None:
    print(f"{GREEN}[OK]{RESET}    {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    print(f"{YELLOW}[WARN]{RESET}  {msg}", file=sys.stderr)


def error(msg: str) -> None:
    print(f"{RED}[ERROR]{RESET} {msg}", file=sys.stderr)


def fatal(msg: str) -> NoReturn:
    error(msg)
    sys.exit(1)


# ─── Frontmatter parsing ───


def parse_frontmatter(path: Path) -> dict:
    """Parse YAML frontmatter from a .md file (between --- delimiters)."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end < 0:
        return {}
    block = text[3:end].strip()
    result = {}
    for line in block.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            result[key] = val
    return result


def extract_element_name(
    source: Path, element_type: str
) -> str:
    """Extract the element name from source path or frontmatter."""
    if element_type == "skill":
        skill_dir = source.parent if source.name == "SKILL.md" else source
        skill_md = skill_dir / "SKILL.md" if skill_dir.is_dir() else source
        if skill_md.exists():
            fm = parse_frontmatter(skill_md)
            if fm.get("name"):
                return fm["name"]
        return skill_dir.name

    if element_type in ("agent", "command", "rule"):
        if source.suffix == ".md":
            fm = parse_frontmatter(source)
            if fm.get("name"):
                return fm["name"]
        return source.stem

    if element_type == "hook":
        return "hooks"

    if element_type in ("mcp-server", "lsp-server", "output-style"):
        # Name comes from the JSON content
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "name" in data:
                return data["name"]
        except (json.JSONDecodeError, OSError):
            pass
        return source.stem

    return source.stem


# ─── Duplicate and incompatibility checks ───


def check_skill_duplicate(plugin: Path, name: str) -> str | None:
    """Return error message if skill already exists, else None."""
    dest = plugin / "skills" / name
    if dest.exists():
        return f"Skill '{name}' already exists at {dest}"
    # Also check by frontmatter name in existing skills
    skills_dir = plugin / "skills"
    if skills_dir.is_dir():
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                fm = parse_frontmatter(skill_md)
                if fm.get("name") == name:
                    return (
                        f"Skill with name '{name}' already exists "
                        f"in {skill_dir.name}/"
                    )
    return None


def check_agent_duplicate(plugin: Path, name: str) -> str | None:
    agents_dir = plugin / "agents"
    if not agents_dir.is_dir():
        return None
    for md in agents_dir.glob("*.md"):
        fm = parse_frontmatter(md)
        if fm.get("name") == name or md.stem == name:
            return f"Agent '{name}' already exists at {md.name}"
    return None


def check_command_duplicate(plugin: Path, name: str) -> str | None:
    cmds_dir = plugin / "commands"
    if not cmds_dir.is_dir():
        return None
    for md in cmds_dir.glob("*.md"):
        fm = parse_frontmatter(md)
        if fm.get("name") == name or md.stem == name:
            return f"Command '{name}' already exists at {md.name}"
    return None


def check_hook_incompatibility(
    plugin: Path, source: Path
) -> str | None:
    """Check if new hooks conflict with existing hooks."""
    existing_hooks_path = plugin / "hooks" / "hooks.json"
    if not existing_hooks_path.exists():
        return None  # No existing hooks, no conflict

    try:
        existing = json.loads(
            existing_hooks_path.read_text(encoding="utf-8")
        )
        new_hooks = json.loads(
            source.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError) as e:
        return f"Cannot parse hooks JSON: {e}"

    existing_events = existing.get("hooks", {})
    new_events = new_hooks.get("hooks", {})

    # Check for duplicate hook commands on the same event
    for event, new_entries in new_events.items():
        if event not in existing_events:
            continue
        existing_cmds = set()
        for group in existing_events[event]:
            for hook in group.get("hooks", []):
                cmd = hook.get("command", "")
                if cmd:
                    existing_cmds.add(cmd)
        for group in (
            new_entries if isinstance(new_entries, list) else [new_entries]
        ):
            for hook in group.get("hooks", []):
                cmd = hook.get("command", "")
                if cmd and cmd in existing_cmds:
                    return (
                        f"Hook command already registered for "
                        f"{event}: {cmd[:80]}"
                    )
    return None


def check_rule_duplicate(plugin: Path, name: str) -> str | None:
    rules_dir = plugin / "rules"
    if not rules_dir.is_dir():
        return None
    filename = f"{name}.md" if not name.endswith(".md") else name
    if (rules_dir / filename).exists():
        return f"Rule '{filename}' already exists in rules/"
    return None


def check_mcp_duplicate(
    plugin: Path, source: Path
) -> str | None:
    """Check if MCP server name conflicts with existing config."""
    try:
        new_config = json.loads(
            source.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError) as e:
        return f"Cannot parse MCP config: {e}"

    server_name = new_config.get("name", "")
    if not server_name:
        return "MCP config missing 'name' field"

    # Check .mcp.json
    mcp_json = plugin / ".mcp.json"
    if mcp_json.exists():
        try:
            existing = json.loads(
                mcp_json.read_text(encoding="utf-8")
            )
            servers = existing.get("mcpServers", {})
            if server_name in servers:
                return (
                    f"MCP server '{server_name}' already "
                    f"defined in .mcp.json"
                )
        except (json.JSONDecodeError, OSError):
            pass

    return None


def check_lsp_duplicate(
    plugin: Path, source: Path
) -> str | None:
    """Check .lsp.json (map keyed by server name) per official spec."""
    try:
        new_config = json.loads(
            source.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError) as e:
        return f"Cannot parse LSP config: {e}"

    server_name = new_config.get("name", "")
    if not server_name:
        return "LSP config missing 'name' field"

    # Official spec: LSP config lives in .lsp.json as a map
    lsp_json = plugin / ".lsp.json"
    if lsp_json.exists():
        try:
            existing = json.loads(
                lsp_json.read_text(encoding="utf-8")
            )
            if server_name in existing:
                return (
                    f"LSP server '{server_name}' already "
                    f"defined in .lsp.json"
                )
        except (json.JSONDecodeError, OSError):
            pass

    return None


def check_output_style_duplicate(
    plugin: Path, source: Path
) -> str | None:
    """Check output-styles/ directory for duplicate .md files (official spec)."""
    if not source.exists() or source.suffix != ".md":
        return "Output style source must be an .md file"

    styles_dir = plugin / "output-styles"
    if not styles_dir.is_dir():
        return None

    dest = styles_dir / source.name
    if dest.exists():
        return (
            f"Output style '{source.name}' already exists "
            f"in output-styles/"
        )

    return None


# ─── Element addition ───


def add_skill(
    plugin: Path, source: Path, dry_run: bool
) -> bool:
    skill_dir = source.parent if source.name == "SKILL.md" else source
    if not skill_dir.is_dir():
        fatal(f"Skill source must be a directory: {skill_dir}")

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        fatal(f"SKILL.md not found in {skill_dir}")

    dest = plugin / "skills" / skill_dir.name
    if dry_run:
        info(f"[DRY-RUN] Would copy {skill_dir} → {dest}")
        return True

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill_dir, dest, dirs_exist_ok=False)
    success(f"Added skill: {skill_dir.name}")
    return True


def add_agent(
    plugin: Path, source: Path, dry_run: bool
) -> bool:
    if not source.exists() or source.suffix != ".md":
        fatal(f"Agent source must be an .md file: {source}")

    fm = parse_frontmatter(source)
    if not fm.get("name"):
        warn("Agent .md has no 'name' in frontmatter")

    dest_dir = plugin / "agents"
    dest = dest_dir / source.name
    if dry_run:
        info(f"[DRY-RUN] Would copy {source} → {dest}")
        return True

    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    success(f"Added agent: {source.name}")
    return True


def add_command(
    plugin: Path, source: Path, dry_run: bool
) -> bool:
    if not source.exists() or source.suffix != ".md":
        fatal(f"Command source must be an .md file: {source}")

    fm = parse_frontmatter(source)
    if not fm.get("name"):
        warn("Command .md has no 'name' in frontmatter")

    dest_dir = plugin / "commands"
    dest = dest_dir / source.name
    if dry_run:
        info(f"[DRY-RUN] Would copy {source} → {dest}")
        return True

    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)

    # Copy command subdirectory if present (e.g., pss-status/)
    subdir = source.parent / source.stem
    if subdir.is_dir():
        dest_subdir = dest_dir / source.stem
        shutil.copytree(subdir, dest_subdir, dirs_exist_ok=False)
        success(f"Added command + subdir: {source.name}")
    else:
        success(f"Added command: {source.name}")
    return True


def add_hook(
    plugin: Path, source: Path, dry_run: bool
) -> bool:
    if not source.exists():
        fatal(f"Hook source not found: {source}")

    try:
        new_hooks = json.loads(
            source.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as e:
        fatal(f"Invalid hooks JSON: {e}")

    hooks_dir = plugin / "hooks"
    hooks_file = hooks_dir / "hooks.json"

    if hooks_file.exists():
        try:
            existing = json.loads(
                hooks_file.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError:
            fatal(f"Existing hooks.json is corrupt: {hooks_file}")
    else:
        existing = {"hooks": {}}

    # Merge: for each event in new_hooks, append entries
    merged = existing.copy()
    merged_hooks = merged.setdefault("hooks", {})
    for event, entries in new_hooks.get("hooks", {}).items():
        if event not in merged_hooks:
            merged_hooks[event] = []
        entry_list = (
            entries if isinstance(entries, list) else [entries]
        )
        merged_hooks[event].extend(entry_list)

    # Preserve description from either source
    if "description" in new_hooks and "description" not in merged:
        merged["description"] = new_hooks["description"]

    if dry_run:
        info(
            f"[DRY-RUN] Would merge {len(new_hooks.get('hooks', {}))} "
            f"event(s) into {hooks_file}"
        )
        return True

    hooks_dir.mkdir(parents=True, exist_ok=True)
    hooks_file.write_text(
        json.dumps(merged, indent=2) + "\n", encoding="utf-8"
    )
    events = list(new_hooks.get("hooks", {}).keys())
    success(f"Merged hooks for events: {', '.join(events)}")
    return True


def add_rule(
    plugin: Path, source: Path, dry_run: bool
) -> bool:
    if not source.exists() or source.suffix != ".md":
        fatal(f"Rule source must be an .md file: {source}")

    dest_dir = plugin / "rules"
    dest = dest_dir / source.name
    if dry_run:
        info(f"[DRY-RUN] Would copy {source} → {dest}")
        return True

    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    success(f"Added rule: {source.name}")
    return True


def add_mcp_server(
    plugin: Path, source: Path, dry_run: bool
) -> bool:
    try:
        config = json.loads(
            source.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError) as e:
        fatal(f"Cannot parse MCP config: {e}")

    name = config.get("name", "")
    if not name:
        fatal("MCP config must have a 'name' field")

    # Build the server entry (name is the key, rest is value)
    server_entry = {
        k: v for k, v in config.items() if k != "name"
    }

    mcp_json = plugin / ".mcp.json"
    if mcp_json.exists():
        try:
            existing = json.loads(
                mcp_json.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError:
            fatal(f"Existing .mcp.json is corrupt: {mcp_json}")
    else:
        existing = {"mcpServers": {}}

    if dry_run:
        info(f"[DRY-RUN] Would add MCP server '{name}' to .mcp.json")
        return True

    existing.setdefault("mcpServers", {})[name] = server_entry
    mcp_json.write_text(
        json.dumps(existing, indent=2) + "\n", encoding="utf-8"
    )
    success(f"Added MCP server: {name}")
    return True


def add_lsp_server(
    plugin: Path, source: Path, dry_run: bool
) -> bool:
    """Add LSP server to .lsp.json (map keyed by name, per official spec)."""
    try:
        config = json.loads(
            source.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError) as e:
        fatal(f"Cannot parse LSP config: {e}")

    name = config.get("name", "")
    if not name:
        fatal("LSP config must have a 'name' field")

    # Official spec: .lsp.json is a map { "name": { config } }
    # The 'name' field is used as the key, rest is the value
    server_entry = {
        k: v for k, v in config.items() if k != "name"
    }

    lsp_json = plugin / ".lsp.json"
    if lsp_json.exists():
        try:
            existing = json.loads(
                lsp_json.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError:
            fatal(f"Existing .lsp.json is corrupt: {lsp_json}")
    else:
        existing = {}

    if dry_run:
        info(
            f"[DRY-RUN] Would add LSP server '{name}' to .lsp.json"
        )
        return True

    existing[name] = server_entry
    lsp_json.write_text(
        json.dumps(existing, indent=2) + "\n", encoding="utf-8"
    )
    success(f"Added LSP server: {name}")
    return True


def add_output_style(
    plugin: Path, source: Path, dry_run: bool
) -> bool:
    """Copy output style .md file to output-styles/ directory (official spec)."""
    if not source.exists() or source.suffix != ".md":
        fatal(f"Output style source must be an .md file: {source}")

    dest_dir = plugin / "output-styles"
    dest = dest_dir / source.name
    if dry_run:
        info(f"[DRY-RUN] Would copy {source} → {dest}")
        return True

    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    success(f"Added output style: {source.name}")
    return True


# ─── Validation ───


CPV_REPO = "Emasoft/claude-plugins-validation"
CPV_UVX_FROM = f"git+https://github.com/{CPV_REPO}"


def validate_plugin(plugin: Path) -> bool:
    """Run CPV validation via uvx remote execution."""
    info(f"Validating plugin at {plugin}...")

    if not shutil.which("uvx"):
        warn("'uvx' not found — install uv to enable CPV validation")
        return True

    result = subprocess.run(
        [
            "uvx",
            "--from", CPV_UVX_FROM,
            "--with", "pyyaml",
            "cpv-remote-validate", "plugin", str(plugin),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )

    if result.returncode == 0:
        success("Plugin validation passed.")
        return True
    elif result.returncode == 4:
        warn("Plugin validation: NIT issues (non-blocking).")
        return True
    else:
        error(f"Plugin validation failed (exit {result.returncode}):")
        # Print last 20 lines of output
        lines = (result.stdout + result.stderr).strip().splitlines()
        for line in lines[-20:]:
            print(f"  {line}", file=sys.stderr)
        return False


# ─── Main dispatch ───

DUPLICATE_CHECKERS = {
    "skill": lambda p, s: check_skill_duplicate(
        p, extract_element_name(s, "skill")
    ),
    "agent": lambda p, s: check_agent_duplicate(
        p, extract_element_name(s, "agent")
    ),
    "command": lambda p, s: check_command_duplicate(
        p, extract_element_name(s, "command")
    ),
    "hook": lambda p, s: check_hook_incompatibility(p, s),
    "rule": lambda p, s: check_rule_duplicate(
        p, extract_element_name(s, "rule")
    ),
    "mcp-server": check_mcp_duplicate,
    "lsp-server": check_lsp_duplicate,
    "output-style": check_output_style_duplicate,
}

ADDERS = {
    "skill": add_skill,
    "agent": add_agent,
    "command": add_command,
    "hook": add_hook,
    "rule": add_rule,
    "mcp-server": add_mcp_server,
    "lsp-server": add_lsp_server,
    "output-style": add_output_style,
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Add standalone elements to Claude Code plugins.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--plugin",
        required=True,
        help="Path to the target plugin directory",
    )
    parser.add_argument(
        "--type",
        required=True,
        choices=ELEMENT_TYPES,
        dest="element_type",
        help="Type of element to add",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to the element source (file or directory)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run CPV validation after adding the element",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip duplicate/incompatibility checks",
    )
    args = parser.parse_args()

    plugin = Path(args.plugin).resolve()
    source = Path(args.source).resolve()

    # Validate plugin path
    plugin_json = plugin / ".claude-plugin" / "plugin.json"
    if not plugin_json.exists():
        fatal(
            f"Not a valid plugin directory (no .claude-plugin/plugin.json): "
            f"{plugin}"
        )

    # Validate source exists
    if not source.exists():
        fatal(f"Source not found: {source}")

    element_type = args.element_type
    name = extract_element_name(source, element_type)

    # Check duplicates/incompatibilities BEFORE printing header
    # (fatal() exits immediately — header would be confusing noise)
    if not args.force:
        checker = DUPLICATE_CHECKERS.get(element_type)
        if checker:
            issue = checker(plugin, source)
            if issue:
                fatal(f"Duplicate/incompatibility: {issue}")

    print(file=sys.stderr)
    info(f"Adding {element_type}: {name}")
    info(f"  Plugin: {plugin}")
    info(f"  Source: {source}")
    print(file=sys.stderr)

    if not args.force:
        success("No duplicates or incompatibilities found.")

    # Add the element
    adder = ADDERS.get(element_type)
    if not adder:
        fatal(f"Unknown element type: {element_type}")

    ok = adder(plugin, source, args.dry_run)
    if not ok:
        fatal(f"Failed to add {element_type}")

    # Validate if requested
    if args.validate and not args.dry_run:
        if not validate_plugin(plugin):
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
