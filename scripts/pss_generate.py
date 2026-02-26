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
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Pre-compiled regex patterns used across extraction functions
FM_TYPE_RE = re.compile(r"^type:\s*(\S+)", re.MULTILINE | re.IGNORECASE)
TRIGGERS_RE = re.compile(
    r"^(?:triggers|keywords|activators):\s*\n((?:\s*-\s*.+\n)*)",
    re.MULTILINE | re.IGNORECASE,
)
CODE_BLOCK_RE = re.compile(r"```(?:bash|shell|sh)?\n(.*?)```", re.DOTALL)
TECH_TERM_RE = re.compile(
    r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+|[a-z]+-[a-z]+(?:-[a-z]+)*)\b"
)
HEADER_RE = re.compile(r"^#+\s+(.+)$", re.MULTILINE)
USE_WHEN_RE = re.compile(
    r"use (?:this (?:skill|element) )?when[:\s]+(.+?)(?:\.|$)", re.IGNORECASE
)
HELPS_RE = re.compile(r"helps? you (?:to )?(.+?)(?:\.|$)", re.IGNORECASE)
BULLET_VERB_RE = re.compile(r"^\s*[-*]\s*([A-Z][a-z]+(?:\s+\w+){1,5})", re.MULTILINE)


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

    # Check frontmatter type field
    fm_match = FM_TYPE_RE.search(content)
    if fm_match:
        fm_type = fm_match.group(1).strip().lower()
        if fm_type == "agent":
            return "agent"
        if fm_type == "command":
            return "command"
        if fm_type == "rule":
            return "rule"
        if fm_type == "mcp":
            return "mcp"
        if fm_type == "lsp":
            return "lsp"

    # Check path
    path_str = str(skill_path).lower()
    if "/agents/" in path_str:
        return "agent"
    if "/commands/" in path_str:
        return "command"
    if "/rules/" in path_str:
        return "rule"

    # Check content patterns
    if "task tool" in content_lower or "subagent_type" in content_lower:
        return "agent"
    if "slash command" in content_lower or "user-invocable" in content_lower:
        return "command"

    return "skill"


