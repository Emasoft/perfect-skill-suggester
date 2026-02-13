#!/usr/bin/env python3
"""
PSS Index Validator - Post-reindex validation for skill-index.json.

Validates the generated skill index after a /pss-reindex-skills run.
If the index is invalid, incomplete, or corrupt:
  1. Deletes the bad index
  2. Restores the backup from /tmp/pss-backup-*
  3. Cleans up residual .pss files in /tmp/pss-queue/

Usage:
    python pss_validate_index.py
    python pss_validate_index.py --pass 1
    python pss_validate_index.py --pass 2
    python pss_validate_index.py --backup-dir /tmp/pss-backup-20260212_143000
    python pss_validate_index.py --checklist ~/.claude/cache/skill-checklist.md
    python pss_validate_index.py --verbose
    python pss_validate_index.py --json
"""

import argparse
import glob
import json
import shutil
import sys
from pathlib import Path
from typing import Any

# -- Constants --

DEFAULT_INDEX_PATH = Path.home() / ".claude" / "cache" / "skill-index.json"
DEFAULT_CHECKLIST_PATH = Path.home() / ".claude" / "cache" / "skill-checklist.md"
DEFAULT_REGISTRY_PATH = Path.home() / ".claude" / "cache" / "domain-registry.json"
PSS_QUEUE_DIR = Path("/tmp/pss-queue")

VALID_CATEGORIES = frozenset(
    [
        "web-frontend",
        "web-backend",
        "mobile",
        "devops-cicd",
        "testing",
        "security",
        "data-ml",
        "research",
        "code-quality",
        "debugging",
        "infrastructure",
        "cli-tools",
        "visualization",
        "ai-llm",
        "project-mgmt",
        "plugin-dev",
    ]
)

VALID_PLATFORMS = frozenset(
    [
        "ios",
        "android",
        "macos",
        "windows",
        "linux",
        "web",
        "universal",
    ]
)

VALID_LANGUAGES = frozenset(
    [
        "swift",
        "kotlin",
        "python",
        "typescript",
        "javascript",
        "rust",
        "go",
        "java",
        "c",
        "cpp",
        "csharp",
        "ruby",
        "php",
        "dart",
        "any",
    ]
)

VALID_SOURCES = frozenset(["user", "project", "plugin"])

VALID_TYPES = frozenset(["skill", "agent", "command"])

VALID_TIERS = frozenset(["primary", "secondary", "specialized"])

VALID_INTENTS = frozenset(
    [
        "deploy",
        "build",
        "test",
        "review",
        "debug",
        "refactor",
        "migrate",
        "configure",
        "install",
        "create",
        "delete",
        "monitor",
        "analyze",
        "optimize",
        "secure",
        "audit",
        "document",
        "design",
        "plan",
        "implement",
        "validate",
        "generate",
        "convert",
        "search",
        "explore",
        "visualize",
        "animate",
        "record",
        "transcribe",
        "translate",
        "publish",
        "package",
        "lint",
        "format",
        "profile",
        "benchmark",
        "scaffold",
        # Allow 'list' and 'add' which some skills use
        "list",
        "add",
        "open",
        "merge",
        "link",
    ]
)

# Pass 1 required fields (must be present and non-empty)
PASS1_REQUIRED_FIELDS = [
    "source",
    "path",
    "type",
    "keywords",
    "category",
    "description",
]

# Pass 1 array fields (must be arrays if present)
PASS1_ARRAY_FIELDS = [
    "keywords",
    "intents",
    "patterns",
    "directories",
    "use_cases",
    "platforms",
    "frameworks",
    "languages",
    "domains",
    "tools",
    "file_types",
]

# Pass 2 co_usage sub-fields
CO_USAGE_ARRAY_FIELDS = ["usually_with", "precedes", "follows", "alternatives"]

# Co-usage quantity limits
CO_USAGE_LIMITS = {
    "usually_with": 5,
    "precedes": 3,
    "follows": 3,
    "alternatives": 3,
}


# -- Error collection --


