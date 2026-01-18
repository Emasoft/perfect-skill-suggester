#!/usr/bin/env python3
"""
Perfect Skill Suggester - Skill Discovery Script.

Find ALL skill files available to Claude Code.
This script ONLY discovers skill locations. It does NOT analyze or extract keywords.
Keyword/phrase extraction is done by the agent reading each skill.

Usage:
    python3 pss_discover_skills.py [--json] [--project-only] [--user-only]
    python3 pss_discover_skills.py --checklist [--batch-size 10] [--output FILE]

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


def get_home_dir() -> Path:
    """Get user home directory."""
    return Path.home()


def get_cwd() -> Path:
    """Get current working directory."""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        return Path(project_dir)
    return Path.cwd()


def get_all_skill_locations() -> list[tuple[str, Path]]:
    """Get all locations where skills can be found.

    Scans:
    1. User-level skills: ~/.claude/skills/
    2. Project-level skills: .claude/skills/
    3. Plugin cache skills: ~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/skills/
    4. Local plugins: ~/.claude/plugins/<plugin>/skills/
    5. Project plugins: .claude/plugins/*/skills/
    """
    locations = []
    home = get_home_dir()
    cwd = get_cwd()

    # 1. User-level skills: ~/.claude/skills/
    user_skills = home / ".claude" / "skills"
    if user_skills.exists():
        locations.append(("user", user_skills))

    # 2. Project-level skills: .claude/skills/
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

    # 5. Project plugins: .claude/plugins/*/skills/
    project_plugins = cwd / ".claude" / "plugins"
    if project_plugins.exists():
        for plugin_dir in project_plugins.iterdir():
            if plugin_dir.is_dir():
                plugin_skills = plugin_dir / "skills"
                if plugin_skills.exists():
                    locations.append((f"plugin:{plugin_dir.name}", plugin_skills))

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


def discover_skills(
    locations: list[tuple[str, Path]], specific_skill: str | None = None
) -> list[dict[str, Any]]:
    """Discover all skills in all provided locations.

    Returns basic metadata only - NO keyword extraction.
    """
    skills = []
    seen_names: set[str] = set()

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

                skills.append(
                    {
                        "name": frontmatter.get("name", skill_path.name),
                        "path": str(skill_md),
                        "source": source,
                        "description": frontmatter.get("description", "")[:200],
                        "preview": body,  # First 500 chars for agent to analyze
                    }
                )
                seen_names.add(skill_path.name)

            except Exception as e:
                print(f"Error reading {skill_md}: {e}", file=sys.stderr)

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
        "Each batch can be assigned to a separate haiku subagent for parallel analysis.",
        "The orchestrator should:",
        "",
        "1. Spawn N subagents (one per batch)",
        "2. Assign each subagent its batch range (e.g., Agent A → Batch 1, Agent B → Batch 2)",
        "3. Each subagent reads the SKILL.md at the given path",
        "4. Each subagent generates patterns: keywords, phrases, intents, errors, triggers",
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
        lines.append(
            f"## Batch {batch_num + 1} ({start_idx + 1}-{end_idx}) - Agent {agent_letter}"
        )
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
            "After all batches are complete, the orchestrator should compile results here:",
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
        "--project-only", action="store_true", help="Only scan project skills"
    )
    parser.add_argument(
        "--user-only", action="store_true", help="Only scan user-level skills"
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
        help="Output file path for checklist (default: stdout or ~/.claude/cache/skill-checklist.md)",
    )

    args = parser.parse_args()

    all_locations = get_all_skill_locations()

    if args.project_only:
        all_locations = [(s, p) for s, p in all_locations if s == "project"]
    elif args.user_only:
        all_locations = [(s, p) for s, p in all_locations if s == "user"]

    skills = discover_skills(all_locations, args.skill)

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
        print(
            f"  {len(skills)} skills in {math.ceil(len(skills) / args.batch_size)} batches"
        )
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
