#!/usr/bin/env python3
"""
PSS File Generator

Generates .pss (Perfect Skill Suggester) matcher files for skills.
Can generate from:
1. Manual specification
2. SKILL.md content analysis
3. Existing index data

Usage:
    # Generate .pss from SKILL.md analysis (basic)
    python pss_generate.py /path/to/skill/SKILL.md

    # Generate for all skills in a directory
    python pss_generate.py --dir /path/to/skills/

    # Generate with tier and category hints
    python pss_generate.py /path/to/skill/SKILL.md --tier primary --category devops

    # Import from existing index
    python pss_generate.py --from-index /path/to/skill-index.json
"""

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class SkillInfo:
    """Extracted skill information."""

    name: str
    skill_type: str = "skill"
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)
    directories: list[str] = field(default_factory=list)


def extract_skill_name(skill_path: Path) -> str:
    """
    Extract skill name from path.

    Handles:
    - /path/to/skill-name/SKILL.md -> skill-name
    - /path/to/skill-name/skill.md -> skill-name
    - /path/to/skill-name.md -> skill-name
    """
    if skill_path.name.lower() in ("skill.md", "agent.md"):
        return skill_path.parent.name
    return skill_path.stem.lower()


def extract_skill_type(content: str, skill_path: Path) -> str:
    """Determine skill type from content or path."""
    content_lower = content.lower()

    # Check frontmatter
    if re.search(r"^type:\s*agent", content, re.MULTILINE | re.IGNORECASE):
        return "agent"
    if re.search(r"^type:\s*command", content, re.MULTILINE | re.IGNORECASE):
        return "command"

    # Check path
    path_str = str(skill_path).lower()
    if "/agents/" in path_str:
        return "agent"
    if "/commands/" in path_str:
        return "command"

    # Check content patterns
    if "task tool" in content_lower or "subagent_type" in content_lower:
        return "agent"
    if "slash command" in content_lower or "user-invocable" in content_lower:
        return "command"

    return "skill"


def extract_keywords_from_content(content: str) -> list[str]:
    """
    Extract potential keywords from SKILL.md content.

    This is a heuristic-based approach. For production use,
    AI-based extraction via /pss-reindex-skills is recommended.
    """
    keywords = set()

    # Extract from frontmatter triggers/keywords
    triggers_match = re.search(
        r"^(?:triggers|keywords|activators):\s*\n((?:\s*-\s*.+\n)*)",
        content,
        re.MULTILINE | re.IGNORECASE,
    )
    if triggers_match:
        for line in triggers_match.group(1).split("\n"):
            kw = line.strip().lstrip("-").strip().strip('"').strip("'").lower()
            if kw and len(kw) > 1:
                keywords.add(kw)

    # Extract code blocks and commands
    code_blocks = re.findall(r"```(?:bash|shell|sh)?\n(.*?)```", content, re.DOTALL)
    for block in code_blocks:
        # Extract command names
        commands = re.findall(r"^\s*(\w+(?:-\w+)*)\s", block, re.MULTILINE)
        for cmd in commands:
            if len(cmd) > 2 and cmd not in ("the", "and", "for", "with"):
                keywords.add(cmd.lower())

    # Extract technical terms (capitalized or hyphenated)
    tech_terms = re.findall(
        r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+|[a-z]+-[a-z]+(?:-[a-z]+)*)\b", content
    )
    for term in tech_terms:
        term_lower = term.lower()
        if len(term_lower) > 2:
            keywords.add(term_lower)

    # Extract from headers
    headers = re.findall(r"^#+\s+(.+)$", content, re.MULTILINE)
    for header in headers:
        words = header.lower().split()
        for word in words:
            word = re.sub(r"[^a-z0-9-]", "", word)
            if len(word) > 3 and word not in (
                "when",
                "what",
                "how",
                "the",
                "and",
                "for",
                "with",
                "this",
                "that",
            ):
                keywords.add(word)

    # Extract from "Use when" patterns
    use_when = re.findall(
        r"use (?:this skill )?when[:\s]+(.+?)(?:\.|$)", content, re.IGNORECASE
    )
    for phrase in use_when:
        words = phrase.lower().split()
        for word in words:
            word = re.sub(r"[^a-z0-9-]", "", word)
            if len(word) > 3:
                keywords.add(word)

    # Filter and deduplicate
    filtered = []
    stopwords = {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "when",
        "what",
        "how",
        "you",
        "your",
        "use",
        "using",
    }
    for kw in keywords:
        if kw not in stopwords and len(kw) > 1:
            filtered.append(kw)

    return sorted(filtered)[:20]  # Cap at 20 keywords


