#!/usr/bin/env python3
"""
PSS Agent TOML Validator

Validates .agent.toml files against the PSS agent TOML schema.
Checks structural correctness, field types, value constraints, and
optionally verifies that referenced skills exist in the skill index.

Usage:
    python3 pss_validate_agent_toml.py /path/to/agent.toml
    python3 pss_validate_agent_toml.py /path/to/agent.toml --check-index
    python3 pss_validate_agent_toml.py /path/to/agent.toml --verbose

Exit codes:
    0 = valid
    1 = invalid (errors found)
    2 = file not found or parse error
"""

import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any


# Schema constraints matching schemas/pss-agent-toml-schema.json
REQUIRED_SECTIONS = ["agent", "skills"]
OPTIONAL_SECTIONS = ["requirements", "agents", "commands", "rules", "mcp", "hooks", "lsp"]
ALL_KNOWN_SECTIONS = REQUIRED_SECTIONS + OPTIONAL_SECTIONS

AGENT_REQUIRED_FIELDS = ["name", "path"]
AGENT_OPTIONAL_FIELDS = ["source"]
AGENT_ALL_FIELDS = AGENT_REQUIRED_FIELDS + AGENT_OPTIONAL_FIELDS

REQUIREMENTS_FIELDS = ["files", "project_type", "tech_stack"]

SKILLS_REQUIRED_FIELDS = ["primary", "secondary", "specialized"]
SKILLS_OPTIONAL_FIELDS = ["excluded"]
SKILLS_ALL_FIELDS = SKILLS_REQUIRED_FIELDS + SKILLS_OPTIONAL_FIELDS

# Tier caps from schema
TIER_MAX_ITEMS = {
    "primary": 7,
    "secondary": 12,
    "specialized": 8,
}