class ValidationResult:
    """Collects validation errors and warnings."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.skill_errors: dict[str, list[str]] = {}
        self.skill_warnings: dict[str, list[str]] = {}
        self.stats: dict[str, Any] = {}

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def skill_error(self, skill_name: str, msg: str) -> None:
        self.skill_errors.setdefault(skill_name, []).append(msg)

    def skill_warning(self, skill_name: str, msg: str) -> None:
        self.skill_warnings.setdefault(skill_name, []).append(msg)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0 and len(self.skill_errors) == 0

    @property
    def total_errors(self) -> int:
        skill_err_count = sum(len(v) for v in self.skill_errors.values())
        return len(self.errors) + skill_err_count

    @property
    def total_warnings(self) -> int:
        skill_warn_count = sum(len(v) for v in self.skill_warnings.values())
        return len(self.warnings) + skill_warn_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.is_valid,
            "total_errors": self.total_errors,
            "total_warnings": self.total_warnings,
            "global_errors": self.errors,
            "global_warnings": self.warnings,
            "skill_errors": self.skill_errors,
            "skill_warnings": self.skill_warnings,
            "stats": self.stats,
        }


# -- Checklist parsing --


def parse_checklist(checklist_path: Path) -> list[str]:
    """Parse skill-checklist.md to extract expected skill names.

    The checklist format has lines like:
      - [ ] skill-name (source: user, path: /path/to/SKILL.md)
      - [x] skill-name (source: plugin, path: /path/to/SKILL.md)

    Returns a list of skill names (without checkboxes or metadata).
    """
    if not checklist_path.exists():
        return []

    skill_names: list[str] = []
    text = checklist_path.read_text(encoding="utf-8")

    for line in text.splitlines():
        stripped = line.strip()
        # Match lines like "- [ ] skill-name (...)" or "- [x] skill-name (...)"
        if stripped.startswith("- [") and "] " in stripped:
            # Extract everything after "] " and before " ("
            after_checkbox = stripped.split("] ", 1)[1]
            # The skill name is before the first " ("
            if " (" in after_checkbox:
                name = after_checkbox.split(" (", 1)[0].strip()
            else:
                name = after_checkbox.strip()
            if name:
                skill_names.append(name)

    return skill_names


# -- Backup discovery --


def find_latest_backup_dir() -> Path | None:
    """Find the most recent /tmp/pss-backup-* directory.

    Returns the path to the latest backup directory, or None if none found.
    """
    pattern = "/tmp/pss-backup-*"
    candidates = sorted(glob.glob(pattern), reverse=True)
    for candidate_str in candidates:
        candidate = Path(candidate_str)
        if candidate.is_dir():
            return candidate
    return None


# -- Validation functions --


def validate_top_level(index: dict[str, Any], result: ValidationResult) -> None:
    """Validate top-level index structure."""
    # Required top-level fields
    if "version" not in index:
        result.error("Missing required field: 'version'")
    elif index["version"] != "3.0":
        result.error(f"Invalid version: '{index['version']}' (expected '3.0')")

    if "pass" not in index:
        result.error("Missing required field: 'pass'")
    elif index["pass"] not in (1, 2):
        result.error(f"Invalid pass: {index['pass']} (expected 1 or 2)")

    if "generated" not in index:
        result.error("Missing required field: 'generated'")

    if "skills" not in index:
        result.error("Missing required field: 'skills'")
    elif not isinstance(index["skills"], dict):
        skills_type = type(index["skills"]).__name__
        result.error(f"'skills' must be an object, got {skills_type}")

    # Check skills_count consistency
    skills = index.get("skills", {})
    declared_count = index.get("skills_count", index.get("skill_count", -1))
    actual_count = len(skills) if isinstance(skills, dict) else 0
    if declared_count >= 0 and declared_count != actual_count:
        result.warning(
            f"skills_count mismatch: declared {declared_count}, actual {actual_count}"
        )

    result.stats["total_skills"] = actual_count
    result.stats["index_pass"] = index.get("pass", 0)


def validate_skill_pass1(
    skill_name: str,
    entry: dict[str, Any],
    result: ValidationResult,
) -> None:
    """Validate a single skill's Pass 1 fields."""
    # Required fields must exist and be non-empty
    for field in PASS1_REQUIRED_FIELDS:
        value = entry.get(field)
        if value is None:
            result.skill_error(
                skill_name,
                f"Missing required field: '{field}'",
            )
        elif isinstance(value, str) and not value.strip():
            result.skill_error(
                skill_name,
                f"Empty required field: '{field}'",
            )
        elif isinstance(value, list) and len(value) == 0 and field == "keywords":
            result.skill_error(
                skill_name,
                "keywords array is empty (must have 1+ entries)",
            )

    # Validate source enum
    source = entry.get("source")
    if source and source not in VALID_SOURCES:
        result.skill_error(
            skill_name,
            f"Invalid source: '{source}' (valid: {sorted(VALID_SOURCES)})",
        )

    # Validate type enum
    skill_type = entry.get("type")
    if skill_type and skill_type not in VALID_TYPES:
        result.skill_error(
            skill_name,
            f"Invalid type: '{skill_type}' (valid: {sorted(VALID_TYPES)})",
        )

    # Validate category enum
    category = entry.get("category")
    if category and category not in VALID_CATEGORIES:
        result.skill_error(
            skill_name,
            f"Invalid category: '{category}' (valid: {sorted(VALID_CATEGORIES)})",
        )

    # Validate array fields are actually arrays
    for field in PASS1_ARRAY_FIELDS:
        value = entry.get(field)
        if value is not None and not isinstance(value, list):
            val_type = type(value).__name__
            result.skill_error(
                skill_name,
                f"Field '{field}' must be an array, got {val_type}",
            )

    # Validate platforms enum values
    platforms = entry.get("platforms", [])
    if isinstance(platforms, list):
        for p in platforms:
            if p not in VALID_PLATFORMS:
                result.skill_error(
                    skill_name,
                    f"Invalid platform: '{p}' (valid: {sorted(VALID_PLATFORMS)})",
                )

    # Validate languages enum values
    languages = entry.get("languages", [])
    if isinstance(languages, list):
        for lang in languages:
            if lang not in VALID_LANGUAGES:
                result.skill_error(
                    skill_name,
                    f"Invalid language: '{lang}' (valid: {sorted(VALID_LANGUAGES)})",
                )

    # Validate intents enum values
    intents = entry.get("intents", [])
    if isinstance(intents, list):
        for intent in intents:
            if intent not in VALID_INTENTS:
                result.skill_warning(
                    skill_name,
                    f"Unknown intent: '{intent}' (not in standard list)",
                )

    # Validate keywords quality
    keywords = entry.get("keywords", [])
    if isinstance(keywords, list):
        if len(keywords) < 5:
            result.skill_warning(
                skill_name,
                f"Only {len(keywords)} keywords (expected 10-20)",
            )
        for kw in keywords:
            if not isinstance(kw, str):
                kw_type = type(kw).__name__
                result.skill_error(
                    skill_name,
                    f"Keyword must be string, got {kw_type}: {kw}",
                )
            elif kw != kw.lower():
                result.skill_warning(
                    skill_name,
                    f"Keyword not lowercase: '{kw}'",
                )

    # Validate domain_gates structure
    domain_gates = entry.get("domain_gates")
    if domain_gates is not None:
        if not isinstance(domain_gates, dict):
            gate_type = type(domain_gates).__name__
            result.skill_error(
                skill_name,
                f"domain_gates must be an object, got {gate_type}",
            )
        else:
            for gate_name, gate_keywords in domain_gates.items():
                if not isinstance(gate_name, str) or not gate_name.strip():
                    result.skill_error(
                        skill_name,
                        "domain_gates key must be a"
                        " non-empty string,"
                        f" got: {gate_name!r}",
                    )
                if not isinstance(gate_keywords, list):
                    gk_type = type(gate_keywords).__name__
                    result.skill_error(
                        skill_name,
                        f"domain_gates['{gate_name}'] must be an array, got {gk_type}",
                    )
                elif len(gate_keywords) == 0:
                    result.skill_error(
                        skill_name,
                        f"domain_gates['{gate_name}']"
                        " is empty"
                        " (must have at least 1 keyword)",
                    )
                else:
                    for kw in gate_keywords:
                        if not isinstance(kw, str):
                            result.skill_error(
                                skill_name,
                                f"domain_gates['{gate_name}']"
                                f" contains non-string: {kw!r}",
                            )
                        elif kw != kw.lower():
                            result.skill_warning(
                                skill_name,
                                f"domain_gates['{gate_name}']"
                                f" keyword not lowercase: '{kw}'",
                            )

    # Validate path exists (warning only since paths may change)
    path = entry.get("path", "")
    if path and not Path(path).exists():
        result.skill_warning(
            skill_name,
            f"SKILL.md path does not exist: {path}",
        )


