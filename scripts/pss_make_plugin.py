#!/usr/bin/env python3
"""Generate a Claude Code plugin from an .agent.toml profile.

Reads the profile, resolves all element paths from the skill index,
copies them into a standard plugin directory structure following the
Anthropic plugin specification.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from typing import Any
from pathlib import Path

import tomllib  # Python 3.11+ (required)


def load_profile(profile_path: Path) -> dict:
    """Load and parse the .agent.toml file."""
    with open(profile_path, "rb") as f:
        return tomllib.load(f)


def load_skill_index() -> dict:
    """Load the skill index to resolve element paths."""
    from pss_paths import get_data_dir

    index_path = get_data_dir() / "skill-index.json"
    if index_path.exists():
        with open(index_path) as f:
            return json.load(f)
    print(
        "ERROR: skill-index.json not found. Run /pss-reindex-skills first.",
        file=sys.stderr,
    )
    sys.exit(1)


def resolve_element_path(name: str, index: dict) -> str | None:
    """Resolve an element name to its file path via the skill index."""
    skills = (
        index
        if isinstance(index, dict) and "skills" not in index
        else index.get("skills", index)
    )
    for _id, entry in skills.items():
        if isinstance(entry, dict) and entry.get("name") == name:
            path = entry.get("path", "")
            if path and Path(path).exists():
                return path
    return None


def resolve_element_type(name: str, index: dict) -> str:
    """Get the type of an element from the index."""
    skills = (
        index
        if isinstance(index, dict) and "skills" not in index
        else index.get("skills", index)
    )
    for _id, entry in skills.items():
        if isinstance(entry, dict) and entry.get("name") == name:
            return entry.get("type", "skill")
    return "skill"


def copy_skill(name: str, source_path: str, dest_skills_dir: Path) -> bool:
    """Copy a skill directory (SKILL.md + references/ + scripts/ + examples/)."""
    source = Path(source_path)

    # Skills are directories containing SKILL.md
    if source.name == "SKILL.md":
        skill_dir = source.parent
    else:
        skill_dir = source

    if not skill_dir.is_dir():
        print(f"  WARNING: Skill directory not found: {skill_dir}", file=sys.stderr)
        return False

    # Use the skill directory name as the destination name
    dest_dir = dest_skills_dir / skill_dir.name
    if dest_dir.exists():
        print(
            f"  WARNING: Skill directory already exists, skipping: {dest_dir.name}",
            file=sys.stderr,
        )
        return False

    # Copy the entire skill directory (SKILL.md + references/ + scripts/ + assets/)
    shutil.copytree(skill_dir, dest_dir, symlinks=True, dirs_exist_ok=False)
    return True


def copy_agent(name: str, source_path: str, dest_agents_dir: Path) -> bool:
    """Copy an agent .md file."""
    source = Path(source_path)
    if not source.exists():
        print(f"  WARNING: Agent file not found: {source}", file=sys.stderr)
        return False

    dest = dest_agents_dir / source.name
    if dest.exists():
        print(
            f"  WARNING: Agent file already exists, skipping: {source.name}",
            file=sys.stderr,
        )
        return False

    shutil.copy2(source, dest)
    return True


def copy_command(name: str, source_path: str, dest_commands_dir: Path) -> bool:
    """Copy a command .md file and its subdirectory (if any)."""
    source = Path(source_path)
    if not source.exists():
        print(f"  WARNING: Command file not found: {source}", file=sys.stderr)
        return False

    dest = dest_commands_dir / source.name
    if dest.exists():
        print(
            f"  WARNING: Command file already exists, skipping: {source.name}",
            file=sys.stderr,
        )
        return False

    shutil.copy2(source, dest)

    # Check for command subdirectory (e.g., pss-setup-agent/execution.md)
    subdir = source.parent / source.stem
    if subdir.is_dir():
        dest_subdir = dest_commands_dir / source.stem
        shutil.copytree(subdir, dest_subdir, symlinks=True, dirs_exist_ok=False)

    return True


def copy_rule(name: str, source_path: str, dest_rules_dir: Path) -> bool:
    """Copy a rule .md file."""
    source = Path(source_path)
    if not source.exists():
        # Try common rule locations
        for candidate in [
            Path.home() / ".claude" / "rules" / f"{name}.md",
            Path(".claude") / "rules" / f"{name}.md",
        ]:
            if candidate.exists():
                source = candidate
                break
        else:
            print(f"  WARNING: Rule file not found: {name}", file=sys.stderr)
            return False

    dest = dest_rules_dir / source.name
    if dest.exists():
        return False

    shutil.copy2(source, dest)
    return True


def generate_plugin_json(
    plugin_name: str,
    agent_name: str,
    description: str,
    profile: dict,
    version: str = "0.1.0",
) -> dict:
    """Generate the plugin.json manifest."""
    manifest = {
        "name": plugin_name,
        "description": description,
        "version": version,
        "author": {
            "name": os.environ.get("GIT_AUTHOR", os.environ.get("USER", "Unknown")),
        },
    }

    # Add keywords from the profile's tech stack and domains
    keywords = []
    req = profile.get("requirements", {})
    if req.get("tech_stack"):
        keywords.extend(req["tech_stack"])
    keywords.append(agent_name)
    if keywords:
        manifest["keywords"] = keywords[:10]  # Cap at 10

    # Propagate optional provenance fields from [metadata] section, if present.
    # These become plugin.json homepage/repository/license per plugins-reference.md.
    # Guard with isinstance(dict) — if a user writes `metadata = "foo"` at top
    # level, profile.get returns a string and .get(key) would crash.
    metadata = profile.get("metadata", {})
    if isinstance(metadata, dict):
        for key in ("homepage", "repository", "license"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                manifest[key] = value.strip()

    # Propagate the optional [userConfig] section verbatim into plugin.json.
    # PSS does NOT validate the nested structure — consumers must follow the
    # Claude Code plugins-reference.md userConfig schema. Pass-through only.
    user_config = profile.get("userConfig")
    if isinstance(user_config, dict) and user_config:
        manifest["userConfig"] = user_config

    # Propagate the optional [monitors] section verbatim into plugin.json.
    # Monitors is a CC v2.1.105+ top-level manifest key for background monitor
    # plugins that auto-arm at session start or on skill invoke. PSS does NOT
    # validate the nested structure — consumers must follow the Claude Code
    # plugins-reference.md monitors schema.
    monitors = profile.get("monitors")
    if isinstance(monitors, dict) and monitors:
        manifest["monitors"] = monitors

    return manifest


def generate_readme(
    plugin_name: str,
    agent_name: str,
    description: str,
    profile: dict,
    stats: dict,
) -> str:
    """Generate a README.md for the plugin."""
    lines = [
        f"# {plugin_name}",
        "",
        f"> {description}",
        "",
        f"Claude Code plugin generated from `{agent_name}.agent.toml` profile by [PSS](https://github.com/Emasoft/perfect-skill-suggester).",
        "",
        "## Contents",
        "",
    ]

    if stats.get("skills"):
        lines.append(f"### Skills ({stats['skills']})")
        for name in profile.get("skills", {}).get("primary", []):
            lines.append(f"- **{name}** (primary)")
        for name in profile.get("skills", {}).get("secondary", []):
            lines.append(f"- {name} (secondary)")
        for name in profile.get("skills", {}).get("specialized", []):
            lines.append(f"- {name} (specialized)")
        lines.append("")

    if stats.get("agents"):
        lines.append(f"### Agents ({stats['agents']})")
        for sect in ("subagents", "agents"):
            for name in profile.get(sect, {}).get("recommended", []):
                lines.append(f"- {name}")
        lines.append("")

    if stats.get("commands"):
        lines.append(f"### Commands ({stats['commands']})")
        for name in profile.get("commands", {}).get("recommended", []):
            lines.append(f"- `/{plugin_name}:{name}`")
        lines.append("")

    if stats.get("rules"):
        lines.append(f"### Rules ({stats['rules']})")
        for name in profile.get("rules", {}).get("recommended", []):
            lines.append(f"- {name}")
        lines.append("")
        lines.append(
            "> Rules are symlinked into `.claude/rules/` at session start and cleaned up at session end."
        )
        lines.append(
            f"> Symlinks are prefixed with `_plugin_{plugin_name}_` for identification."
        )
        lines.append("")

    lines.extend(
        [
            "## Installation",
            "",
            "```bash",
            f"claude plugin install /path/to/{plugin_name}",
            "```",
            "",
            "## Generated",
            "",
            f"- **Date**: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            f"- **Source profile**: `{agent_name}.agent.toml`",
            "- **Generator**: PSS `/pss-make-plugin-from-profile`",
            "",
        ]
    )

    return "\n".join(lines)


def generate_rules_hook_scripts(plugin_name: str, scripts_dir: Path) -> None:
    """Generate the SessionStart/SessionEnd hook scripts for rule symlinks.

    Rules are not a native plugin component, so we use hooks to symlink
    them into the project's .claude/rules/ at session start and clean up
    at session end.
    """
    # Prefix used to identify symlinks created by this plugin
    prefix = f"_plugin_{plugin_name}_"

    install_script = scripts_dir / "install-rules.sh"
    install_script.write_text(
        f"""#!/usr/bin/env bash
