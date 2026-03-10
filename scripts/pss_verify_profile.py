#!/usr/bin/env python3
"""PSS Profile Verification — validates all element names in .agent.toml against the skill index.

Checks:
  1. Every element name (skills, agents, commands, rules, MCP, LSP) exists in the index
  2. Elements sourced from the agent definition are marked as "agent-defined" (not hallucinations)
  3. Auto-skills from frontmatter are in the primary tier
  4. Force-included elements are present, force-excluded elements are absent
  5. Non-coding agents don't have LSP/linting/code-fixing elements
  6. Fuzzy matching suggests corrections for misspelled names

Usage:
  uv run scripts/pss_verify_profile.py <file.agent.toml> [--agent-def <agent.md>]
  uv run scripts/pss_verify_profile.py <file.agent.toml> --auto-fix
  uv run scripts/pss_verify_profile.py <file.agent.toml> --include skill-a --exclude skill-b
  uv run scripts/pss_verify_profile.py <file.agent.toml> --json
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

# Type → TOML sections mapping
SECTION_TYPE_MAP: dict[str, str] = {
    "skills.primary": "skill",
    "skills.secondary": "skill",
    "skills.specialized": "skill",
    "agents.recommended": "agent",
    "commands.recommended": "command",
    "rules.recommended": "rule",
    "mcp.recommended": "mcp",
    "lsp.recommended": "lsp",
}

# Skills that indicate code-writing capability (non-coding agents should NOT have these)
CODING_SKILL_PATTERNS: list[str] = [
    r".*-lsp$",
    r".*-code-fixer$",
    r".*-test-writer$",
    r"^eslint.*",
    r"^ruff.*",
    r"^prettier.*",
    r"^pyright.*",
    r"^typescript-lsp$",
    r"^gopls.*",
    r"^rust-analyzer.*",
    r"^clangd.*",
    r"^python-code-fixer$",
    r"^js-code-fixer$",
    r"^mypy.*",
    r"^biome.*",
    r"^clippy.*",
    r"^rubocop.*",
    r"^shellcheck.*",
    r"^flake8.*",
    r"^black.*",
    r"^isort.*",
    r"^pylint.*",
    r"^stylelint.*",
    r"^standardjs.*",
    r"^swiftlint.*",
    r"^ktlint.*",
]


class VerificationResult:
    """Collects verification findings."""

    def __init__(self) -> None:
        self.verified: list[dict] = []
        self.not_found: list[dict] = []
        self.agent_defined: list[dict] = []
        self.auto_fix_applied: list[dict] = []
        self.restriction_violations: list[dict] = []
        self.coding_violations: list[dict] = []
        self.pinning_violations: list[dict] = []

    @property
    def has_errors(self) -> bool:
        return bool(
            self.not_found
            or self.restriction_violations
            or self.coding_violations
            or self.pinning_violations
        )

    def summary(self) -> str:
        parts = [
            f"verified={len(self.verified)}",
            f"agent-defined={len(self.agent_defined)}",
            f"not-found={len(self.not_found)}",
        ]
        if self.auto_fix_applied:
            parts.append(f"auto-fixed={len(self.auto_fix_applied)}")
        if self.restriction_violations:
            parts.append(f"restriction-violations={len(self.restriction_violations)}")
        if self.coding_violations:
            parts.append(f"coding-violations={len(self.coding_violations)}")
        if self.pinning_violations:
            parts.append(f"pinning-violations={len(self.pinning_violations)}")
        return ", ".join(parts)


def load_toml(path: Path) -> dict:
    """Load a TOML file — try tomllib (3.11+), fallback to tomli."""
    text = path.read_text(encoding="utf-8")
    try:
        import tomllib

        return tomllib.loads(text)
    except ImportError:
        pass
    try:
        import tomli

        return tomli.loads(text)
    except ImportError:
        pass
    sys.exit("ERROR: Python 3.11+ or 'tomli' package required for TOML parsing.")


def load_index(index_path: Path) -> dict[str, dict]:
    """Load skill-index.json and build a name→entry lookup keyed by (name, type)."""
    if not index_path.exists():
        sys.exit(
            f"ERROR: Skill index not found at {index_path}. Run /pss-reindex-skills."
        )
    with open(index_path) as f:
        data = json.load(f)
    return data.get("skills", {})


def build_type_index(index: dict[str, dict]) -> dict[str, set[str]]:
    """Build a type→set-of-names mapping from the index."""
    result: dict[str, set[str]] = {}
    for name, entry in index.items():
        etype = entry.get("type", "skill")
        result.setdefault(etype, set()).add(name)
    return result


def extract_agent_defined_names(agent_md_path: Path) -> set[str]:
    """Extract names declared in the agent .md file (auto_skills, sub-agents, etc.).

    These are names from the agent's OWN plugin that may not be in the local index.
    They should NOT be flagged as hallucinations.
    """
    names: set[str] = set()
    if not agent_md_path.exists():
        return names

    text = agent_md_path.read_text(encoding="utf-8")

    # Extract frontmatter list items only from name-bearing keys
    NAME_BEARING_KEYS = {
        "auto_skills",
        "triggers",
        "agents",
        "commands",
        "skills",
        "rules",
        "mcp",
        "lsp",
    }
    fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        current_key: str | None = None
        for line in fm_text.splitlines():
            stripped = line.strip()
            # Detect YAML key (e.g. "auto_skills:")
            key_match = re.match(r"^([a-z_]+)\s*:", stripped)
            if key_match:
                current_key = key_match.group(1)
                continue
            # Only capture list items under name-bearing keys
            if (
                current_key in NAME_BEARING_KEYS
                and stripped.startswith("- ")
                and not stripped.startswith("- {")
            ):
                name = stripped[2:].strip().strip('"').strip("'")
                if name and not name.startswith("#"):
                    names.add(name)

    # Extract agent names from routing tables (markdown table rows with ** bold **)
    for match in re.finditer(r"\*\*([a-z][a-z0-9_-]+)\*\*", text):
        candidate = match.group(1)
        if len(candidate) >= 3 and re.match(r"^[a-z][a-z0-9_-]+$", candidate):
            names.add(candidate)

    # Extract backtick-quoted names (e.g. `skill-name` in instructions)
    for match in re.finditer(r"`([a-z][a-z0-9_-]{2,})`", text):
        candidate = match.group(1)
        if re.match(r"^[a-z][a-z0-9_-]+$", candidate):
            names.add(candidate)

    return names


def extract_auto_skills(agent_md_path: Path) -> list[str]:
    """Extract the auto_skills list from agent .md frontmatter."""
    if not agent_md_path.exists():
        return []

    text = agent_md_path.read_text(encoding="utf-8")
    fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return []

    fm_text = fm_match.group(1)
    in_auto_skills = False
    skills: list[str] = []

    for line in fm_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("auto_skills:"):
            in_auto_skills = True
            continue
        if in_auto_skills:
            if stripped.startswith("- "):
                name = stripped[2:].strip().strip('"').strip("'")
                if name:
                    skills.append(name)
            elif stripped and not stripped.startswith("#"):
                # New YAML key — end of auto_skills list
                break

    return skills


def detect_non_coding_agent(agent_md_path: Path) -> bool:
    """Detect if the agent is a non-coding orchestrator/coordinator."""
    if not agent_md_path.exists():
        return False

    text = agent_md_path.read_text(encoding="utf-8")

    # Check frontmatter for type: orchestrator
    fm_match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        for line in fm_text.splitlines():
            if re.match(
                r"^\s*type:\s*(orchestrator|coordinator|manager|gatekeeper)", line
            ):
                return True

    # Check body text for orchestrator indicators
    lower_text = text.lower()
    indicators = [
        "does not write code",
        "do not write code",
        "route to sub-agents",
        "delegate to",
        "you do not write code",
        "writes_code=false",
        "writes_code: false",
    ]
    return any(ind in lower_text for ind in indicators)


def is_coding_element(name: str) -> bool:
    """Check if an element name matches coding-only patterns."""
    return any(re.match(pat, name) for pat in CODING_SKILL_PATTERNS)


def _normalize_name(name: str) -> str:
    """Normalize hyphens/underscores for comparison."""
    return name.lower().replace("_", "-")


def find_closest_match(
    name: str, candidates: set[str], cutoff: float = 0.6
) -> str | None:
    """Find the closest matching name using difflib with hyphen/underscore normalization."""
    # First try exact match after normalization
    norm = _normalize_name(name)
    for c in candidates:
        if _normalize_name(c) == norm:
            return c
    # Fall back to fuzzy matching
    matches = difflib.get_close_matches(name, candidates, n=1, cutoff=cutoff)
    return matches[0] if matches else None


def extract_toml_elements(data: dict) -> list[tuple[str, str, str]]:
    """Extract all element (name, expected_type, section) tuples from parsed TOML."""
    elements: list[tuple[str, str, str]] = []

    # Skills
    skills = data.get("skills", {})
    for tier in ("primary", "secondary", "specialized"):
        for name in skills.get(tier, []):
            elements.append((name, "skill", f"skills.{tier}"))

    # Other sections (including hooks)
    for section in ("agents", "commands", "rules", "mcp", "lsp", "hooks"):
        sec_data = data.get(section, {})
        rec = sec_data.get("recommended", [])
        if isinstance(rec, list):
            etype = SECTION_TYPE_MAP.get(f"{section}.recommended", section)
            for name in rec:
                elements.append((name, etype, f"{section}.recommended"))

    return elements


def verify_profile(
    toml_path: Path,
    index_path: Path,
    agent_md_path: Path | None = None,
    include_elements: list[str] | None = None,
    exclude_elements: list[str] | None = None,
    auto_fix: bool = False,
) -> tuple[VerificationResult, dict | None]:
    """Run all verification checks. Returns (result, fixed_toml_data_or_None)."""
    result = VerificationResult()

    # Load inputs
    toml_data = load_toml(toml_path)
    index = load_index(index_path)
    type_index = build_type_index(index)
    all_index_names = set(index.keys())

    # Agent-defined names (from the .md file, not the profiler)
    agent_names: set[str] = set()
    auto_skills: list[str] = []
    is_non_coding = False
    if agent_md_path:
        agent_names = extract_agent_defined_names(agent_md_path)
        auto_skills = extract_auto_skills(agent_md_path)
        is_non_coding = detect_non_coding_agent(agent_md_path)

    # Extract all elements from TOML
    elements = extract_toml_elements(toml_data)
    fixed_data = toml_data if auto_fix else None

    # Check 1: Verify each element exists in the index or is agent-defined
    for name, expected_type, section in elements:
        if name in agent_names:
            result.agent_defined.append(
                {
                    "name": name,
                    "type": expected_type,
                    "section": section,
                    "status": "agent-defined",
                }
            )
            continue

        # Check index — first exact match, then case-insensitive
        type_names = type_index.get(expected_type, set())
        if name in type_names:
            result.verified.append(
                {
                    "name": name,
                    "type": expected_type,
                    "section": section,
                    "status": "verified",
                }
            )
            continue

        # Try case-insensitive match
        lower_map = {n.lower(): n for n in type_names}
        if name.lower() in lower_map:
            correct_name = lower_map[name.lower()]
            if auto_fix and fixed_data:
                _apply_name_fix(fixed_data, section, name, correct_name)
                result.auto_fix_applied.append(
                    {
                        "name": name,
                        "corrected": correct_name,
                        "section": section,
                        "reason": "case mismatch",
                    }
                )
            else:
                result.not_found.append(
                    {
                        "name": name,
                        "type": expected_type,
                        "section": section,
                        "suggestion": correct_name,
                        "reason": f"case mismatch — did you mean '{correct_name}'?",
                    }
                )
            continue

        # Try name in ANY type (wrong section?)
        if name in all_index_names:
            actual_type = index[name].get("type", "unknown")
            result.not_found.append(
                {
                    "name": name,
                    "type": expected_type,
                    "section": section,
                    "suggestion": None,
                    "reason": f"found in index but as type '{actual_type}', not '{expected_type}'",
                }
            )
            continue

        # Fuzzy match within the correct type
        suggestion = find_closest_match(name, type_names)
        # Also try across all names if no type-specific match
        if not suggestion:
            suggestion = find_closest_match(name, all_index_names)

        if auto_fix and suggestion and fixed_data:
            _apply_name_fix(fixed_data, section, name, suggestion)
            result.auto_fix_applied.append(
                {
                    "name": name,
                    "corrected": suggestion,
                    "section": section,
                    "reason": "fuzzy match",
                }
            )
        else:
            result.not_found.append(
                {
                    "name": name,
                    "type": expected_type,
                    "section": section,
                    "suggestion": suggestion,
                    "reason": f"not found in index{f' — closest match: {suggestion!r}' if suggestion else ''}",
                }
            )

    # Check 2: Auto-skills pinning
    if auto_skills:
        primary_skills = set(toml_data.get("skills", {}).get("primary", []))
        for skill in auto_skills:
            if skill not in primary_skills:
                result.pinning_violations.append(
                    {
                        "name": skill,
                        "expected": "skills.primary",
                        "reason": f"auto_skill '{skill}' must be in primary tier",
                    }
                )

    # Check 3: Non-coding agent filter
    if is_non_coding:
        for name, expected_type, section in elements:
            if is_coding_element(name):
                result.coding_violations.append(
                    {
                        "name": name,
                        "section": section,
                        "reason": f"non-coding agent should not have coding element '{name}'",
                    }
                )

    # Check 4: Restriction enforcement
    include_elements = include_elements or []
    exclude_elements = exclude_elements or []

    all_toml_names = {name for name, _, _ in elements}

    for inc_name in include_elements:
        if inc_name not in all_toml_names:
            result.restriction_violations.append(
                {
                    "name": inc_name,
                    "directive": "include",
                    "reason": f"force-included element '{inc_name}' is MISSING from the profile",
                }
            )

    for exc_name in exclude_elements:
        if exc_name in all_toml_names:
            result.restriction_violations.append(
                {
                    "name": exc_name,
                    "directive": "exclude",
                    "reason": f"force-excluded element '{exc_name}' is PRESENT in the profile",
                }
            )

    return result, fixed_data if auto_fix else None


def _apply_name_fix(data: dict, section: str, old_name: str, new_name: str) -> None:
    """Apply a name correction in the TOML data structure."""
    parts = section.split(".")
    if len(parts) == 2:
        sec, field = parts
        container = data.get(sec, {})
        if isinstance(container, dict) and field in container:
            lst = container[field]
            if isinstance(lst, list):
                for i, name in enumerate(lst):
                    if name == old_name:
                        lst[i] = new_name
                        return


def write_toml(data: dict, path: Path) -> None:
    """Write TOML data back to a file (manual serialization for comments preservation)."""
    # We use tomli_w if available, otherwise manual
    try:
        import tomli_w

        path.write_bytes(tomli_w.dumps(data))
        return
    except ImportError:
        pass

    # Manual TOML writer for the known .agent.toml structure
    lines: list[str] = []

    def write_section(name: str, d: dict, prefix: str = "") -> None:
        full = f"{prefix}.{name}" if prefix else name
        lines.append(f"[{full}]")
        for k, v in d.items():
            if isinstance(v, dict):
                continue  # handled recursively below
            elif isinstance(v, list):
                items = ", ".join(f'"{i}"' for i in v)
                lines.append(f"{k} = [{items}]")
            elif isinstance(v, str):
                # Escape special TOML characters in string values
                escaped = (
                    v.replace("\\", "\\\\")
                    .replace('"', '\\"')
                    .replace("\n", "\\n")
                    .replace("\t", "\\t")
                )
                lines.append(f'{k} = "{escaped}"')
            elif isinstance(v, bool):
                lines.append(f"{k} = {'true' if v else 'false'}")
            elif isinstance(v, int):
                lines.append(f"{k} = {v}")
        for k, v in d.items():
            if isinstance(v, dict):
                lines.append("")
                write_section(k, v, full)
        lines.append("")

    for section, content in data.items():
        if isinstance(content, dict):
            write_section(section, content)

    path.write_text("\n".join(lines), encoding="utf-8")


def print_report(result: VerificationResult, verbose: bool = False) -> None:
    """Print human-readable verification report."""
    # Header
    total = len(result.verified) + len(result.agent_defined) + len(result.not_found)
    print(f"\nPSS Profile Verification: {total} elements checked")
    print(f"  {result.summary()}")
    print()

    # Not found (always show)
    if result.not_found:
        print("NOT FOUND IN INDEX:")
        for item in result.not_found:
            suggestion = item.get("suggestion")
            sug_text = f" → suggestion: {suggestion!r}" if suggestion else ""
            print(f"  ✗ [{item['section']}] {item['name']}{sug_text}")
            print(f"    {item['reason']}")
        print()

    # Pinning violations
    if result.pinning_violations:
        print("AUTO-SKILLS PINNING VIOLATIONS:")
        for item in result.pinning_violations:
            print(f"  ✗ {item['name']} — {item['reason']}")
        print()

    # Coding violations
    if result.coding_violations:
        print("NON-CODING AGENT VIOLATIONS:")
        for item in result.coding_violations:
            print(f"  ✗ [{item['section']}] {item['name']} — {item['reason']}")
        print()

    # Restriction violations
    if result.restriction_violations:
        print("RESTRICTION VIOLATIONS:")
        for item in result.restriction_violations:
            print(f"  ✗ {item['name']} ({item['directive']}) — {item['reason']}")
        print()

    # Auto-fixed
    if result.auto_fix_applied:
        print("AUTO-FIXED:")
        for item in result.auto_fix_applied:
            print(
                f"  ↻ [{item['section']}] {item['name']} → {item['corrected']} ({item['reason']})"
            )
        print()

    # Verbose: show all verified
    if verbose:
        if result.verified:
            print("VERIFIED:")
            for item in result.verified:
                print(f"  ✓ [{item['section']}] {item['name']}")
            print()

        if result.agent_defined:
            print("AGENT-DEFINED (from agent .md, not in local index):")
            for item in result.agent_defined:
                print(f"  ◆ [{item['section']}] {item['name']}")
            print()

    # Final verdict
    if result.has_errors:
        print("VERDICT: FAIL — issues found that need correction")
    else:
        print("VERDICT: PASS — all elements verified")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify all element names in .agent.toml against the PSS skill index"
    )
    parser.add_argument("toml_file", help="Path to the .agent.toml file")
    parser.add_argument(
        "--agent-def",
        help="Path to the agent .md definition file (for auto_skills, sub-agent extraction)",
    )
    parser.add_argument(
        "--index",
        default=None,  # Resolved below via pss_paths
        help="Path to skill-index.json (default: ~/.claude/cache/skill-index.json)",
    )
    parser.add_argument(
        "--include",
        nargs="*",
        default=[],
        help="Elements that must be present in the profile",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help="Elements that must NOT be present in the profile",
    )
    parser.add_argument(
        "--auto-fix",
        action="store_true",
        help="Automatically fix misspelled names using closest index match",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of human-readable text",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show verified and agent-defined elements too",
    )
    args = parser.parse_args()

    toml_path = Path(args.toml_file)
    if not toml_path.exists():
        sys.exit(f"ERROR: TOML file not found: {toml_path}")

    if args.index is None:
        from pss_paths import get_index_path
        index_path = get_index_path()
    else:
        index_path = Path(args.index)
    agent_md_path = Path(args.agent_def) if args.agent_def else None

    # Also try to get agent_def from the TOML's [agent].path field
    if not agent_md_path:
        try:
            data = load_toml(toml_path)
            agent_path_str = data.get("agent", {}).get("path")
            # Guard against empty string resolving to cwd
            if agent_path_str and agent_path_str.strip():
                candidate = Path(agent_path_str)
                if candidate.exists():
                    agent_md_path = candidate
        except Exception:
            pass

    result, fixed_data = verify_profile(
        toml_path=toml_path,
        index_path=index_path,
        agent_md_path=agent_md_path,
        include_elements=args.include,
        exclude_elements=args.exclude,
        auto_fix=args.auto_fix,
    )

    # Write fixed data back if auto-fix was applied
    if args.auto_fix and fixed_data and result.auto_fix_applied:
        write_toml(fixed_data, toml_path)
        print(f"Auto-fixed {len(result.auto_fix_applied)} elements in {toml_path}")

    if args.json:
        report = {
            "file": str(toml_path),
            "agent_def": str(agent_md_path) if agent_md_path else None,
            "verified": result.verified,
            "agent_defined": result.agent_defined,
            "not_found": result.not_found,
            "auto_fix_applied": result.auto_fix_applied,
            "restriction_violations": result.restriction_violations,
            "coding_violations": result.coding_violations,
            "pinning_violations": result.pinning_violations,
            "has_errors": result.has_errors,
            "summary": result.summary(),
        }
        print(json.dumps(report, indent=2))
    else:
        print_report(result, verbose=args.verbose)

    return 1 if result.has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