def extract_keywords_from_content(content: str) -> list[str]:
    """
    Extract potential keywords from element content (SKILL.md, agent, command, or rule).

    This is a heuristic-based approach. For production use,
    AI-based extraction via /pss-reindex-skills is recommended.
    """
    keywords = set()

    # Extract from frontmatter triggers/keywords
    triggers_match = TRIGGERS_RE.search(content)
    if triggers_match:
        for line in triggers_match.group(1).split("\n"):
            kw = line.strip().lstrip("-").strip().strip('"').strip("'").lower()
            if kw and len(kw) > 1:
                keywords.add(kw)

    # Extract code blocks and commands
    code_blocks = CODE_BLOCK_RE.findall(content)
    for block in code_blocks:
        # Extract command names
        commands = re.findall(r"^\s*(\w+(?:-\w+)*)\s", block, re.MULTILINE)
        for cmd in commands:
            if len(cmd) > 2 and cmd not in ("the", "and", "for", "with"):
                keywords.add(cmd.lower())

    # Extract technical terms (capitalized or hyphenated)
    tech_terms = TECH_TERM_RE.findall(content)
    for term in tech_terms:
        term_lower = term.lower()
        if len(term_lower) > 2:
            keywords.add(term_lower)

    # Extract from headers
    headers = HEADER_RE.findall(content)
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
    use_when = USE_WHEN_RE.findall(content)
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
    """Extract intent phrases from element content."""
    intents = []

    # Extract from "Use when" patterns
    use_when = USE_WHEN_RE.findall(content)
    intents.extend(use_when)

    # Extract from "This skill helps you" patterns
    helps = HELPS_RE.findall(content)
    intents.extend(helps)

    # Extract from bullet points starting with verbs
    bullets = BULLET_VERB_RE.findall(content)
    for bullet in bullets:
        # Extract first word (verb) from the bullet phrase
        first_word = bullet.split()[0].lower() if bullet.split() else ""
        if first_word in [
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
    """Calculate SHA-256 hash of element file content."""
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

    with open(skill_path, encoding="utf-8") as f:
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
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(pss_data, f, indent=2)
    print(f"Generated: {output_path}")


def generate_pss_for_mcp(
    name: str, server_config: dict[str, Any], source: str, path: str = ""
) -> dict[str, Any]:
    """Generate PSS data for an MCP server entry (flat format for merge_pass1).

    Args:
        name: Server name (e.g., "chrome-devtools")
        server_config: Raw config dict with type, command, args
        source: Source identifier (user, project, etc.)
        path: Path to the config file that defines this MCP server
    """
    # Extract keywords from server name and command
    keywords: set[str] = set()
    for part in re.split(r"[-_]", name.lower()):
        if len(part) > 2:
            keywords.add(part)
    keywords.add(name.lower())

    cmd = server_config.get("command", "")
    if cmd:
        keywords.add(cmd.lower())

    for arg in server_config.get("args", []):
        if isinstance(arg, str) and not arg.startswith("-"):
            for part in re.split(r"[@/]", arg):
                for sub in re.split(r"[-_]", part.lower()):
                    if len(sub) > 2 and sub not in ("latest", "npx", "node"):
                        keywords.add(sub)

    return {
        "name": name,
        "type": "mcp",
        "source": source,
        "path": path,
        "keywords": sorted(keywords),
        "intents": [],
        "patterns": [],
        "directories": [],
        "description": "",
        "use_cases": [],
        "category": "",
        "tier": "secondary",
        "boost": 0,
        "domain_gates": {},
        "server_type": server_config.get("type", "stdio"),
        "server_command": server_config.get("command", ""),
        "server_args": server_config.get("args", []),
    }


def generate_pss_for_lsp(name: str, marketplace: str, path: str = "") -> dict[str, Any]:  # noqa: ARG001
    """Generate PSS data for an LSP server (flat format for merge_pass1).

    Args:
        name: LSP name (e.g., "pyright-lsp")
        marketplace: Marketplace identifier (reserved for future use)
        path: Path to the config file that defines this LSP server
    """
    # Common LSP name-to-language mapping for automatic language_ids detection
    lsp_languages = {
        "pyright": ["python"],
        "typescript": ["typescript", "javascript"],
        "gopls": ["go"],
        "rust-analyzer": ["rust"],
        "jdtls": ["java"],
        "clangd": ["c", "cpp"],
        "swift": ["swift"],
        "csharp": ["csharp"],
    }
    # Try to match against the name
    lang_ids: list[str] = []
    name_lower = name.lower()
    for key, langs in lsp_languages.items():
        if key in name_lower:
            lang_ids = langs
            break

    keywords: set[str] = set()
    for part in re.split(r"[-_]", name_lower):
        if len(part) > 1 and part != "lsp":
            keywords.add(part)
    keywords.add(name_lower)
    keywords.add("lsp")
    keywords.add("language server")

    return {
        "name": name,
        "type": "lsp",
        "source": "built-in",
        "path": path,
        "keywords": sorted(keywords),
        "intents": [],
        "patterns": [],
        "directories": [],
        "description": "",
        "use_cases": [],
        "category": "code-quality",
        "tier": "secondary",
        "boost": 0,
        "domain_gates": {},
        "language_ids": lang_ids,
    }


def generate_for_directory(
    dir_path: Path,
    tier: str = "secondary",
    category: str | None = None,
    source: str | None = None,
    force: bool = False,
) -> int:
    """
    Generate .pss files for all skills in a directory.

    Output goes to the system temp pss-queue dir to prevent .pss accumulation in skill dirs.
    Returns count of generated files.
    """
    # Write .pss to queue dir, not skill dirs, to prevent orphaned file buildup
    queue_dir = Path(tempfile.gettempdir()) / "pss-queue"
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

    # Check for agent/command/rule .md files in known subdirectories (one level deep)
    for subdir_name in ("agents", "commands", "rules"):
        subdir = dir_path / subdir_name
        if not subdir.is_dir():
            # Also check if dir_path itself IS an agents/commands/rules dir
            if dir_path.name == subdir_name:
                subdir = dir_path
            else:
                continue

        for md_file in sorted(subdir.iterdir()):
            if not md_file.is_file() or not md_file.name.endswith(".md"):
                continue
            if md_file.name.lower() in ("skill.md", "readme.md"):
                continue

            pss_path = queue_dir / f"{md_file.stem}.pss"
            if pss_path.exists() and not force:
                print(f"Skipping (exists): {pss_path}")
                continue

            try:
                pss_data = generate_pss(md_file, tier, category, source, force)
                save_pss(pss_data, pss_path)
                count += 1
            except Exception as e:
                print(f"Error processing {md_file}: {e}", file=sys.stderr)

    return count


def import_from_index(index_path: Path, output_dir: Path, force: bool = False) -> int:
    """
    Import skills from an existing skill-index.json file.

    Creates .pss files for each skill in the index.
    """
    with open(index_path, encoding="utf-8") as f:
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
        scoring_dict: dict[str, Any] = {"tier": skill_data.get("tier", "secondary")}

        pss: dict[str, Any] = {
            "version": "1.0",
            "skill": skill_dict,
            "matchers": matchers_dict,
            "scoring": scoring_dict,
            "metadata": {
                "generated_by": "manual",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "generator_version": "import_from_index/1.0",
            },
        }

        # Add optional matcher fields
        if skill_data.get("intents"):
            matchers_dict["intents"] = skill_data["intents"]
        if skill_data.get("patterns"):
            matchers_dict["patterns"] = skill_data["patterns"]
        if skill_data.get("directories"):
            matchers_dict["directories"] = skill_data["directories"]

        # Multi-type fields (MCP/LSP)
        if skill_data.get("server_type"):
            skill_dict["server_type"] = skill_data["server_type"]
        if skill_data.get("server_command"):
            skill_dict["server_command"] = skill_data["server_command"]
        if skill_data.get("server_args"):
            skill_dict["server_args"] = skill_data["server_args"]
        if skill_data.get("language_ids"):
            skill_dict["language_ids"] = skill_data["language_ids"]

        # Scoring fields
        if skill_data.get("category"):
            scoring_dict["category"] = skill_data["category"]
        if skill_data.get("boost"):
            scoring_dict["boost"] = skill_data["boost"]

        # Domain gates and path patterns
        if skill_data.get("domain_gates"):
            matchers_dict["domain_gates"] = skill_data["domain_gates"]
        if skill_data.get("path_patterns"):
            matchers_dict["path_patterns"] = skill_data["path_patterns"]

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
        choices=["primary", "secondary", "specialized"],
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

            # Determine output path — default to system temp pss-queue to avoid
            # polluting skill directories with .pss files
            if args.output:
                output_path = Path(args.output)
            else:
                queue_dir = Path(tempfile.gettempdir()) / "pss-queue"
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
