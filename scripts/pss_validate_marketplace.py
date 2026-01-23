#!/usr/bin/env python3
"""
Marketplace Validator for Claude Code Plugin Marketplaces.

Validates marketplace.json according to the official Anthropic schema:
https://code.claude.com/docs/en/plugin-marketplaces.md

Usage:
    uv run python scripts/pss_validate_marketplace.py [marketplace_path]

If no path is provided, validates the emasoft-plugins marketplace.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Reserved marketplace names that cannot be used
RESERVED_MARKETPLACE_NAMES = {
    "claude-code-marketplace",
    "claude-code-plugins",
    "claude-plugins-official",
    "anthropic-marketplace",
    "anthropic-plugins",
    "agent-skills",
    "life-sciences",
}

# Patterns that suggest impersonating official marketplaces
IMPERSONATION_PATTERNS = [
    r"^official.*claude",
    r"^official.*anthropic",
    r"^claude.*official",
    r"^anthropic.*official",
    r"anthropic.*tools",
    r"claude.*official.*plugins",
]


@dataclass
class ValidationReport:
    """Collects validation results."""

    critical_issues: list[str] = field(default_factory=list)
    major_issues: list[str] = field(default_factory=list)
    minor_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)

    def critical(self, msg: str, location: str = "") -> None:
        loc = f" [{location}]" if location else ""
        self.critical_issues.append(f"CRITICAL{loc}: {msg}")

    def major(self, msg: str, location: str = "") -> None:
        loc = f" [{location}]" if location else ""
        self.major_issues.append(f"MAJOR{loc}: {msg}")

    def minor(self, msg: str, location: str = "") -> None:
        loc = f" [{location}]" if location else ""
        self.minor_issues.append(f"MINOR{loc}: {msg}")

    def warning(self, msg: str, location: str = "") -> None:
        loc = f" [{location}]" if location else ""
        self.warnings.append(f"WARNING{loc}: {msg}")

    def add_info(self, msg: str, location: str = "") -> None:
        loc = f" [{location}]" if location else ""
        self.info.append(f"INFO{loc}: {msg}")

    def add_passed(self, msg: str, location: str = "") -> None:
        loc = f" [{location}]" if location else ""
        self.passed.append(f"PASSED{loc}: {msg}")

    def has_critical(self) -> bool:
        return len(self.critical_issues) > 0

    def has_major(self) -> bool:
        return len(self.major_issues) > 0

    def has_minor(self) -> bool:
        return len(self.minor_issues) > 0

    def print_report(self, verbose: bool = False) -> None:
        print("\n" + "=" * 60)
        print("MARKETPLACE VALIDATION REPORT")
        print("=" * 60)

        if self.critical_issues:
            print("\n--- CRITICAL ISSUES (must fix) ---")
            for issue in self.critical_issues:
                print(f"  {issue}")

        if self.major_issues:
            print("\n--- MAJOR ISSUES (should fix) ---")
            for issue in self.major_issues:
                print(f"  {issue}")

        if self.minor_issues:
            print("\n--- MINOR ISSUES (consider fixing) ---")
            for issue in self.minor_issues:
                print(f"  {issue}")

        if self.warnings:
            print("\n--- WARNINGS ---")
            for w in self.warnings:
                print(f"  {w}")

        if self.info:
            print("\n--- INFO ---")
            for i in self.info:
                print(f"  {i}")

        if verbose and self.passed:
            print("\n--- PASSED CHECKS ---")
            for p in self.passed:
                print(f"  {p}")

        # Summary
        print("\n" + "-" * 60)
        print(
            f"Summary: {len(self.critical_issues)} critical, "
            f"{len(self.major_issues)} major, {len(self.minor_issues)} minor, "
            f"{len(self.warnings)} warnings"
        )

        if self.critical_issues:
            print("\nRESULT: FAILED (critical issues)")
        elif self.major_issues:
            print("\nRESULT: FAILED (major issues)")
        elif self.minor_issues:
            print("\nRESULT: PASSED with minor issues")
        else:
            print("\nRESULT: PASSED")
        print("=" * 60)


def is_valid_kebab_case(name: str) -> bool:
    """Check if name follows kebab-case (lowercase, hyphens, no spaces)."""
    return bool(re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name))


def is_reserved_name(name: str) -> bool:
    """Check if name is reserved or impersonates official marketplaces."""
    if name.lower() in RESERVED_MARKETPLACE_NAMES:
        return True
    for pattern in IMPERSONATION_PATTERNS:
        if re.search(pattern, name.lower()):
            return True
    return False


def validate_source(
    source: Any, plugin_name: str, marketplace_path: Path, report: ValidationReport
) -> None:
    """Validate a plugin source field."""
    loc = f"plugins[{plugin_name}].source"

    if isinstance(source, str):
        # Relative path source
        if ".." in source:
            report.critical(
                f"Path traversal not allowed in source: {source}", loc
            )
        elif not source.startswith("./"):
            report.warning(
                f"Relative path should start with './': {source}", loc
            )
        else:
            # Check if path exists in marketplace
            source_path = marketplace_path / source
            if not source_path.exists():
                report.major(
                    f"Source path does not exist: {source}", loc
                )
            else:
                report.add_passed(f"Source path exists: {source}", loc)

    elif isinstance(source, dict):
        source_type = source.get("source")
        if source_type == "github":
            if "repo" not in source:
                report.critical("GitHub source missing 'repo' field", loc)
            else:
                repo = source["repo"]
                if not re.match(r"^[^/]+/[^/]+$", repo):
                    report.major(
                        f"Invalid repo format (expected 'owner/repo'): {repo}", loc
                    )
                else:
                    report.add_passed(f"GitHub source format valid: {repo}", loc)

            # Validate optional fields
            if "sha" in source:
                sha = source["sha"]
                if not re.match(r"^[a-f0-9]{40}$", sha):
                    report.major(
                        f"SHA must be full 40-character hex: {sha}", loc
                    )

        elif source_type == "url":
            if "url" not in source:
                report.critical("URL source missing 'url' field", loc)
            else:
                url = source["url"]
                if not url.endswith(".git"):
                    report.warning(
                        f"Git URL should end with '.git': {url}", loc
                    )

            # Validate optional fields
            if "sha" in source:
                sha = source["sha"]
                if not re.match(r"^[a-f0-9]{40}$", sha):
                    report.major(
                        f"SHA must be full 40-character hex: {sha}", loc
                    )

        elif source_type is None:
            report.critical(
                "Object source missing 'source' field (expected 'github' or 'url')", loc
            )
        else:
            report.major(
                f"Unknown source type: {source_type} (expected 'github' or 'url')", loc
            )
    else:
        report.critical(
            f"Invalid source type: {type(source).__name__} (expected string or object)",
            loc,
        )


def validate_plugin_entry(
    plugin: dict[str, Any],
    index: int,
    marketplace_path: Path,
    seen_names: set[str],
    report: ValidationReport,
) -> None:
    """Validate a single plugin entry."""
    loc = f"plugins[{index}]"

    # Required: name
    if "name" not in plugin:
        report.critical("Plugin entry missing required 'name' field", loc)
        return

    name = plugin["name"]
    loc = f"plugins[{name}]"

    # Validate name format
    if not isinstance(name, str):
        report.critical(f"Plugin name must be string, got {type(name).__name__}", loc)
        return

    if not is_valid_kebab_case(name):
        report.major(
            f"Plugin name should be kebab-case (lowercase, hyphens): {name}", loc
        )

    # Check for duplicates
    if name in seen_names:
        report.critical(f"Duplicate plugin name: {name}", loc)
    seen_names.add(name)

    # Required: source
    if "source" not in plugin:
        report.critical("Plugin entry missing required 'source' field", loc)
    else:
        validate_source(plugin["source"], name, marketplace_path, report)

    # Optional fields validation
    if "version" in plugin:
        version = plugin["version"]
        if not isinstance(version, str):
            report.minor(f"Version should be string, got {type(version).__name__}", loc)

    if "author" in plugin:
        author = plugin["author"]
        if isinstance(author, dict):
            if "name" not in author:
                report.minor("author object should have 'name' field", loc)
        elif not isinstance(author, str):
            report.minor(
                f"author should be object or string, got {type(author).__name__}", loc
            )

    if "strict" in plugin:
        strict = plugin["strict"]
        if not isinstance(strict, bool):
            report.major(
                f"'strict' must be boolean, got {type(strict).__name__}", loc
            )

    # Check for plugin.json based on strict mode
    strict = plugin.get("strict", True)
    source = plugin.get("source")
    if isinstance(source, str) and source.startswith("./"):
        plugin_json_path = (
            marketplace_path / source / ".claude-plugin" / "plugin.json"
        )
        plugin_json_exists = plugin_json_path.exists()

        if strict:
            # strict=true (default): plugin.json is REQUIRED
            if not plugin_json_exists:
                report.major(
                    f"strict=true (default) but plugin.json not found at: "
                    f"{source}/.claude-plugin/plugin.json",
                    loc,
                )
            else:
                report.add_passed(
                    "Plugin has plugin.json (strict=true is satisfied)", loc
                )
        else:
            # strict=false: plugin.json should NOT exist
            # Having both causes CLI issues (e.g., uninstall fails)
            if plugin_json_exists:
                report.major(
                    f"strict=false but plugin.json EXISTS at: "
                    f"{source}/.claude-plugin/plugin.json - "
                    "This causes CLI issues (uninstall fails). "
                    "Remove plugin.json when using strict=false.",
                    loc,
                )
            else:
                report.add_passed(
                    "No plugin.json (correct for strict=false)", loc
                )

    # Validate component paths
    path_fields = ["commands", "agents", "hooks", "mcpServers", "lspServers"]
    for fld in path_fields:
        if fld in plugin:
            value = plugin[fld]
            if isinstance(value, str) and not value.startswith("./"):
                report.warning(
                    f"'{fld}' path should start with './': {value}", loc
                )
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, str) and not item.startswith("./"):
                        report.warning(
                            f"'{fld}[{i}]' path should start with './': {item}", loc
                        )


def validate_marketplace(
    marketplace_path: Path, report: ValidationReport
) -> None:
    """Validate marketplace.json and structure."""
    manifest_path = marketplace_path / ".claude-plugin" / "marketplace.json"

    # Check marketplace.json exists
    if not manifest_path.exists():
        report.critical(
            f"marketplace.json not found at: {manifest_path}",
            ".claude-plugin/marketplace.json",
        )
        return

    report.add_passed(
        "marketplace.json exists", ".claude-plugin/marketplace.json"
    )

    # Parse JSON
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except json.JSONDecodeError as e:
        report.critical(
            f"Invalid JSON syntax: {e}", ".claude-plugin/marketplace.json"
        )
        return

    report.add_passed("JSON syntax valid", ".claude-plugin/marketplace.json")

    # Validate required fields
    # 1. name (required)
    if "name" not in manifest:
        report.critical(
            "Missing required field 'name'", ".claude-plugin/marketplace.json"
        )
    else:
        name = manifest["name"]
        if not isinstance(name, str):
            report.critical(
                f"'name' must be string, got {type(name).__name__}",
                ".claude-plugin/marketplace.json",
            )
        elif is_reserved_name(name):
            report.critical(
                f"Marketplace name is reserved or impersonates official: {name}",
                ".claude-plugin/marketplace.json",
            )
        elif not is_valid_kebab_case(name):
            report.major(
                f"Marketplace name should be kebab-case: {name}",
                ".claude-plugin/marketplace.json",
            )
        else:
            report.add_passed(
                f"Marketplace name valid: {name}",
                ".claude-plugin/marketplace.json",
            )

    # 2. owner (required)
    if "owner" not in manifest:
        report.critical(
            "Missing required field 'owner'", ".claude-plugin/marketplace.json"
        )
    else:
        owner = manifest["owner"]
        if not isinstance(owner, dict):
            report.critical(
                f"'owner' must be object, got {type(owner).__name__}",
                ".claude-plugin/marketplace.json",
            )
        elif "name" not in owner:
            report.critical(
                "owner object missing required 'name' field",
                ".claude-plugin/marketplace.json",
            )
        else:
            report.add_passed("owner.name present", ".claude-plugin/marketplace.json")

    # 3. plugins (required)
    if "plugins" not in manifest:
        report.critical(
            "Missing required field 'plugins'", ".claude-plugin/marketplace.json"
        )
    else:
        plugins = manifest["plugins"]
        if not isinstance(plugins, list):
            report.critical(
                f"'plugins' must be array, got {type(plugins).__name__}",
                ".claude-plugin/marketplace.json",
            )
        elif len(plugins) == 0:
            report.warning(
                "Marketplace has no plugins defined",
                ".claude-plugin/marketplace.json",
            )
        else:
            report.add_passed(
                f"plugins array has {len(plugins)} entries",
                ".claude-plugin/marketplace.json",
            )

            # Validate each plugin
            seen_names: set[str] = set()
            for i, plugin in enumerate(plugins):
                if not isinstance(plugin, dict):
                    report.critical(
                        f"plugins[{i}] must be object, got {type(plugin).__name__}",
                        f"plugins[{i}]",
                    )
                else:
                    validate_plugin_entry(
                        plugin, i, marketplace_path, seen_names, report
                    )

    # Optional metadata
    if "metadata" in manifest:
        metadata = manifest["metadata"]
        if isinstance(metadata, dict):
            if "description" not in metadata:
                report.minor(
                    "No marketplace description provided (metadata.description)",
                    ".claude-plugin/marketplace.json",
                )
            if "pluginRoot" in metadata:
                root = metadata["pluginRoot"]
                if not isinstance(root, str):
                    report.minor(
                        f"metadata.pluginRoot must be string, got {type(root).__name__}",
                        ".claude-plugin/marketplace.json",
                    )
                elif ".." in root:
                    report.major(
                        f"metadata.pluginRoot contains path traversal: {root}",
                        ".claude-plugin/marketplace.json",
                    )
    else:
        report.add_info(
            "No metadata section (optional)",
            ".claude-plugin/marketplace.json",
        )

    # Check for unknown top-level fields
    known_fields = {"name", "owner", "plugins", "metadata"}
    for key in manifest.keys():
        if key not in known_fields:
            report.add_info(
                f"Unknown top-level field '{key}' (may be ignored by CLI)",
                ".claude-plugin/marketplace.json",
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Claude Code plugin marketplace"
    )
    parser.add_argument(
        "marketplace_path",
        nargs="?",
        default=os.path.expanduser(
            "~/.claude/plugins/marketplaces/emasoft-plugins"
        ),
        help="Path to marketplace directory (default: emasoft-plugins)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show all passed checks",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()
    marketplace_path = Path(args.marketplace_path).resolve()

    if not marketplace_path.exists():
        print(f"Error: Marketplace path does not exist: {marketplace_path}")
        return 1

    report = ValidationReport()
    print(f"Validating marketplace at: {marketplace_path}")

    validate_marketplace(marketplace_path, report)

    if args.json:
        output = {
            "critical": report.critical_issues,
            "major": report.major_issues,
            "minor": report.minor_issues,
            "warnings": report.warnings,
            "info": report.info,
            "passed": report.passed if args.verbose else [],
        }
        print(json.dumps(output, indent=2))
    else:
        report.print_report(verbose=args.verbose)

    # Return codes
    if report.has_critical():
        return 1
    if report.has_major():
        return 2
    if report.has_minor():
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
