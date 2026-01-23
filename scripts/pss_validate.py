#!/usr/bin/env python3
"""
PSS File Format Validator

Validates .pss (Perfect Skill Suggester) matcher files against the v1.0 schema.

Usage:
    python pss_validate.py <file.pss> [--verbose]
    python pss_validate.py --dir <directory> [--verbose]
"""

import json
import sys
import hashlib
import re
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    """Result of validating a .pss file."""

    file_path: Path
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_schema() -> dict[str, Any]:
    """Load the PSS v1.0 JSON schema."""
    schema_path = Path(__file__).parent.parent / "schemas" / "pss-v1.schema.json"
    if not schema_path.exists():
        # Inline minimal schema if file not found
        return {
            "required": ["version", "skill", "matchers", "metadata"],
            "properties": {
                "version": {"const": "1.0"},
                "skill": {"required": ["name", "type"]},
                "matchers": {"required": ["keywords"]},
                "metadata": {"required": ["generated_by", "generated_at"]},
            },
        }
    with open(schema_path) as f:
        result: dict[str, Any] = json.load(f)
        return result


def validate_pss_file(file_path: Path, verbose: bool = False) -> ValidationResult:
    """
    Validate a single .pss file.

    Args:
        file_path: Path to the .pss file
        verbose: Whether to include detailed warnings

    Returns:
        ValidationResult with errors and warnings
    """
    result = ValidationResult(file_path=file_path, valid=True)

    # Check file exists
    if not file_path.exists():
        result.valid = False
        result.errors.append(f"File not found: {file_path}")
        return result

    # Check file extension
    if file_path.suffix != ".pss":
        result.warnings.append(
            f"File extension should be .pss, got: {file_path.suffix}"
        )

    # Load JSON
    try:
        with open(file_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        result.valid = False
        result.errors.append(f"Invalid JSON: {e}")
        return result

    # Validate required fields
    required_fields = ["version", "skill", "matchers", "metadata"]
    for field_name in required_fields:
        if field_name not in data:
            result.valid = False
            result.errors.append(f"Missing required field: {field_name}")

    if not result.valid:
        return result

    # Validate version
    if data["version"] != "1.0":
        result.valid = False
        result.errors.append(f"Invalid version: {data['version']} (expected '1.0')")

    # Validate skill object
    skill = data.get("skill", {})
    if "name" not in skill:
        result.valid = False
        result.errors.append("Missing skill.name")
    elif not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$", skill["name"]):
        result.valid = False
        result.errors.append(
            f"Invalid skill.name format: {skill['name']} (must be kebab-case)"
        )

    if "type" not in skill:
        result.valid = False
        result.errors.append("Missing skill.type")
    elif skill["type"] not in ["skill", "agent", "command"]:
        result.valid = False
        result.errors.append(
            f"Invalid skill.type: {skill['type']} (must be skill|agent|command)"
        )

    if "source" in skill and skill["source"] not in ["user", "project", "plugin"]:
        result.valid = False
        result.errors.append(
            f"Invalid skill.source: {skill['source']} (must be user|project|plugin)"
        )

    # Validate matchers object
    matchers = data.get("matchers", {})
    if "keywords" not in matchers:
        result.valid = False
        result.errors.append("Missing matchers.keywords")
    elif not isinstance(matchers["keywords"], list):
        result.valid = False
        result.errors.append("matchers.keywords must be an array")
    elif len(matchers["keywords"]) == 0:
        result.valid = False
        result.errors.append("matchers.keywords cannot be empty")
    else:
        # Validate keyword format
        for i, kw in enumerate(matchers["keywords"]):
            if not isinstance(kw, str):
                result.valid = False
                result.errors.append(f"matchers.keywords[{i}] must be a string")
            elif kw != kw.lower():
                result.warnings.append(
                    f"matchers.keywords[{i}] should be lowercase: '{kw}'"
                )

        # Check for duplicates
        seen = set()
        for kw in matchers["keywords"]:
            if kw in seen:
                result.warnings.append(f"Duplicate keyword: '{kw}'")
            seen.add(kw)

    # Validate optional matchers fields
    for field_name in ["intents", "patterns", "directories", "negative_keywords"]:
        if field_name in matchers:
            if not isinstance(matchers[field_name], list):
                result.valid = False
                result.errors.append(f"matchers.{field_name} must be an array")
            else:
                for i, item in enumerate(matchers[field_name]):
                    if not isinstance(item, str):
                        result.valid = False
                        result.errors.append(
                            f"matchers.{field_name}[{i}] must be a string"
                        )

    # Validate patterns are valid regex
    if "patterns" in matchers and isinstance(matchers["patterns"], list):
        for i, pattern in enumerate(matchers["patterns"]):
            if isinstance(pattern, str):
                try:
                    re.compile(pattern)
                except re.error as e:
                    result.valid = False
                    result.errors.append(
                        f"Invalid regex in matchers.patterns[{i}]: {e}"
                    )

    # Validate scoring object
    if "scoring" in data:
        scoring = data["scoring"]
        if not isinstance(scoring, dict):
            result.valid = False
            result.errors.append("scoring must be an object")
        else:
            if "tier" in scoring and scoring["tier"] not in [
                "primary",
                "secondary",
                "utility",
            ]:
                result.valid = False
                result.errors.append(
                    f"Invalid scoring.tier: {scoring['tier']} "
                    "(must be primary|secondary|utility)"
                )

            if "boost" in scoring:
                if not isinstance(scoring["boost"], int):
                    result.valid = False
                    result.errors.append("scoring.boost must be an integer")
                elif not (-10 <= scoring["boost"] <= 10):
                    result.valid = False
                    result.errors.append(
                        f"scoring.boost out of range: {scoring['boost']} "
                        "(must be -10 to +10)"
                    )

    # Validate metadata object
    metadata = data.get("metadata", {})
    if "generated_by" not in metadata:
        result.valid = False
        result.errors.append("Missing metadata.generated_by")
    elif metadata["generated_by"] not in ["ai", "manual", "hybrid"]:
        result.valid = False
        result.errors.append(
            f"Invalid metadata.generated_by: {metadata['generated_by']} "
            "(must be ai|manual|hybrid)"
        )

    if "generated_at" not in metadata:
        result.valid = False
        result.errors.append("Missing metadata.generated_at")
    elif not isinstance(metadata["generated_at"], str):
        result.valid = False
        result.errors.append("metadata.generated_at must be a string")

    if "skill_hash" in metadata:
        if not re.match(r"^[a-f0-9]{64}$", metadata["skill_hash"]):
            result.warnings.append("Invalid skill_hash format (expected SHA-256)")

    # Verbose checks
    if verbose and result.valid:
        # Check for keyword count
        kw_count = len(matchers.get("keywords", []))
        if kw_count < 5:
            result.warnings.append(f"Low keyword count ({kw_count}), recommend 5-15")
        elif kw_count > 15:
            result.warnings.append(f"High keyword count ({kw_count}), recommend 5-15")

        # Check for missing optional fields
        if "intents" not in matchers:
            result.warnings.append("Consider adding intents for better matching")
        if "scoring" not in data:
            result.warnings.append("Consider adding scoring hints (tier, category)")
        if "skill_hash" not in metadata:
            result.warnings.append("Consider adding skill_hash for staleness detection")

    # Check accompanying SKILL.md
    skill_md_path = file_path.parent / "SKILL.md"
    if skill_md_path.exists():
        if "skill_hash" in metadata:
            # Verify hash matches
            with open(skill_md_path, "rb") as f:
                actual_hash = hashlib.sha256(f.read()).hexdigest()
            if actual_hash != metadata["skill_hash"]:
                result.warnings.append(
                    "skill_hash mismatch - SKILL.md may have changed"
                )
    else:
        result.warnings.append("No SKILL.md found alongside .pss file")

    return result


def validate_directory(dir_path: Path, verbose: bool = False) -> list[ValidationResult]:
    """
    Validate all .pss files in a directory (recursively).

    Args:
        dir_path: Directory to search
        verbose: Whether to include detailed warnings

    Returns:
        List of ValidationResults
    """
    results = []
    for pss_file in dir_path.rglob("*.pss"):
        results.append(validate_pss_file(pss_file, verbose))
    return results


def print_result(result: ValidationResult, verbose: bool = False) -> None:
    """Print validation result with colors."""
    if result.valid:
        status = "\033[92mVALID\033[0m"
    else:
        status = "\033[91mINVALID\033[0m"

    print(f"\n{result.file_path}: {status}")

    for error in result.errors:
        print(f"  \033[91mERROR\033[0m: {error}")

    if verbose:
        for warning in result.warnings:
            print(f"  \033[93mWARN\033[0m:  {warning}")


def main() -> int:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate PSS (Perfect Skill Suggester) matcher files"
    )
    parser.add_argument("path", nargs="?", help="Path to .pss file or directory")
    parser.add_argument("--dir", help="Directory to search for .pss files")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show warnings and recommendations"
    )
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()

    # Determine path
    if args.dir:
        path = Path(args.dir)
        if not path.is_dir():
            print(f"Error: {path} is not a directory", file=sys.stderr)
            return 1
        results = validate_directory(path, args.verbose)
    elif args.path:
        path = Path(args.path)
        if path.is_dir():
            results = validate_directory(path, args.verbose)
        else:
            results = [validate_pss_file(path, args.verbose)]
    else:
        # Default to current directory
        results = validate_directory(Path("."), args.verbose)

    if not results:
        print("No .pss files found")
        return 0

    # Output results
    if args.json:
        output = []
        for result in results:
            output.append(
                {
                    "file": str(result.file_path),
                    "valid": result.valid,
                    "errors": result.errors,
                    "warnings": result.warnings,
                }
            )
        print(json.dumps(output, indent=2))
    else:
        for result in results:
            print_result(result, args.verbose)

        # Summary
        valid_count = sum(1 for r in results if r.valid)
        total_count = len(results)
        print(f"\n{'=' * 50}")
        invalid_count = total_count - valid_count
        print(
            f"Validated {total_count} file(s): "
            f"{valid_count} valid, {invalid_count} invalid"
        )

    # Return non-zero if any invalid
    return 0 if all(r.valid for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