# Agent name pattern from schema
AGENT_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class ValidationResult:
    """Collects errors and warnings during validation."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def report(self, verbose: bool = False) -> str:
        lines: list[str] = []
        for e in self.errors:
            lines.append(f"  ERROR: {e}")
        if verbose:
            for w in self.warnings:
                lines.append(f"  WARN:  {w}")
        return "\n".join(lines)


def validate_agent_section(data: dict[str, Any], result: ValidationResult) -> None:
    """Validate the [agent] section."""
    agent = data.get("agent")
    if agent is None:
        result.error("[agent] section is missing (required)")
        return

    if not isinstance(agent, dict):
        result.error("[agent] must be a table/dict, got: " + type(agent).__name__)
        return

    # Required fields
    for field in AGENT_REQUIRED_FIELDS:
        if field not in agent:
            result.error(f"[agent].{field} is missing (required)")

    # Unknown fields
    for field in agent:
        if field not in AGENT_ALL_FIELDS:
            result.warn(f"[agent] has unknown field: '{field}'")

    # Type checks
    name = agent.get("name")
    if name is not None:
        if not isinstance(name, str):
            result.error(f"[agent].name must be a string, got: {type(name).__name__}")
        elif not AGENT_NAME_PATTERN.match(name):
            result.error(
                f"[agent].name must be kebab-case (a-z, 0-9, hyphens, underscores), "
                f"got: '{name}'"
            )

    path = agent.get("path")
    if path is not None:
        if not isinstance(path, str):
            result.error(f"[agent].path must be a string, got: {type(path).__name__}")
        elif not path.startswith("/"):
            result.warn(f"[agent].path should be an absolute path, got: '{path}'")

    source = agent.get("source")
    if source is not None and not isinstance(source, str):
        result.error(f"[agent].source must be a string, got: {type(source).__name__}")


def validate_requirements_section(
    data: dict[str, Any], result: ValidationResult
) -> None:
    """Validate the [requirements] section (optional)."""
    reqs = data.get("requirements")
    if reqs is None:
        return  # Optional section

    if not isinstance(reqs, dict):
        result.error(
            "[requirements] must be a table/dict, got: " + type(reqs).__name__
        )
        return

    # Unknown fields
    for field in reqs:
        if field not in REQUIREMENTS_FIELDS:
            result.warn(f"[requirements] has unknown field: '{field}'")

    # Type checks
    files = reqs.get("files")
    if files is not None:
        if not isinstance(files, list):
            result.error(
                f"[requirements].files must be an array, got: {type(files).__name__}"
            )
        elif not all(isinstance(f, str) for f in files):
            result.error("[requirements].files must contain only strings")

    proj_type = reqs.get("project_type")
    if proj_type is not None and not isinstance(proj_type, str):
        result.error(
            f"[requirements].project_type must be a string, "
            f"got: {type(proj_type).__name__}"
        )

    tech = reqs.get("tech_stack")
    if tech is not None:
        if not isinstance(tech, list):
            result.error(
                f"[requirements].tech_stack must be an array, "
                f"got: {type(tech).__name__}"
            )
        elif not all(isinstance(t, str) for t in tech):
            result.error("[requirements].tech_stack must contain only strings")


def validate_skills_section(
    data: dict[str, Any],
    result: ValidationResult,
    index_skills: set[str] | None = None,
) -> None:
    """Validate the [skills] section."""
    skills = data.get("skills")
    if skills is None:
        result.error("[skills] section is missing (required)")
        return

    if not isinstance(skills, dict):
        result.error("[skills] must be a table/dict, got: " + type(skills).__name__)
        return

    # Required tier fields
    for tier in SKILLS_REQUIRED_FIELDS:
        if tier not in skills:
            result.error(f"[skills].{tier} is missing (required)")

    # Unknown fields
    for field in skills:
        if field not in SKILLS_ALL_FIELDS:
            result.warn(f"[skills] has unknown field: '{field}'")

    # Validate each tier
    all_skill_names: list[str] = []
    for tier in SKILLS_REQUIRED_FIELDS:
        tier_list = skills.get(tier)
        if tier_list is None:
            continue

        if not isinstance(tier_list, list):
            result.error(
                f"[skills].{tier} must be an array, got: {type(tier_list).__name__}"
            )
            continue

        if not all(isinstance(s, str) for s in tier_list):
            result.error(f"[skills].{tier} must contain only strings")
            continue

        # Check max items
        max_items = TIER_MAX_ITEMS.get(tier)
        if max_items is not None and len(tier_list) > max_items:
            result.error(
                f"[skills].{tier} has {len(tier_list)} items, max is {max_items}"
            )

        # Check for empty skill names
        for skill_name in tier_list:
            if not skill_name.strip():
                result.error(f"[skills].{tier} contains an empty skill name")

        all_skill_names.extend(tier_list)

    # Check for duplicates across tiers
    seen: set[str] = set()
    for name in all_skill_names:
        if name in seen:
            result.error(
                f"Skill '{name}' appears in multiple tiers (must be unique across "
                f"primary/secondary/specialized)"
            )
        seen.add(name)

    # Verify skills exist in index (if index provided)
    if index_skills is not None:
        for name in all_skill_names:
            if name not in index_skills:
                result.warn(
                    f"Skill '{name}' not found in skill-index.json "
                    f"(may be unindexed or misspelled)"
                )

    # Validate excluded section (optional)
    excluded = skills.get("excluded")
    if excluded is not None:
        if not isinstance(excluded, dict):
            result.error(
                f"[skills.excluded] must be a table/dict, "
                f"got: {type(excluded).__name__}"
            )
        elif not all(isinstance(v, str) for v in excluded.values()):
            result.error(
                "[skills.excluded] values must be strings (exclusion reasons)"
            )


def validate_recommendation_section(
    data: dict[str, Any], section: str, result: ValidationResult
) -> None:
    """Validate a recommendation section (agents, mcp, hooks, lsp)."""
    sec = data.get(section)
    if sec is None:
        return  # All optional

    if not isinstance(sec, dict):
        result.error(f"[{section}] must be a table/dict, got: {type(sec).__name__}")
        return

    rec = sec.get("recommended")
    if rec is not None:
        if not isinstance(rec, list):
            result.error(
                f"[{section}].recommended must be an array, "
                f"got: {type(rec).__name__}"
            )
        elif not all(isinstance(r, str) for r in rec):
            result.error(f"[{section}].recommended must contain only strings")

    # Unknown fields
    for field in sec:
        if field != "recommended":
            result.warn(f"[{section}] has unknown field: '{field}'")


def validate_toml(
    data: dict[str, Any],
    result: ValidationResult,
    index_skills: set[str] | None = None,
) -> None:
    """Run all validations on parsed TOML data."""
    # Check for unknown top-level sections
    for key in data:
        if key not in ALL_KNOWN_SECTIONS:
            result.warn(f"Unknown top-level section: '[{key}]'")

    validate_agent_section(data, result)
    validate_requirements_section(data, result)
    validate_skills_section(data, result, index_skills)
    for section in ("agents", "commands", "rules", "mcp", "hooks", "lsp"):
        validate_recommendation_section(data, section, result)


def load_index_skills(index_path: Path) -> set[str] | None:
    """Load skill names from skill-index.json for cross-referencing."""
    if not index_path.exists():
        return None
    with open(index_path) as f:
        index = json.load(f)
    return set(index.get("skills", {}).keys())


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate .agent.toml files against the PSS schema"
    )
    parser.add_argument(
        "toml_file", nargs="?", help="Path to the .agent.toml file to validate"
    )
    parser.add_argument(
        "--check-index",
        action="store_true",
        help="Verify recommended skills exist in ~/.claude/cache/skill-index.json",
    )
    parser.add_argument(
        "--index",
        help="Custom path to skill-index.json (default: ~/.claude/cache/skill-index.json)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show warnings in addition to errors",
    )
    parser.add_argument(
        "--schema",
        action="store_true",
        help="Print the path to the JSON schema file and exit",
    )

    args = parser.parse_args()

    # --schema flag: print schema path and exit
    if args.schema:
        schema_path = (
            Path(__file__).parent.parent / "schemas" / "pss-agent-toml-schema.json"
        )
        print(str(schema_path))
        return 0

    # toml_file is required when not using --schema
    if args.toml_file is None:
        parser.error("toml_file is required")

    toml_path = Path(args.toml_file)

    # Check file exists
    if not toml_path.exists():
        print(f"ERROR: File not found: {toml_path}", file=sys.stderr)
        return 2

    if not toml_path.name.endswith(".toml"):
        print(
            f"WARNING: File does not have .toml extension: {toml_path.name}",
            file=sys.stderr,
        )

    # Parse TOML
    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        print(f"ERROR: Invalid TOML syntax: {e}", file=sys.stderr)
        return 2

    # Load index skills if --check-index
    index_skills: set[str] | None = None
    if args.check_index:
        if args.index:
            index_path = Path(args.index)
        else:
            index_path = Path.home() / ".claude" / "cache" / "skill-index.json"
        index_skills = load_index_skills(index_path)
        if index_skills is None:
            print(
                f"WARNING: Could not load skill index from {index_path}",
                file=sys.stderr,
            )

    # Validate
    result = ValidationResult()
    validate_toml(data, result, index_skills)

    # Report
    if result.is_valid:
        agent_name = data.get("agent", {}).get("name", "unknown")
        skill_counts = []
        skills = data.get("skills", {})
        for tier in ("primary", "secondary", "specialized"):
            count = len(skills.get(tier, []))
            skill_counts.append(f"{count} {tier}")
        print(f"VALID: {toml_path.name} (agent: {agent_name}, {', '.join(skill_counts)})")
        if args.verbose and result.warnings:
            print(result.report(verbose=True))
        return 0
    else:
        print(f"INVALID: {toml_path.name}")
        print(result.report(verbose=args.verbose))
        return 1


if __name__ == "__main__":
    sys.exit(main())
