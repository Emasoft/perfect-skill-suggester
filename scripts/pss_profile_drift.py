#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pycozo[embedded]>=0.7.6",
# ]
# ///
"""PSS Profile Drift — read-only comparison of a .agent.toml profile vs the live CozoDB index.

Implements the issue #15 contract: reports
  - `missing`:     profile elements (name+type) the index has no exact entry for
  - `extra`:       index entries that fuzzily shadow a profile element but are
                   not in the profile (case-insensitive equality or
                   find_closest_match ratio >= 0.92)
  - `moved_scope`: elements present in the index whose current source prefix
                   differs from the generation-time scope recorded in
                   `[pss].scope_hints` (either the `[pss.scope_hints]` header
                   form or the inline table the profiler stamps since #16 —
                   both parse to the same dict)

Non-interactive, no LLM. Single JSON object on stdout; drift itself is not an
error (a wrapper decides what to do with non-empty arrays).

Usage:
  uv run scripts/pss_profile_drift.py <file.agent.toml>

Exit codes:
  0  ran to completion (verdict is in the JSON)
  2  bad input file (missing, unreadable, or invalid TOML)
  3  could-not-run (CozoDB index unavailable)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from pss_cozodb import get_all_entries  # noqa: E402
from pss_verify_profile import (  # noqa: E402
    SECTION_TYPE_MAP,  # noqa: F401  (re-exported per spec: one source of truth)
    extract_toml_elements,
    find_closest_match,
    load_toml,
)

# Source prefixes recognised by the index (`plugin:X/` carries the plugin name).
_PLAIN_SCOPES = ("user:", "project:", "local:")
NEAR_MATCH_CUTOFF = 0.92


def _current_scope_prefix(source: str) -> str:
    """Reduce an index `source` value to its scope prefix."""
    if source.startswith(_PLAIN_SCOPES):
        return source.split(":", 1)[0] + ":"
    if source.startswith("plugin:"):
        if "/" in source:
            return source.split("/", 1)[0] + "/"
        return source
    return source


def compute_drift(data: dict, index: dict[str, dict]) -> dict:
    """Compare a parsed profile against the index; return the JSON verdict dict."""
    elements = extract_toml_elements(data)

    # Index names grouped by type, for exact (verbatim) matching.
    index_names_by_type: dict[str, set[str]] = {}
    for name, idx_entry in index.items():
        etype = idx_entry.get("type", "skill")
        index_names_by_type.setdefault(etype, set()).add(name)

    missing: list[dict] = []
    moved_scope: list[dict] = []
    scope_hints: dict = data.get("pss", {}).get("scope_hints", {})
    if not isinstance(scope_hints, dict):
        scope_hints = {}

    for name, etype, section in elements:
        if name not in index_names_by_type.get(etype, set()):
            # Case-insensitive match does NOT count — the wrapper layer
            # consumes names verbatim.
            missing.append({"name": name, "type": etype, "section": section})
            continue
        entry: dict[Any, Any] | None = index.get(name)
        if entry is None:
            continue
        hint = scope_hints.get(name)
        if entry is not None and hint is not None:
            current = _current_scope_prefix(str(entry.get("source", "")))
            if hint != current:
                moved_scope.append(
                    {
                        "name": name,
                        "type": etype,
                        "generated_scope": hint,
                        "current_scope": current,
                    }
                )

    # extra: index entries of a profile-carried type that fuzzily shadow a
    # profile element but are not in it. Sorted by name, no truncation.
    profile_names_by_type: dict[str, set[str]] = {}
    for name, etype, _section in elements:
        profile_names_by_type.setdefault(etype, set()).add(name)

    extra: list[dict] = []
    for idx_name, entry in index.items():
        etype = entry.get("type", "skill")
        profile_names = profile_names_by_type.get(etype)
        if not profile_names or idx_name in profile_names:
            continue
        lowered = {p.lower(): p for p in profile_names}
        if idx_name.lower() in lowered:
            extra.append(
                {"name": idx_name, "type": etype, "reason": "case-insensitive"}
            )
            continue
        near = find_closest_match(idx_name, profile_names, cutoff=NEAR_MATCH_CUTOFF)
        if near is not None:
            extra.append(
                {"name": idx_name, "type": etype, "reason": f"near-match:{near}"}
            )
    extra.sort(key=lambda item: item["name"])

    return {
        "missing": missing,
        "extra": extra,
        "moved_scope": moved_scope,
        "counts": {
            "missing": len(missing),
            "extra": len(extra),
            "moved_scope": len(moved_scope),
        },
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="pss-profile-drift",
        description=(
            "Detect drift between a .agent.toml profile and the live CozoDB "
            "index (issue #15 contract): missing, extra, and moved_scope "
            "elements, as a single JSON verdict on stdout."
        ),
        epilog=(
            "Exit codes: 0 ran (verdict in JSON; drift itself is not an "
            "error) | 2 bad input file | 3 could-not-run (index unavailable)."
        ),
    )
    parser.add_argument("profile", help="Path to a .agent.toml profile")
    args = parser.parse_args(argv)

    path = Path(args.profile)
    try:
        data = load_toml(path)
    except OSError:
        print(f"ERROR: cannot read profile file: {path}", file=sys.stderr)
        sys.exit(2)
    except Exception as exc:  # tomllib.TOMLDecodeError and friends
        print(f"ERROR: invalid TOML in {path}: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        index = get_all_entries()
    except (ImportError, FileNotFoundError) as exc:
        print(f"ERROR: could-not-run: index unavailable: {exc}", file=sys.stderr)
        sys.exit(3)

    print(json.dumps(compute_drift(data, index), indent=2))


if __name__ == "__main__":
    main()
