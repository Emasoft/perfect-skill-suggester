#!/usr/bin/env python3
"""
Perfect Skill Suggester - Skill Discovery Script.

Find ALL skill files available to Claude Code across ALL projects.
This script discovers skill locations from:
- User-level skills (~/.claude/skills/)
- All projects registered in ~/.claude.json
- Plugin caches and local plugins

This script ONLY discovers skill locations. It does NOT analyze or extract keywords.
Keyword/phrase extraction is done by the agent reading each skill.

Usage:
    python3 pss_discover_skills.py [--json] [--project-only] [--user-only]
    python3 pss_discover_skills.py --checklist [--batch-size 10] [--output FILE]
    python3 pss_discover_skills.py --all-projects
    # --all-projects scans ALL projects from ~/.claude.json

Output Modes:
    Default: List of skill paths with metadata (name, path, source)
    --json: JSON format for programmatic use
    --checklist: Markdown checklist with batches for parallel agent processing

Checklist Format:
    The checklist divides skills into batches (default 10 per batch) for parallel
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

# PSS file schema version
PSS_SCHEMA_VERSION = "1.0.0"


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
                    file=sys.stderr
                )
                continue

            if not project_path.is_dir():
                print(
                    f"Warning: Project path is not a directory: {project_path}",
                    file=sys.stderr
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


def get_all_skill_locations(scan_all_projects: bool = False) -> list[tuple[str, Path]]:
    """Get all locations where skills can be found.

    Scans:
    1. User-level skills: ~/.claude/skills/
    2. Current project skills: .claude/skills/
    3. Plugin cache skills:
       ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/skills/
    4. Local plugins: ~/.claude/plugins/<plugin>/skills/
    5. Current project plugins: .claude/plugins/*/skills/
    6. (if scan_all_projects=True) ALL projects from ~/.claude.json:
       - <project>/.claude/skills/
       - <project>/.claude/plugins/*/skills/

    Args:
        scan_all_projects: If True, scan all projects registered in ~/.claude.json
    """
    locations = []
    home = get_home_dir()
    cwd = get_cwd()

    # 1. User-level skills: ~/.claude/skills/
    user_skills = home / ".claude" / "skills"
    if user_skills.exists():
        locations.append(("user", user_skills))

    # 2. Current project-level skills: .claude/skills/
    project_skills = cwd / ".claude" / "skills"
    if project_skills.exists():
        locations.append(("project", project_skills))

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
                    skills_dir = version / "skills"
                    if skills_dir.exists():
                        locations.append(
                            (f"plugin:{marketplace.name}/{plugin.name}", skills_dir)
                        )
                    if (version / "SKILL.md").exists():
                        locations.append(
                            (f"plugin:{marketplace.name}/{plugin.name}", version.parent)
                        )

    # 4. Local plugins: ~/.claude/plugins/<plugin>/skills/
    user_plugins = home / ".claude" / "plugins"
    if user_plugins.exists():
        for plugin_dir in user_plugins.iterdir():
            if not plugin_dir.is_dir():
                continue
            if plugin_dir.name in ("cache", "_disabled", "repos", "marketplaces"):
                continue
            plugin_skills = plugin_dir / "skills"
            if plugin_skills.exists():
                locations.append((f"plugin:{plugin_dir.name}", plugin_skills))

    # 5. Current project plugins: .claude/plugins/*/skills/
    project_plugins = cwd / ".claude" / "plugins"
    if project_plugins.exists():
        for plugin_dir in project_plugins.iterdir():
            if plugin_dir.is_dir():
                plugin_skills = plugin_dir / "skills"
                if plugin_skills.exists():
                    locations.append((f"plugin:{plugin_dir.name}", plugin_skills))

    # 6. All projects from ~/.claude.json (comprehensive indexing)
    if scan_all_projects:
        seen_project_paths: set[Path] = {cwd}  # Skip current project (already scanned)

        all_projects = get_all_projects_from_claude_config()
        for project_name, project_path in all_projects:
            # Skip if already scanned (current project)
            if project_path in seen_project_paths:
                continue
            seen_project_paths.add(project_path)

            # 6a. Project-level skills: <project>/.claude/skills/
            proj_skills = project_path / ".claude" / "skills"
            if proj_skills.exists():
                locations.append((f"project:{project_name}", proj_skills))

            # 6b. Project plugins: <project>/.claude/plugins/*/skills/
            proj_plugins = project_path / ".claude" / "plugins"
            if proj_plugins.exists():
                for plugin_dir in proj_plugins.iterdir():
                    if plugin_dir.is_dir():
                        plugin_skills = plugin_dir / "skills"
                        if plugin_skills.exists():
                            source = f"project:{project_name}/plugin:{plugin_dir.name}"
                            locations.append((source, plugin_skills))

    return locations


def parse_frontmatter(content: str) -> dict[str, Any]:
    """Parse YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}

    end_idx = content.find("---", 3)
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


