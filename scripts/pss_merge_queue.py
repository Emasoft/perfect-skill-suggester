#!/usr/bin/env python3
"""
PSS Merge Queue - Atomic merge of .pss files into skill-index.json.

Merges data from a temporary .pss JSON file into the master
skill-index.json with file locking to prevent concurrent corruption.

Usage:
    python pss_merge_queue.py <pss_file>
    python pss_merge_queue.py <pss_file> --pass 1
    python pss_merge_queue.py <pss_file> --pass 2
    python pss_merge_queue.py <pss_file> --index /path/to/skill-index.json
    python pss_merge_queue.py --batch-stdin < batch.jsonl
"""

import argparse

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore[assignment]  # Windows has no fcntl
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pss_paths import get_index_path, get_lock_path

# Default paths for index and lock files
DEFAULT_INDEX_PATH = get_index_path()
DEFAULT_LOCK_PATH = get_lock_path()

# Fields merged during pass 1 (factual skill data)
PASS1_FIELDS: list[str] = [
    "source",
    "path",
    "type",
    "keywords",
    "intents",
    "patterns",
    "directories",
    "path_patterns",
    "description",
    "use_cases",
    "category",
    "secondary_categories",
    "platforms",
    "frameworks",
    "languages",
    "domains",
    "tools",
    "services",
    "file_types",
    "domain_gates",
    "tier",
    "boost",
    "server_type",
    "server_command",
    "server_args",
    "language_ids",
]

# Fields merged during pass 2 (AI co-usage relationships)
PASS2_CO_USAGE_FIELDS: list[str] = [
    "usually_with",
    "precedes",
    "follows",
    "alternatives",
    "rationale",
]


def create_skeleton_index() -> dict[str, Any]:
    """Create a new empty skill-index.json skeleton structure.

    Returns a dict with version 3.0, empty skills, and current timestamp.
    """
    return {
        "version": "3.0",
        "generated": datetime.now(timezone.utc).isoformat(),
        "generator": "ai-analyzed",
        "pass": 1,
        "skill_count": 0,
        "skills": {},
    }