def validate_skill_pass2(
    skill_name: str,
    entry: dict[str, Any],
    all_skill_names: set[str],
    result: ValidationResult,
) -> None:
    """Validate a single skill's Pass 2 fields."""
    # co_usage must exist
    co_usage = entry.get("co_usage")
    if co_usage is None:
        result.skill_error(
            skill_name,
            "Missing 'co_usage' field (Pass 2 not completed)",
        )
        return

    if not isinstance(co_usage, dict):
        cu_type = type(co_usage).__name__
        result.skill_error(
            skill_name,
            f"'co_usage' must be an object, got {cu_type}",
        )
        return

    # Validate co_usage array fields
    for field in CO_USAGE_ARRAY_FIELDS:
        value = co_usage.get(field, [])
        if not isinstance(value, list):
            val_type = type(value).__name__
            result.skill_error(
                skill_name,
                f"co_usage.{field} must be an array, got {val_type}",
            )
            continue

        # Check quantity limits
        limit = CO_USAGE_LIMITS.get(field, 5)
        if len(value) > limit:
            result.skill_warning(
                skill_name,
                f"co_usage.{field} has {len(value)} entries (max {limit})",
            )

        # Check that referenced skills exist in the index
        for ref_skill in value:
            if not isinstance(ref_skill, str):
                result.skill_error(
                    skill_name,
                    f"co_usage.{field} contains non-string: {ref_skill}",
                )
            elif ref_skill not in all_skill_names:
                result.skill_warning(
                    skill_name,
                    f"co_usage.{field} references unknown skill: '{ref_skill}'",
                )

    # Validate rationale exists and is non-empty
    rationale = co_usage.get("rationale", "")
    if not rationale or not rationale.strip():
        result.skill_warning(skill_name, "co_usage.rationale is empty")

    # Validate tier
    tier = entry.get("tier")
    if tier is None:
        result.skill_warning(
            skill_name,
            "Missing 'tier' field (Pass 2 should set this)",
        )
    elif tier not in VALID_TIERS:
        result.skill_error(
            skill_name,
            f"Invalid tier: '{tier}' (valid: {sorted(VALID_TIERS)})",
        )

    # Check for self-references in co_usage
    for field in CO_USAGE_ARRAY_FIELDS:
        value = co_usage.get(field, [])
        if isinstance(value, list) and skill_name in value:
            result.skill_error(
                skill_name,
                f"co_usage.{field} contains self-reference",
            )