# Auto-generated by PSS — symlinks plugin rules into project .claude/rules/
# Runs on SessionStart. Reads JSON from stdin to get project cwd.
set -euo pipefail

PLUGIN_ROOT="${{CLAUDE_PLUGIN_ROOT}}"
RULES_SRC="${{PLUGIN_ROOT}}/rules"

# Read cwd from stdin JSON (SessionStart provides it)
CWD="$(cat | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null || echo "")"
[ -z "$CWD" ] && exit 0
[ ! -d "$RULES_SRC" ] && exit 0

RULES_DST="${{CWD}}/.claude/rules"
mkdir -p "$RULES_DST"

# Clean stale/broken symlinks from this plugin (e.g. after crash)
for link in "$RULES_DST"/{prefix}*.md; do
    [ -L "$link" ] && [ ! -e "$link" ] && rm -f "$link"
done

# Create fresh symlinks for each rule
for rule in "$RULES_SRC"/*.md; do
    [ -f "$rule" ] || continue
    basename="$(basename "$rule")"
    target="${{RULES_DST}}/{prefix}${{basename}}"
    ln -sf "$rule" "$target"
done

exit 0
""",
    )
    install_script.chmod(0o755)

    cleanup_script = scripts_dir / "cleanup-rules.sh"
    cleanup_script.write_text(
        f"""#!/usr/bin/env bash
# Auto-generated by PSS — removes plugin rule symlinks from project .claude/rules/
# Runs on SessionEnd (1.5s timeout — must be fast).
set -euo pipefail

CWD="$(cat | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null || echo "")"
[ -z "$CWD" ] && exit 0

RULES_DST="${{CWD}}/.claude/rules"
[ ! -d "$RULES_DST" ] && exit 0

# Remove only symlinks created by this plugin (matching our prefix)
for link in "$RULES_DST"/{prefix}*.md; do
    [ -L "$link" ] && rm -f "$link"
done

exit 0
""",
    )
    cleanup_script.chmod(0o755)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a Claude Code plugin from an .agent.toml profile"
    )
    parser.add_argument("profile", help="Path to .agent.toml file")
    parser.add_argument(
        "--output", required=True, help="Output directory for the plugin"
    )
    parser.add_argument("--name", help="Override plugin name (default: agent name)")
    args = parser.parse_args()

    profile_path = Path(args.profile).resolve()
    output_dir = Path(args.output).resolve()

    # Validate input
    if not profile_path.exists():
        print(f"ERROR: Profile not found: {profile_path}", file=sys.stderr)
        sys.exit(1)
    if not profile_path.suffix == ".toml":
        print(
            f"ERROR: Expected .agent.toml file, got: {profile_path.name}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Check output doesn't already have a plugin
    if (output_dir / ".claude-plugin").exists():
        print(
            "ERROR: Output directory already contains .claude-plugin/. Use a fresh directory.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load profile
    print(f"Loading profile: {profile_path}")
    profile = load_profile(profile_path)

    agent_section = profile.get("agent", {})
    agent_name = agent_section.get("name", profile_path.stem.replace(".agent", ""))
    agent_path = agent_section.get("path", "")
    plugin_name = args.name or agent_name

    # Quad-match check: plugin name should match agent name for AI Maestro compatibility
    if plugin_name != agent_name:
        print(
            f"WARNING: Plugin name '{plugin_name}' differs from agent name '{agent_name}'. AI Maestro requires these to match.",
            file=sys.stderr,
        )

    # Validate plugin name is kebab-case
    if not re.match(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$", plugin_name):
        print(
            f"ERROR: Plugin name must be kebab-case: '{plugin_name}'", file=sys.stderr
        )
        sys.exit(1)

    # Load skill index for path resolution
    print("Loading skill index...")
    index = load_skill_index()

    # Collect all element names from the profile
    skills_section = profile.get("skills", {})
    all_skill_names = (
        skills_section.get("primary", [])
        + skills_section.get("secondary", [])
        + skills_section.get("specialized", [])
    )
    agent_names = profile.get("subagents", profile.get("agents", {})).get(
        "recommended", []
    )
    command_names = profile.get("commands", {}).get("recommended", [])
    rule_names = profile.get("rules", {}).get("recommended", [])
    mcp_names = profile.get("mcp", {}).get("recommended", [])
    hook_names = profile.get("hooks", {}).get("recommended", [])

    print(
        f"Profile: {len(all_skill_names)} skills, {len(agent_names)} agents, {len(command_names)} commands, {len(rule_names)} rules, {len(mcp_names)} MCPs"
    )

    # Create plugin directory structure
    print(f"Creating plugin at: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / ".claude-plugin").mkdir(exist_ok=True)

    # Track stats for README
    stats = {
        "skills": 0,
        "agents": 0,
        "commands": 0,
        "rules": 0,
        "mcp": 0,
        "output_styles": 0,
    }

    # Copy skills
    if all_skill_names:
        skills_dir = output_dir / "skills"
        skills_dir.mkdir(exist_ok=True)
        for name in all_skill_names:
            path = resolve_element_path(name, index)
            if path:
                if copy_skill(name, path, skills_dir):
                    stats["skills"] += 1
                    print(f"  ✓ skill: {name}")
            else:
                print(f"  ✗ skill: {name} — not found in index", file=sys.stderr)

    # Copy the agent definition itself
    agents_dir = output_dir / "agents"
    agents_dir.mkdir(exist_ok=True)
    if agent_path and Path(agent_path).exists():
        shutil.copy2(agent_path, agents_dir / Path(agent_path).name)
        stats["agents"] += 1
        print(f"  ✓ agent: {agent_name} (main agent definition)")

    # Copy recommended agents
    for name in agent_names:
        path = resolve_element_path(name, index)
        if path:
            if copy_agent(name, path, agents_dir):
                stats["agents"] += 1
                print(f"  ✓ agent: {name}")
        else:
            print(f"  ✗ agent: {name} — not found in index", file=sys.stderr)

    # Copy commands
    if command_names:
        commands_dir = output_dir / "commands"
        commands_dir.mkdir(exist_ok=True)
        for name in command_names:
            path = resolve_element_path(name, index)
            if path:
                if copy_command(name, path, commands_dir):
                    stats["commands"] += 1
                    print(f"  ✓ command: {name}")
            else:
                print(f"  ✗ command: {name} — not found in index", file=sys.stderr)

    # Copy rules to plugin's rules/ dir (not a standard plugin component).
    # A SessionStart hook will symlink them into the project's .claude/rules/.
    if rule_names:
        rules_dir = output_dir / "rules"
        rules_dir.mkdir(exist_ok=True)
        for name in rule_names:
            path = resolve_element_path(name, index)
            if path:
                if copy_rule(name, path, rules_dir):
                    stats["rules"] += 1
                    print(f"  ✓ rule: {name}")
            else:
                # Try direct path for rules (they may not be in the skill index)
                if copy_rule(name, "", rules_dir):
                    stats["rules"] += 1
                    print(f"  ✓ rule: {name} (from user rules)")
                else:
                    print(f"  ✗ rule: {name} — not found", file=sys.stderr)

    # Copy output styles to plugin's output-styles/ dir
    output_style_names = profile.get("output_styles", {}).get("recommended", [])
    if output_style_names:
        output_styles_dir = output_dir / "output-styles"
        output_styles_dir.mkdir(exist_ok=True)
        for name in output_style_names:
            path = resolve_element_path(name, index)
            if path and Path(path).exists():
                shutil.copy2(Path(path), output_styles_dir / Path(path).name)
                stats["output_styles"] += 1
                print(f"  ✓ output-style: {name}")
            else:
                print(f"  ✗ output-style: {name} — not found in index", file=sys.stderr)

    # Generate MCP config from index metadata
    if mcp_names:
        mcp_configs: dict[str, Any] = {}
        for name in mcp_names:
            path = resolve_element_path(name, index)
            if path and Path(path).exists():
                # Try to read actual MCP config from the source
                try:
                    with open(path, encoding="utf-8") as mf:
                        src_data = json.load(mf)
                    # Extract server config if it's an MCP descriptor
                    if "command" in src_data or "url" in src_data:
                        mcp_configs[name] = src_data
                        continue
                except (json.JSONDecodeError, OSError):
                    pass
            # Fallback: placeholder requiring manual config
            mcp_configs[name] = {
                "command": f"TODO: configure {name}",
                "args": [],
            }
        if mcp_configs:
            mcp_json = {"mcpServers": mcp_configs}
            with open(output_dir / ".mcp.json", "w") as f:
                json.dump(mcp_json, f, indent=2)
                f.write("\n")
            stats["mcp"] = len(mcp_names)
            print(
                f"  ✓ .mcp.json placeholder ({len(mcp_names)} MCP servers — configure manually)"
            )

    # Generate hooks.json — includes rules symlink hooks if rules exist
    has_rules = stats.get("rules", 0) > 0
    has_user_hooks = bool(hook_names)
    if has_rules or has_user_hooks:
        hooks_dir = output_dir / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        hooks_json: dict = {"hooks": {}}

        # Rules symlink hooks: SessionStart installs, SessionEnd cleans up
        if has_rules:
            scripts_dir = output_dir / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            generate_rules_hook_scripts(plugin_name, scripts_dir)
            hooks_json["hooks"]["SessionStart"] = [
                {
                    "matcher": "startup|resume|clear|compact",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "bash ${CLAUDE_PLUGIN_ROOT}/scripts/install-rules.sh",
                            "timeout": 5000,
                        }
                    ],
                }
            ]
            hooks_json["hooks"]["SessionEnd"] = [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "bash ${CLAUDE_PLUGIN_ROOT}/scripts/cleanup-rules.sh",
                            "timeout": 1500,
                        }
                    ],
                }
            ]
            print(
                "  ✓ scripts/install-rules.sh + cleanup-rules.sh (rule symlink hooks)"
            )

        if has_user_hooks:
            print(
                f"  ✓ hooks/hooks.json placeholder ({len(hook_names)} hooks — configure manually)"
            )

        with open(hooks_dir / "hooks.json", "w") as f:
            json.dump(hooks_json, f, indent=2)
            f.write("\n")
        print("  ✓ hooks/hooks.json")

    # Generate plugin.json
    # Use [description].text from profile if available, otherwise generate default
    desc_section = profile.get("description", {})
    description = (
        desc_section.get("text", "").strip()
        or f"Plugin for {agent_name} agent — auto-generated from .agent.toml profile"
    )
    manifest = generate_plugin_json(plugin_name, agent_name, description, profile)
    with open(output_dir / ".claude-plugin" / "plugin.json", "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print("  ✓ .claude-plugin/plugin.json")

    # Copy the .agent.toml itself for reference
    shutil.copy2(profile_path, output_dir / profile_path.name)
    print(f"  ✓ {profile_path.name} (profile reference)")

    # Generate README
    readme = generate_readme(plugin_name, agent_name, description, profile, stats)
    with open(output_dir / "README.md", "w") as f:
        f.write(readme)
    print("  ✓ README.md")

    # Summary
    total = sum(stats.values())
    print(f"\n{'=' * 50}")
    print(f"Plugin '{plugin_name}' created at: {output_dir}")
    print(
        f"  Skills: {stats['skills']}, Agents: {stats['agents']}, Commands: {stats['commands']}, Rules: {stats['rules']}, MCP: {stats['mcp']}"
    )
    print(f"  Total elements copied: {total}")
    print(f"\nInstall with: claude plugin install {output_dir}")
    print(f"Test with:    claude --plugin-dir {output_dir}")


if __name__ == "__main__":
    main()