def read_json_file(path: Path) -> dict[str, Any]:
    """Read and parse a JSON file, returning its contents as a dict.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed JSON as a dictionary.

    Raises:
        SystemExit: If the file cannot be read or parsed.
    """
    try:
        text = path.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(text)
        return data
    except FileNotFoundError:
        print(f"[ERROR] File not found: {path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(
            f"[ERROR] Invalid JSON in {path}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)


def detect_pass(pss_data: dict[str, Any]) -> int:
    """Auto-detect which pass a .pss file contains.

    If the file has a non-empty co_usage object, it is pass 2.
    Otherwise it is pass 1.

    Args:
        pss_data: Parsed .pss file contents.

    Returns:
        1 for pass 1 data, 2 for pass 2 data.
    """
    co_usage = pss_data.get("co_usage")
    if isinstance(co_usage, dict) and len(co_usage) > 0:
        return 2
    return 1


def merge_pass1(
    index: dict[str, Any],
    pss_data: dict[str, Any],
) -> str:
    """Merge pass 1 (factual) data from .pss into the index.

    Finds or creates the skill entry by name, then copies all
    pass 1 fields from the .pss data into the index entry.

    Args:
        index: The current skill-index.json data (mutated in place).
        pss_data: The parsed .pss file contents.

    Returns:
        The skill name that was merged.

    Raises:
        SystemExit: If the .pss file has no 'name' field.
    """
    skill_name = pss_data.get("name")
    if not skill_name:
        print(
            "[ERROR] .pss file missing required 'name' field",
            file=sys.stderr,
        )
        sys.exit(1)

    # Use composite key "source::name" to prevent collisions when different
    # sources (plugins, user, marketplace) provide same-named elements.
    source = pss_data.get("source", "unknown")
    composite_key = f"{source}::{skill_name}"

    skills = index.setdefault("skills", {})
    entry = skills.setdefault(composite_key, {})

    # Copy each pass 1 field if present in the .pss data
    for field_name in PASS1_FIELDS:
        if field_name in pss_data:
            entry[field_name] = pss_data[field_name]

    # Preserve the skill name inside the entry for consistency
    entry["name"] = skill_name

    return skill_name


def merge_pass2(
    index: dict[str, Any],
    pss_data: dict[str, Any],
) -> str:
    """Merge pass 2 (co-usage relationship) data from .pss into the index.

    Finds the skill entry by name and merges the co_usage object.
    Also sets 'tier' if present in the .pss data, and updates the
    index-level pass marker to 2.

    Args:
        index: The current skill-index.json data (mutated in place).
        pss_data: The parsed .pss file contents.

    Returns:
        The skill name that was merged.

    Raises:
        SystemExit: If the .pss file has no 'name' field or the
            skill entry does not exist in the index.
    """
    skill_name = pss_data.get("name")
    if not skill_name:
        print(
            "[ERROR] .pss file missing required 'name' field",
            file=sys.stderr,
        )
        sys.exit(1)

    # Look up by composite key "source::name" (new format) or fall back to name (legacy)
    source = pss_data.get("source", "unknown")
    composite_key = f"{source}::{skill_name}"

    skills = index.get("skills", {})
    if composite_key in skills:
        entry = skills[composite_key]
    elif skill_name in skills:
        # Legacy fallback: old index format uses name as key
        entry = skills[skill_name]
    else:
        print(
            f"[ERROR] Skill '{skill_name}' not found in index. Run pass 1 first.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Merge co_usage sub-fields
    pss_co_usage = pss_data.get("co_usage", {})
    if isinstance(pss_co_usage, dict):
        entry_co_usage = entry.setdefault("co_usage", {})
        for co_field in PASS2_CO_USAGE_FIELDS:
            if co_field in pss_co_usage:
                entry_co_usage[co_field] = pss_co_usage[co_field]

    # Set tier if present in .pss data
    if "tier" in pss_data:
        entry["tier"] = pss_data["tier"]

    # Mark index-level pass as 2
    index["pass"] = 2

    return skill_name


def atomic_write_json(
    path: Path,
    data: dict[str, Any],
) -> None:
    """Write JSON data atomically using temp file + rename.

    Writes to a temporary file in the same directory as the target,
    then uses os.rename() for an atomic replacement. This ensures
    no partial writes are visible to other processes.

    Args:
        path: Destination file path.
        data: Dictionary to serialize as JSON.
    """
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in the same directory (same filesystem)
    fd, tmp_path_str = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=".pss_merge_tmp_",
        suffix=".json",
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            json.dump(data, tmp_file, indent=2, ensure_ascii=False)
            tmp_file.write("\n")
        # Atomic replace (os.replace works cross-platform, os.rename fails on Windows)
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file on failure
        tmp_path.unlink(missing_ok=True)
        raise


def run_merge(
    pss_file: Path,
    pass_num: int | None,
    index_path: Path,
    quiet: bool = False,
) -> None:
    """Execute the full merge operation with file locking.

    Acquires an exclusive lock, reads the index (or creates a
    skeleton if it does not exist), merges the .pss data, writes
    the index atomically, deletes the .pss file, and releases
    the lock.

    Args:
        pss_file: Path to the .pss JSON file to merge.
        pass_num: Which pass to merge (1 or 2), or None for
            auto-detection.
        index_path: Path to the skill-index.json file.
        quiet: If True, suppress per-element output.
    """
    # Read the .pss file before acquiring lock (fail fast)
    pss_data = read_json_file(pss_file)

    # Auto-detect pass if not specified
    if pass_num is None:
        pass_num = detect_pass(pss_data)

    # Ensure lock file parent directory exists
    lock_path = DEFAULT_LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    # Acquire exclusive file lock
    lock_fd = open(lock_path, "w")  # noqa: SIM115
    try:
        if fcntl is not None:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)

        # Read or create the index
        if index_path.exists():
            index = read_json_file(index_path)
        else:
            index = create_skeleton_index()

        # Merge based on pass number
        match pass_num:
            case 1:
                skill_name = merge_pass1(index, pss_data)
            case 2:
                skill_name = merge_pass2(index, pss_data)
            case _:
                print(
                    f"[ERROR] Invalid pass number: {pass_num}. Must be 1 or 2.",
                    file=sys.stderr,
                )
                sys.exit(1)

        # Update index metadata
        index["skill_count"] = len(index.get("skills", {}))
        index["generated"] = datetime.now(timezone.utc).isoformat()

        # Atomic write
        atomic_write_json(index_path, index)

        # Cleanup: delete the merged .pss file
        pss_file.unlink(missing_ok=True)

        if not quiet:
            print(f"[MERGED] {skill_name} (pass {pass_num}) into {index_path.name}")

    finally:
        # Release lock and close file descriptor
        if fcntl is not None:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_fd.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Parsed namespace with pss_file, pass_num, and index attributes.
    """
    parser = argparse.ArgumentParser(
        description=("Atomic merge of .pss JSON files into skill-index.json"),
    )
    parser.add_argument(
        "pss_file",
        nargs="?",
        type=Path,
        default=None,
        help="Path to the .pss JSON file to merge",
    )
    parser.add_argument(
        "--pass",
        dest="pass_num",
        type=int,
        choices=[1, 2],
        default=None,
        help="Which pass data to merge (default: auto-detect)",
    )
    parser.add_argument(
        "--index",
        type=Path,
        default=DEFAULT_INDEX_PATH,
        help=(f"Path to skill-index.json (default: {DEFAULT_INDEX_PATH})"),
    )
    parser.add_argument(
        "--batch-stdin",
        action="store_true",
        default=False,
        help="Read JSONL from stdin, merge each line as pass-1 data",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=False,
        help="Suppress per-element output, print only final summary",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Entry point: parse args and run the merge operation."""
    args = parse_args()

    # --batch-stdin mode: read JSONL from stdin and merge each line as pass-1
    if args.batch_stdin:
        batch_index_path = Path(args.index)
        # Acquire exclusive file lock (same as single-file mode) to prevent races
        lock_path = DEFAULT_LOCK_PATH
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = open(lock_path, "w")  # noqa: SIM115
        try:
            if fcntl is not None:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
            if batch_index_path.exists():
                index = read_json_file(batch_index_path)
            else:
                index = create_skeleton_index()
            count = 0
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    pss_data = json.loads(line)
                    merge_pass1(index, pss_data)
                    count += 1
                except json.JSONDecodeError as e:
                    print(f"Warning: Skipping invalid JSON line: {e}", file=sys.stderr)
            index["skill_count"] = len(index.get("skills", {}))
            atomic_write_json(batch_index_path, index)
            print(f"Merged {count} elements into {batch_index_path}", file=sys.stderr)
        finally:
            if fcntl is not None:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            lock_fd.close()
        sys.exit(0)

    # Normal single-file mode requires pss_file argument
    if args.pss_file is None:
        print(
            "[ERROR] pss_file argument is required (unless using --batch-stdin)",
            file=sys.stderr,
        )
        sys.exit(1)

    pss_file: Path = args.pss_file.resolve()
    index_path: Path = args.index.resolve()

    if not pss_file.exists():
        print(
            f"[ERROR] .pss file not found: {pss_file}",
            file=sys.stderr,
        )
        sys.exit(1)

    run_merge(pss_file, args.pass_num, index_path, quiet=args.quiet)


if __name__ == "__main__":
    main()