def validate_completeness(
    index: dict[str, Any],
    expected_skills: list[str],
    result: ValidationResult,
) -> None:
    """Check that ALL expected skills are present."""
    skills = index.get("skills", {})
    indexed_names = set(skills.keys())
    expected_names = set(expected_skills)

    missing = expected_names - indexed_names
    extra = indexed_names - expected_names

    if missing:
        result.error(
            f"{len(missing)} skills from checklist"
            f" are MISSING from index: {sorted(missing)}"
        )

    if extra:
        # Extra skills are a warning (index is superset by design)
        extra_sample = sorted(extra)[:10]
        suffix = "..." if len(extra) > 10 else ""
        result.warning(
            f"{len(extra)} skills in index but not in"
            " checklist (may be from previous"
            f" runs): {extra_sample}{suffix}"
        )

    result.stats["expected_skills"] = len(expected_names)
    result.stats["indexed_skills"] = len(indexed_names)
    result.stats["missing_skills"] = len(missing)
    result.stats["extra_skills"] = len(extra)
    if missing:
        result.stats["missing_skill_names"] = sorted(missing)


# -- Domain registry validation --


def validate_domain_registry(
    registry_path: Path,
    index: dict[str, Any],
    result: ValidationResult,
    verbose: bool = False,
) -> None:
    """Validate domain-registry.json against the skill index.

    Checks:
    - Registry file exists and is valid JSON
    - Required top-level fields
    - Each domain entry has required fields
    - All skills referenced exist in the index
    - All skills with domain_gates are in the registry
    - No empty keyword lists
    """
    if not registry_path.exists():
        result.warning(
            f"Domain registry not found at {registry_path}"
            " (run pss_aggregate_domains.py)"
        )
        return

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        result.error(f"Domain registry is not valid JSON: {exc}")
        return

    if verbose:
        print(f"Validating domain registry: {registry_path}")

    # Check top-level fields
    reg_ver = registry.get("version")
    if reg_ver != "1.0":
        result.error(f"Domain registry version must be '1.0', got: {reg_ver!r}")

    if "generated" not in registry:
        result.error("Domain registry missing 'generated' field")

    if "domains" not in registry:
        result.error("Domain registry missing 'domains' field")
        return

    domains = registry.get("domains", {})
    if not isinstance(domains, dict):
        dom_type = type(domains).__name__
        result.error(f"Domain registry 'domains' must be an object, got {dom_type}")
        return

    # Check declared count matches actual
    declared_count = registry.get("domain_count", -1)
    actual_count = len(domains)
    if declared_count >= 0 and declared_count != actual_count:
        result.warning(
            "Domain registry domain_count mismatch:"
            f" declared {declared_count},"
            f" actual {actual_count}"
        )

    all_skill_names = set(index.get("skills", {}).keys())
    registry_referenced_skills: set[str] = set()

    # Validate each domain entry
    for domain_name, entry in domains.items():
        if not isinstance(entry, dict):
            result.error(f"Domain '{domain_name}' entry must be an object")
            continue

        # Required fields
        required = (
            "canonical_name",
            "aliases",
            "example_keywords",
            "skills",
        )
        for field in required:
            if field not in entry:
                result.error(
                    f"Domain '{domain_name}' missing required field: '{field}'"
                )

        # canonical_name must match the key
        canon = entry.get("canonical_name")
        if canon != domain_name:
            result.warning(
                f"Domain '{domain_name}'"
                " canonical_name mismatch:"
                f" key is '{domain_name}'"
                f" but field says '{canon}'"
            )

        # aliases must be non-empty array of strings
        aliases = entry.get("aliases", [])
        if not isinstance(aliases, list) or len(aliases) == 0:
            result.error(f"Domain '{domain_name}' aliases must be a non-empty array")
        else:
            for alias in aliases:
                if not isinstance(alias, str):
                    result.error(
                        f"Domain '{domain_name}' alias must be string, got: {alias!r}"
                    )

        # example_keywords must be non-empty array of strings
        keywords = entry.get("example_keywords", [])
        if not isinstance(keywords, list) or len(keywords) == 0:
            result.error(
                f"Domain '{domain_name}' example_keywords must be a non-empty array"
            )
        else:
            for kw in keywords:
                if not isinstance(kw, str):
                    result.error(
                        f"Domain '{domain_name}' keyword must be string, got: {kw!r}"
                    )
                elif kw != kw.lower() and kw != "generic":
                    result.warning(
                        f"Domain '{domain_name}' keyword not lowercase: '{kw}'"
                    )

        # has_generic consistency check
        has_generic_flag = entry.get("has_generic", False)
        has_generic_actual = isinstance(keywords, list) and "generic" in keywords
        if has_generic_flag != has_generic_actual:
            result.warning(
                f"Domain '{domain_name}'"
                f" has_generic flag ({has_generic_flag})"
                " does not match presence of"
                " 'generic' in keywords"
                f" ({has_generic_actual})"
            )

        # skills must reference existing skills
        skills = entry.get("skills", [])
        if isinstance(skills, list):
            for skill_ref in skills:
                registry_referenced_skills.add(skill_ref)
                if skill_ref not in all_skill_names:
                    result.warning(
                        f"Domain '{domain_name}'"
                        " references unknown"
                        f" skill: '{skill_ref}'"
                    )

        # skill_count consistency
        skill_count = entry.get("skill_count", -1)
        if isinstance(skills, list) and skill_count >= 0 and skill_count != len(skills):
            result.warning(
                f"Domain '{domain_name}'"
                f" skill_count ({skill_count})"
                f" != len(skills) ({len(skills)})"
            )

    # Cross-check: skills with domain_gates should be in registry
    skills_with_gates: set[str] = set()
    for skill_name, skill_entry in index.get("skills", {}).items():
        gates = skill_entry.get("domain_gates")
        if gates and isinstance(gates, dict) and len(gates) > 0:
            skills_with_gates.add(skill_name)

    missing_from_registry = skills_with_gates - registry_referenced_skills
    if missing_from_registry:
        n_missing = len(missing_from_registry)
        sample = sorted(missing_from_registry)[:5]
        suffix = "..." if len(missing_from_registry) > 5 else ""
        result.warning(
            f"{n_missing} skills have domain_gates"
            " but are not in registry:"
            f" {sample}{suffix}"
        )

    result.stats["registry_domains"] = actual_count
    result.stats["registry_skills_referenced"] = len(registry_referenced_skills)
    result.stats["skills_with_gates"] = len(skills_with_gates)

    if verbose:
        print(f"  Domains: {actual_count}")
        gates_count = len(skills_with_gates)
        print(f"  Skills with gates: {gates_count}")
        ref_count = len(registry_referenced_skills)
        print(f"  Skills in registry: {ref_count}")