def extract_intents_from_content(content: str) -> list[str]:
    """Extract intent phrases from SKILL.md content."""
    intents = []

    # Extract from "Use when" patterns
    use_when = re.findall(
        r"use (?:this skill )?when[:\s]+(.+?)(?:\.|$)", content, re.IGNORECASE
    )
    intents.extend(use_when)

    # Extract from "This skill helps you" patterns
    helps = re.findall(r"helps? you (?:to )?(.+?)(?:\.|$)", content, re.IGNORECASE)
    intents.extend(helps)

    # Extract from bullet points starting with verbs
    bullets = re.findall(
        r"^\s*[-*]\s*([A-Z][a-z]+(?:\s+\w+){1,5})", content, re.MULTILINE
    )
    for bullet in bullets:
        if bullet[0].lower() in [
            "create",
            "build",
            "write",
            "generate",
            "configure",
            "set",
            "add",
            "implement",
            "debug",
            "test",
            "deploy",
            "run",
            "fix",
        ]:
            intents.append(bullet.lower())

    # Clean and deduplicate
    cleaned = []
    seen = set()
    for intent in intents:
        intent = intent.strip().lower()
        intent = re.sub(r"\s+", " ", intent)  # Normalize whitespace
        if intent not in seen and len(intent) > 5 and len(intent) < 100:
            cleaned.append(intent)
            seen.add(intent)

    return cleaned[:10]  # Cap at 10 intents