def generate_pss_file(skill_data: dict[str, Any], skill_dir: Path) -> Path | None:
    """Generate a .pss metadata file for a discovered skill.

    The .pss file is a JSON file containing:
    - Basic skill metadata (name, description, source)
    - Path to the SKILL.md file
    - Discovery timestamp
    - Schema version

    This file is saved in the same directory as the SKILL.md file and is used
    by the index generator to quickly identify which skills need re-indexing.

    Args:
        skill_data: Dictionary with skill metadata from discover_skills()
        skill_dir: Path to the skill directory (parent of SKILL.md)

    Returns:
        Path to the generated .pss file, or None if generation failed
    """
    pss_file = skill_dir / f"{skill_data['name']}.pss"

    pss_content = {
        "schema_version": PSS_SCHEMA_VERSION,
        "name": skill_data["name"],
        "description": skill_data.get("description", ""),
        "source": skill_data["source"],
        "skill_md_path": skill_data["path"],
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "needs_indexing": True,  # Flag for index generator to process
    }

    try:
        pss_file.write_text(
            json.dumps(pss_content, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        return pss_file
    except PermissionError:
        print(
            f"Warning: Cannot write .pss file (permission denied): {pss_file}",
            file=sys.stderr
        )
        return None
    except Exception as e:
        print(f"Warning: Failed to write .pss file: {pss_file}: {e}", file=sys.stderr)
        return None


def discover_skills(
    locations: list[tuple[str, Path]],
    specific_skill: str | None = None,
    generate_pss_files: bool = False,
) -> list[dict[str, Any]]:
    """Discover all skills in all provided locations.

    Returns basic metadata only - NO keyword extraction.

    Args:
        locations: List of (source, path) tuples to scan for skills
        specific_skill: If provided, only discover this specific skill
        generate_pss_files: If True, generate .pss metadata files for each skill

    Returns:
        List of skill metadata dictionaries
    """
    skills = []
    seen_names: set[str] = set()
    pss_files_generated = 0
    pss_files_failed = 0

    for source, skills_dir in locations:
        if not skills_dir.exists():
            continue

        for skill_path in sorted(skills_dir.iterdir()):
            if not skill_path.is_dir():
                continue

            if specific_skill and skill_path.name != specific_skill:
                continue

            skill_md = skill_path / "SKILL.md"
            if not skill_md.exists():
                continue

            if skill_path.name in seen_names:
                continue

            try:
                content = skill_md.read_text(encoding="utf-8")
                frontmatter = parse_frontmatter(content)

                # Extract description (first 500 chars after frontmatter)
                body_start = content.find("---", 3)
                if body_start != -1:
                    body = content[body_start + 3 :].strip()[:500]
                else:
                    body = content[:500]

                skill_data = {
                    "name": frontmatter.get("name", skill_path.name),
                    "path": str(skill_md),
                    "source": source,
                    "description": frontmatter.get("description", "")[:200],
                    "preview": body,  # First 500 chars for agent to analyze
                }
                skills.append(skill_data)
                seen_names.add(skill_path.name)

                # Generate .pss file if requested
                if generate_pss_files:
                    pss_result = generate_pss_file(skill_data, skill_path)
                    if pss_result:
                        pss_files_generated += 1
                    else:
                        pss_files_failed += 1

            except Exception as e:
                print(f"Error reading {skill_md}: {e}", file=sys.stderr)

    # Report .pss file generation results
    if generate_pss_files:
        print(
            f"Generated {pss_files_generated} .pss files "
            f"({pss_files_failed} failed)",
            file=sys.stderr
        )

    return skills


def generate_checklist(skills: list[dict[str, Any]], batch_size: int = 10) -> str:
    """Generate a markdown checklist with batches for parallel agent processing.

    Args:
        skills: List of discovered skills with name, path, source
        batch_size: Number of skills per batch (for dividing among agents)

    Returns:
        Markdown formatted checklist string
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total_skills = len(skills)
    num_batches = math.ceil(total_skills / batch_size)

    lines = [
        "# PSS Skill Index Checklist",
        "",
        f"**Generated:** {now}",
        f"**Total Skills:** {total_skills}",
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
        "3. Each subagent reads the SKILL.md at the given path",
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
        end_idx = min(start_idx + batch_size, total_skills)
        batch_skills = skills[start_idx:end_idx]

        # Batch header with agent assignment suggestion
        agent_letter = chr(ord("A") + (batch_num % 26))  # A-Z, then wraps
        batch_range = f"{start_idx + 1}-{end_idx}"
        lines.append(f"## Batch {batch_num + 1} ({batch_range}) - Agent {agent_letter}")
        lines.append("")
        lines.append(f"**Skills in this batch:** {len(batch_skills)}")
        lines.append("")

        # Add each skill as a checkbox item
        for i, skill in enumerate(batch_skills, start=start_idx + 1):
            skill_name = skill["name"]
            skill_path = skill["path"]
            skill_source = skill["source"]
            lines.append(f"- [ ] **{i}.** `{skill_name}` [{skill_source}]")
            lines.append(f"  - Path: `{skill_path}`")
            if skill.get("description"):
                desc = skill["description"][:100]
                lines.append(f"  - Description: {desc}...")
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
            "| Batch | Agent | Skills Processed | Status |",
            "|-------|-------|------------------|--------|",
        ]
    )

    for batch_num in range(num_batches):
        agent_letter = chr(ord("A") + (batch_num % 26))
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, total_skills)
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
        description="PSS - Discover ALL skill files available to Claude Code"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--skill", type=str, help="Only discover specific skill")
    parser.add_argument(
        "--project-only", action="store_true", help="Only scan current project skills"
    )
    parser.add_argument(
        "--user-only", action="store_true", help="Only scan user-level skills"
    )
    # All projects scanning
    parser.add_argument(
        "--all-projects",
        action="store_true",
        help="Scan ALL projects registered in ~/.claude.json (comprehensive indexing)",
    )
    # PSS file generation
    parser.add_argument(
        "--generate-pss",
        action="store_true",
        help="Generate .pss metadata files for each discovered skill",
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
        help="Number of skills per batch for checklist (default: 10)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path for checklist "
        "(default: stdout or ~/.claude/cache/skill-checklist.md)",
    )

    args = parser.parse_args()

    # Determine if we should scan all projects (comprehensive indexing)
    # Skip if --project-only or --user-only is specified
    scan_all_projects = args.all_projects and not (args.project_only or args.user_only)

    all_locations = get_all_skill_locations(scan_all_projects=scan_all_projects)

    if args.project_only:
        # Filter to current project only (not other projects)
        all_locations = [(s, p) for s, p in all_locations if s == "project"]
    elif args.user_only:
        all_locations = [(s, p) for s, p in all_locations if s == "user"]

    skills = discover_skills(
        all_locations,
        args.skill,
        generate_pss_files=args.generate_pss,
    )

    # Checklist mode: generate markdown checklist with batches
    if args.checklist:
        checklist_content = generate_checklist(skills, args.batch_size)

        if args.output:
            output_path = Path(args.output)
        else:
            # Default output path
            cache_dir = Path.home() / ".claude" / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            output_path = cache_dir / "skill-checklist.md"

        output_path.write_text(checklist_content, encoding="utf-8")
        print(f"Checklist written to: {output_path}")
        num_batches = math.ceil(len(skills) / args.batch_size)
        print(f"  {len(skills)} skills in {num_batches} batches")
        return 0

    # JSON mode
    if args.json:
        print(json.dumps({"skills": skills, "count": len(skills)}, indent=2))
    else:
        # Default text mode
        print(f"Discovered {len(skills)} skills:\n")
        for skill in skills:
            print(f"  {skill['name']} [{skill['source']}]")
            print(f"    Path: {skill['path']}")
            if skill["description"]:
                print(f"    Desc: {skill['description'][:80]}...")
            print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