# -- Main validation --


def validate_index(
    index_path: Path,
    checklist_path: Path,
    expected_pass: int | None,
    verbose: bool = False,
) -> ValidationResult:
    """Run all validation checks on the skill index.

    Args:
        index_path: Path to skill-index.json
        checklist_path: Path to skill-checklist.md
        expected_pass: Expected pass number (1 or 2),
            or None for auto-detect
        verbose: Print progress messages

    Returns:
        ValidationResult with all errors and warnings
    """
    result = ValidationResult()

    # Check index file exists
    if not index_path.exists():
        result.error(f"Index file does not exist: {index_path}")
        return result

    # Parse JSON
    try:
        text = index_path.read_text(encoding="utf-8")
        index: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError as exc:
        result.error(f"Index file is not valid JSON: {exc}")
        return result

    if verbose:
        print(f"Loaded index: {index_path}")

    # Top-level structure
    validate_top_level(index, result)
    if not result.is_valid:
        return result

    skills = index.get("skills", {})
    all_skill_names = set(skills.keys())
    index_pass = index.get("pass", 1)

    # Determine expected pass
    if expected_pass is not None:
        if index_pass != expected_pass:
            result.error(f"Index pass is {index_pass} but expected {expected_pass}")
    else:
        expected_pass = index_pass

    if verbose:
        print(f"Index pass: {index_pass}, skills: {len(skills)}")

    # Validate each skill
    pass1_ok = 0
    pass1_fail = 0
    pass2_ok = 0
    pass2_fail = 0
    pass2_missing = 0

    for skill_name, entry in skills.items():
        if not isinstance(entry, dict):
            entry_type = type(entry).__name__
            result.skill_error(
                skill_name,
                f"Skill entry must be an object, got {entry_type}",
            )
            continue

        # Pass 1 validation (always run)
        errors_before = len(result.skill_errors.get(skill_name, []))
        validate_skill_pass1(skill_name, entry, result)
        errors_after = len(result.skill_errors.get(skill_name, []))
        if errors_after > errors_before:
            pass1_fail += 1
        else:
            pass1_ok += 1

        # Pass 2 validation (only if expected)
        if expected_pass == 2:
            errors_before_p2 = len(result.skill_errors.get(skill_name, []))
            validate_skill_pass2(skill_name, entry, all_skill_names, result)
            errors_after_p2 = len(result.skill_errors.get(skill_name, []))
            if "co_usage" not in entry:
                pass2_missing += 1
            elif errors_after_p2 > errors_before_p2:
                pass2_fail += 1
            else:
                pass2_ok += 1

    result.stats["pass1_ok"] = pass1_ok
    result.stats["pass1_fail"] = pass1_fail
    if expected_pass == 2:
        result.stats["pass2_ok"] = pass2_ok
        result.stats["pass2_fail"] = pass2_fail
        result.stats["pass2_missing"] = pass2_missing

    # Completeness check against checklist
    expected_skills = parse_checklist(checklist_path)
    if expected_skills:
        if verbose:
            n_expected = len(expected_skills)
            print(f"Checklist: {n_expected} expected skills")
        validate_completeness(index, expected_skills, result)
    else:
        if verbose:
            print("No checklist found, skipping completeness check")
        result.warning("No skill checklist found - cannot verify completeness")

    return result