def calculate_skill_hash(skill_path: Path) -> str:
    """Calculate SHA-256 hash of SKILL.md content."""
    with open(skill_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def generate_pss(
    skill_path: Path,
    tier: str = "secondary",
    category: str | None = None,
    source: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """
    Generate a .pss file for a skill.

    Args:
        skill_path: Path to SKILL.md file
        tier: Skill tier (primary, secondary, utility)
        category: Optional category
        source: Optional source (user, project, plugin)
        force: Overwrite existing .pss file

    Returns:
        Generated PSS data as dictionary
    """
    _ = force  # Unused but kept for API compatibility
    if not skill_path.exists():
        raise FileNotFoundError(f"Skill file not found: {skill_path}")

    with open(skill_path) as f:
        content = f.read()

    # Extract info
    skill_name = extract_skill_name(skill_path)
    skill_type = extract_skill_type(content, skill_path)
    keywords = extract_keywords_from_content(content)
    intents = extract_intents_from_content(content)

    # Build PSS structure with explicit typing for nested dicts
    skill_dict: dict[str, Any] = {"name": skill_name, "type": skill_type}
    matchers_dict: dict[str, Any] = {"keywords": keywords}
    scoring_dict: dict[str, Any] = {"tier": tier}

    pss: dict[str, Any] = {
        "version": "1.0",
        "skill": skill_dict,
        "matchers": matchers_dict,
        "scoring": scoring_dict,
        "metadata": {
            "generated_by": "manual",  # Will be "ai" when using /pss-reindex-skills
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generator_version": "generate_pss/1.0",
            "skill_hash": calculate_skill_hash(skill_path),
        },
    }

    # Add optional fields
    if intents:
        matchers_dict["intents"] = intents
    if source:
        skill_dict["source"] = source
    if category:
        scoring_dict["category"] = category

    return pss


def save_pss(pss_data: dict[str, Any], output_path: Path) -> None:
    """Save PSS data to file."""
    with open(output_path, "w") as f:
        json.dump(pss_data, f, indent=2)
    print(f"Generated: {output_path}")


def generate_for_directory(
    dir_path: Path,
    tier: str = "secondary",
    category: str | None = None,
    source: str | None = None,
    force: bool = False,
) -> int:
    """
    Generate .pss files for all skills in a directory.

    Output goes to /tmp/pss-queue/ to prevent .pss accumulation in skill dirs.
    Returns count of generated files.
    """
    # Write .pss to queue dir, not skill dirs, to prevent orphaned file buildup
    queue_dir = Path("/tmp/pss-queue")
    queue_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    # Find SKILL.md files
    for skill_md in dir_path.rglob("SKILL.md"):
        pss_path = queue_dir / f"{extract_skill_name(skill_md)}.pss"

        if pss_path.exists() and not force:
            print(f"Skipping (exists): {pss_path}")
            continue

        try:
            pss_data = generate_pss(skill_md, tier, category, source, force)
            save_pss(pss_data, pss_path)
            count += 1
        except Exception as e:
            print(f"Error processing {skill_md}: {e}", file=sys.stderr)

    # Also check for agent.md files
    for agent_md in dir_path.rglob("*.md"):
        if agent_md.name.lower() in ("skill.md", "readme.md"):
            continue

        parent_name = agent_md.parent.name
        if parent_name in ("agents", "commands"):
            pss_path = queue_dir / f"{agent_md.stem}.pss"

            if pss_path.exists() and not force:
                print(f"Skipping (exists): {pss_path}")
                continue

            try:
                pss_data = generate_pss(agent_md, tier, category, source, force)
                save_pss(pss_data, pss_path)
                count += 1
            except Exception as e:
                print(f"Error processing {agent_md}: {e}", file=sys.stderr)

    return count


def import_from_index(index_path: Path, output_dir: Path, force: bool = False) -> int:
    """
    Import skills from an existing skill-index.json file.

    Creates .pss files for each skill in the index.
    """
    with open(index_path) as f:
        index = json.load(f)

    skills = index.get("skills", {})
    count = 0

    for skill_name, skill_data in skills.items():
        pss_path = output_dir / f"{skill_name}.pss"

        if pss_path.exists() and not force:
            print(f"Skipping (exists): {pss_path}")
            continue

        # Convert index format to PSS format with explicit typing
        skill_dict: dict[str, Any] = {
            "name": skill_name,
            "type": skill_data.get("type", "skill"),
            "source": skill_data.get("source", "user"),
        }
        matchers_dict: dict[str, Any] = {"keywords": skill_data.get("keywords", [])}

        pss: dict[str, Any] = {
            "version": "1.0",
            "skill": skill_dict,
            "matchers": matchers_dict,
            "metadata": {
                "generated_by": "manual",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generator_version": "import_from_index/1.0",
            },
        }

        # Add optional fields
        if skill_data.get("intents"):
            matchers_dict["intents"] = skill_data["intents"]
        if skill_data.get("patterns"):
            matchers_dict["patterns"] = skill_data["patterns"]
        if skill_data.get("directories"):
            matchers_dict["directories"] = skill_data["directories"]

        save_pss(pss, pss_path)
        count += 1

    return count


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate PSS (Perfect Skill Suggester) matcher files"
    )
    parser.add_argument("path", nargs="?", help="Path to SKILL.md file")
    parser.add_argument("--dir", help="Generate for all skills in directory")
    parser.add_argument("--from-index", help="Import from existing skill-index.json")
    parser.add_argument("--output", "-o", help="Output path for .pss file or directory")
    parser.add_argument(
        "--tier",
        choices=["primary", "secondary", "utility"],
        default="secondary",
        help="Skill tier (default: secondary)",
    )
    parser.add_argument("--category", help="Skill category (e.g., devops, testing)")
    parser.add_argument(
        "--source", choices=["user", "project", "plugin"], help="Skill source"
    )
    parser.add_argument(
        "--force", "-f", action="store_true", help="Overwrite existing .pss files"
    )

    args = parser.parse_args()

    # Handle import from index
    if args.from_index:
        index_path = Path(args.from_index)
        output_dir = Path(args.output) if args.output else Path(".")
        output_dir.mkdir(parents=True, exist_ok=True)
        count = import_from_index(index_path, output_dir, args.force)
        print(f"\nImported {count} skill(s) from index")
        return 0

    # Handle directory generation
    if args.dir:
        dir_path = Path(args.dir)
        if not dir_path.is_dir():
            print(f"Error: {dir_path} is not a directory", file=sys.stderr)
            return 1
        count = generate_for_directory(
            dir_path, args.tier, args.category, args.source, args.force
        )
        print(f"\nGenerated {count} .pss file(s)")
        return 0

    # Handle single file
    if args.path:
        skill_path = Path(args.path)
        if not skill_path.exists():
            print(f"Error: {skill_path} not found", file=sys.stderr)
            return 1

        try:
            pss_data = generate_pss(
                skill_path, args.tier, args.category, args.source, args.force
            )

            # Determine output path — default to /tmp/pss-queue/ to avoid
            # polluting skill directories with .pss files
            if args.output:
                output_path = Path(args.output)
            else:
                queue_dir = Path("/tmp/pss-queue")
                queue_dir.mkdir(parents=True, exist_ok=True)
                skill_name = extract_skill_name(skill_path)
                output_path = queue_dir / f"{skill_name}.pss"

            save_pss(pss_data, output_path)
            return 0

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    # No input provided
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
