#!/usr/bin/env python3
"""
PSS Domain Aggregator - Post-reindex domain name normalization and registry generation.

After all skills have been indexed (Pass 1 + Pass 2), this script:
1. Reads skill-index.json
2. Collects all domain_gates from all skills
3. Normalizes similar gate names to canonical forms
   (e.g., input_language, language_input, input_lang, lang_input → input_language)
4. Aggregates all keywords found across skills for each canonical domain
5. Writes domain-registry.json for the suggester to use at runtime

The domain registry enables two-phase matching in the suggester:
  Phase 1: Detect which domains are relevant to the user prompt (using example_keywords)
  Phase 2: Check each skill's domain gates against detected domains (boolean pass/fail)

Usage:
    python pss_aggregate_domains.py
    python pss_aggregate_domains.py --index /path/to/skill-index.json
    python pss_aggregate_domains.py --output /path/to/domain-registry.json
    python pss_aggregate_domains.py --verbose
    python pss_aggregate_domains.py --dry-run
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# -- Constants --

DEFAULT_INDEX_PATH = Path.home() / ".claude" / "cache" / "skill-index.json"
DEFAULT_REGISTRY_PATH = Path.home() / ".claude" / "cache" / "domain-registry.json"

# Abbreviation expansions for gate name normalization.
# Maps abbreviated tokens to their canonical expanded form.
ABBREVIATION_EXPANSIONS: dict[str, str] = {
    "lang": "language",
    "langs": "language",
    "plat": "platform",
    "platf": "platform",
    "fw": "framework",
    "fwork": "framework",
    "fmwk": "framework",
    "fmt": "format",
    "prog": "programming",
    "env": "environment",
    "os": "operating_system",
    "db": "database",
    "lib": "library",
    "libs": "library",
    "pkg": "package",
    "svc": "service",
    "srv": "service",
    "src": "source",
    "dst": "destination",
    "dest": "destination",
    "out": "output",
    "in": "input",
    "tgt": "target",
    "prov": "provider",
}

# Canonical token orderings for common multi-token domain names.
# When tokens match one of these sets (after expansion), use this ordering.
# This ensures that e.g. "language_target" and "target_language"
# both become "target_language".
CANONICAL_ORDERINGS: dict[frozenset[str], str] = {
    frozenset({"target", "language"}): "target_language",
    frozenset({"target", "platform"}): "target_platform",
    frozenset({"target", "framework"}): "target_framework",
    frozenset({"input", "language"}): "input_language",
    frozenset({"output", "language"}): "output_language",
    frozenset({"source", "language"}): "source_language",
    frozenset({"input", "format"}): "input_format",
    frozenset({"output", "format"}): "output_format",
    frozenset({"programming", "language"}): "programming_language",
    frozenset({"text", "language"}): "text_language",
    frozenset({"cloud", "provider"}): "cloud_provider",
    frozenset({"operating", "system"}): "operating_system",
    frozenset({"mobile", "platform"}): "mobile_platform",
    frozenset({"rendering", "engine"}): "rendering_engine",
}


def normalize_gate_name(raw_name: str) -> str:
    """Normalize a gate name to its canonical form.

    Steps:
    1. Lowercase and strip whitespace
    2. Split on underscores to get tokens
    3. Expand abbreviations (e.g., 'lang' → 'language')
    4. Check if the token set matches a known canonical ordering
    5. If not, sort tokens alphabetically and join with underscore

    Examples:
        'target_language' → 'target_language'
        'language_target' → 'target_language'
        'input_lang'      → 'input_language'
        'lang_input'      → 'input_language'
        'tgt_lang'        → 'target_language'
        'cloud_provider'  → 'cloud_provider'
        'my_custom_gate'  → 'custom_gate_my' (alphabetical fallback)
    """
    # Step 1: clean up
    clean = raw_name.strip().lower()

    # Step 2: split on underscores
    tokens = [t for t in clean.split("_") if t]

    # Step 3: expand abbreviations
    expanded_tokens = []
    for token in tokens:
        expanded = ABBREVIATION_EXPANSIONS.get(token, token)
        # Some expansions contain underscores (e.g., 'operating_system')
        # so we split again after expansion
        expanded_tokens.extend(expanded.split("_"))

    # Step 4: check for known canonical orderings
    token_set = frozenset(expanded_tokens)
    if token_set in CANONICAL_ORDERINGS:
        return CANONICAL_ORDERINGS[token_set]

    # Step 5: alphabetical fallback
    return "_".join(sorted(expanded_tokens))


def collect_domain_gates(
    index: dict[str, Any],
) -> dict[str, list[tuple[str, str, list[str]]]]:
    """Collect all domain_gates from all skills in the index.

    Returns a dict mapping canonical domain name to a list of tuples:
        (skill_name, original_gate_name, gate_keywords)
    """
    # canonical_name → [(skill_name, original_gate_name, keywords), ...]
    domains: dict[str, list[tuple[str, str, list[str]]]] = defaultdict(list)

    skills = index.get("skills", {})
    for skill_name, entry in skills.items():
        gates = entry.get("domain_gates")
        if not gates or not isinstance(gates, dict):
            continue

        for gate_name, gate_keywords in gates.items():
            if not isinstance(gate_keywords, list):
                continue

            canonical = normalize_gate_name(gate_name)
            domains[canonical].append((skill_name, gate_name, gate_keywords))

    return dict(domains)


def build_registry(
    index: dict[str, Any],
    index_path: Path,
    verbose: bool = False,
) -> dict[str, Any]:
    """Build the domain registry from the skill index.

    Returns the complete domain-registry.json structure.
    """
    collected = collect_domain_gates(index)

    if verbose:
        print(f"Found {len(collected)} canonical domains across skills")

    registry_domains: dict[str, Any] = {}

    for canonical_name in sorted(collected.keys()):
        entries = collected[canonical_name]

        # Collect all unique original gate names (aliases)
        aliases = sorted(set(original for _, original, _ in entries))

        # Collect all unique keywords across all skills for this domain
        all_keywords: set[str] = set()
        skills_list: list[str] = []
        has_generic = False

        for skill_name, _, keywords in entries:
            skills_list.append(skill_name)
            for kw in keywords:
                if isinstance(kw, str):
                    lower_kw = kw.lower()
                    all_keywords.add(lower_kw)
                    if lower_kw == "generic":
                        has_generic = True

        # Sort keywords for deterministic output, with 'generic' first if present
        sorted_keywords = sorted(all_keywords - {"generic"})
        if has_generic:
            sorted_keywords.insert(0, "generic")

        registry_domains[canonical_name] = {
            "canonical_name": canonical_name,
            "aliases": aliases,
            "example_keywords": sorted_keywords,
            "has_generic": has_generic,
            "skill_count": len(set(skills_list)),
            "skills": sorted(set(skills_list)),
        }

        if verbose:
            print(
                f"  {canonical_name}: "
                f"{len(sorted_keywords)} keywords, "
                f"{len(set(skills_list))} skills, "
                f"aliases={aliases}" + (" [has generic]" if has_generic else "")
            )

    registry: dict[str, Any] = {
        "version": "1.0",
        "generated": datetime.now(timezone.utc).isoformat(),
        "source_index": str(index_path),
        "domain_count": len(registry_domains),
        "domains": registry_domains,
    }

    return registry


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate domain gates from skill-index.json"
            " into domain-registry.json"
        )
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=DEFAULT_INDEX_PATH,
        help=f"Path to skill-index.json (default: {DEFAULT_INDEX_PATH})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REGISTRY_PATH,
        help=f"Path to write domain-registry.json (default: {DEFAULT_REGISTRY_PATH})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed progress information",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print registry to stdout instead of writing to file",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON (for scripting)",
    )

    args = parser.parse_args()

    # Read the skill index
    if not args.index.exists():
        print(f"ERROR: Skill index not found at {args.index}", file=sys.stderr)
        return 1

    try:
        index = json.loads(args.index.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: Failed to read skill index: {exc}", file=sys.stderr)
        return 1

    # Build the registry
    registry = build_registry(index, args.index, verbose=args.verbose)

    if args.dry_run:
        print(json.dumps(registry, indent=2))
        return 0

    # Write the registry
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(registry, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"ERROR: Failed to write domain registry: {exc}", file=sys.stderr)
        return 1

    if args.json:
        result = {
            "status": "ok",
            "registry_path": str(args.output),
            "domain_count": registry["domain_count"],
        }
        print(json.dumps(result))
    elif args.verbose:
        print(f"\nDomain registry written to {args.output}")
        print(f"  {registry['domain_count']} canonical domains")
    else:
        print(
            f"[OK] Domain registry: {registry['domain_count']} domains → {args.output}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