# -- Restore / cleanup --


def restore_backup(
    index_path: Path,
    backup_dir: Path | None,
    verbose: bool = False,
) -> bool:
    """Delete bad index and restore backup.

    Args:
        index_path: Path to the bad skill-index.json
        backup_dir: Path to the backup directory
        verbose: Print progress

    Returns:
        True if backup was restored, False if no backup available
    """
    # Delete the bad index
    if index_path.exists():
        index_path.unlink()
        if verbose:
            print(f"Deleted bad index: {index_path}")

    # Find backup directory if not specified
    if backup_dir is None:
        backup_dir = find_latest_backup_dir()

    if backup_dir is None:
        if verbose:
            print("No backup directory found - cannot restore")
        return False

    backup_index = backup_dir / "skill-index.json"
    if not backup_index.exists():
        if verbose:
            print(f"No backup index in {backup_dir}")
        return False

    # Restore the backup
    shutil.copy2(backup_index, index_path)
    if verbose:
        print(f"Restored backup from: {backup_index}")
    return True


def cleanup_pss_queue(verbose: bool = False) -> int:
    """Clean up residual .pss files in /tmp/pss-queue/.

    Returns the number of files cleaned up.
    """
    if not PSS_QUEUE_DIR.exists():
        return 0

    count = 0
    for pss_file in PSS_QUEUE_DIR.glob("*.pss"):
        pss_file.unlink()
        count += 1

    if verbose and count > 0:
        print(f"Cleaned up {count} residual .pss files from {PSS_QUEUE_DIR}")

    return count


# -- Reporting --


def print_report(result: ValidationResult, verbose: bool = False) -> None:
    """Print human-readable validation report."""
    stats = result.stats
    total = stats.get("total_skills", 0)

    if result.is_valid:
        print(f"\n[PASS] Index validation passed ({total} skills)")
    else:
        n_err = result.total_errors
        n_warn = result.total_warnings
        print(f"\n[FAIL] Index validation FAILED ({n_err} errors, {n_warn} warnings)")

    # Stats summary
    print("\nStats:")
    print(f"  Total skills: {total}")
    idx_pass = stats.get("index_pass", "?")
    print(f"  Index pass: {idx_pass}")
    p1_ok = stats.get("pass1_ok", 0)
    p1_fail = stats.get("pass1_fail", 0)
    print(f"  Pass 1 OK: {p1_ok}, Failed: {p1_fail}")
    if "pass2_ok" in stats:
        p2_ok = stats.get("pass2_ok", 0)
        p2_fail = stats.get("pass2_fail", 0)
        p2_miss = stats.get("pass2_missing", 0)
        print(f"  Pass 2 OK: {p2_ok}, Failed: {p2_fail}, Missing: {p2_miss}")
    if "expected_skills" in stats:
        expected = stats.get("expected_skills", 0)
        print(f"  Expected (from checklist): {expected}")
        missing = stats.get("missing_skills", 0)
        print(f"  Missing from index: {missing}")
    if "registry_domains" in stats:
        n_domains = stats.get("registry_domains", 0)
        n_gates = stats.get("skills_with_gates", 0)
        print(f"  Domain registry: {n_domains} domains, {n_gates} skills with gates")

    # Global errors
    if result.errors:
        print(f"\nGlobal errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  ERROR: {err}")

    # Global warnings
    if result.warnings and verbose:
        n_warn = len(result.warnings)
        print(f"\nGlobal warnings ({n_warn}):")
        for warn in result.warnings:
            print(f"  WARN: {warn}")

    # Per-skill errors
    if result.skill_errors:
        n_skills = len(result.skill_errors)
        print(f"\nSkill errors ({n_skills} skills):")
        for skill_name, errors in sorted(result.skill_errors.items()):
            print(f"  {skill_name}:")
            for err in errors:
                print(f"    ERROR: {err}")

    # Per-skill warnings (verbose only)
    if result.skill_warnings and verbose:
        n_skills = len(result.skill_warnings)
        print(f"\nSkill warnings ({n_skills} skills):")
        for skill_name, warnings in sorted(result.skill_warnings.items()):
            print(f"  {skill_name}:")
            for warn in warnings:
                print(f"    WARN: {warn}")


# -- CLI --


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate PSS skill-index.json after reindexing",
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=DEFAULT_INDEX_PATH,
        help=f"Path to skill-index.json (default: {DEFAULT_INDEX_PATH})",
    )
    parser.add_argument(
        "--checklist",
        type=Path,
        default=DEFAULT_CHECKLIST_PATH,
        help=f"Path to skill-checklist.md (default: {DEFAULT_CHECKLIST_PATH})",
    )
    parser.add_argument(
        "--pass",
        dest="expected_pass",
        type=int,
        choices=[1, 2],
        default=None,
        help="Expected pass number (default: auto-detect from index)",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="Backup directory for restore (default: latest /tmp/pss-backup-*)",
    )
    parser.add_argument(
        "--restore-on-failure",
        action="store_true",
        default=False,
        help="Automatically restore backup if validation fails",
    )
    parser.add_argument(
        "--cleanup-pss",
        action="store_true",
        default=False,
        help="Clean up residual .pss files in /tmp/pss-queue/ on failure",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY_PATH,
        help=f"Path to domain-registry.json (default: {DEFAULT_REGISTRY_PATH})",
    )
    parser.add_argument(
        "--validate-registry",
        action="store_true",
        default=False,
        help="Also validate the domain registry against the index",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Print detailed validation output",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        default=False,
        help="Output results as JSON",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Entry point: validate index and optionally restore on failure."""
    args = parse_args()

    index_path: Path = args.index.resolve()
    checklist_path: Path = args.checklist.resolve()

    # Run validation
    result = validate_index(
        index_path=index_path,
        checklist_path=checklist_path,
        expected_pass=args.expected_pass,
        verbose=args.verbose,
    )

    # Domain registry validation (optional, runs after index validation)
    if args.validate_registry:
        # Need to load the index again for cross-referencing
        if index_path.exists():
            try:
                index_data = json.loads(index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                index_data = {"skills": {}}
        else:
            index_data = {"skills": {}}

        validate_domain_registry(
            registry_path=args.registry.resolve(),
            index=index_data,
            result=result,
            verbose=args.verbose,
        )

    # Output results
    if args.json_output:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print_report(result, verbose=args.verbose)

    # Handle failure
    if not result.is_valid:
        if args.restore_on_failure:
            print("\n--- RESTORING BACKUP ---")
            restored = restore_backup(
                index_path=index_path,
                backup_dir=args.backup_dir,
                verbose=True,
            )
            if restored:
                print("Backup restored successfully.")
            else:
                print("WARNING: Could not restore backup. No backup found.")

        if args.cleanup_pss:
            cleaned = cleanup_pss_queue(verbose=True)
            if cleaned > 0:
                print(f"Cleaned up {cleaned} residual .pss files.")

        sys.exit(1)
    else:
        # Even on success, clean up any residual .pss files
        if args.cleanup_pss:
            cleaned = cleanup_pss_queue(verbose=args.verbose)

        sys.exit(0)


if __name__ == "__main__":
    main()
