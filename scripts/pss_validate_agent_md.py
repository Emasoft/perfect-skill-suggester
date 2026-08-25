#!/usr/bin/env python3
"""
PSS Agent Markdown Validator

Validates a Claude Code subagent definition (`agents/<name>.md`) — the output of
`pss make-agent`, or any hand-written agent.

The checks worth knowing about, because they encode failures that actually
happened rather than schema pedantry:

- **Unsubstituted placeholders.** A generator that emits a literal ``{}`` or
  ``{name}`` produces a file that compiles, tests green, and instructs the agent
  to use something that does not exist. Caught here as an error.
- **Preloadability of every `skills:` entry.** Claude Code SILENTLY skips a
  preloaded skill it cannot find, with only a debug-log line. A typo therefore
  costs you the skill with no error anywhere — so an unresolvable name is an
  error here, where you will see it.
- **Plugin-forbidden fields.** A plugin-shipped agent may not declare `hooks`,
  `mcpServers` or `permissionMode`; those are silently ignored at load.

Usage:
    python3 pss_validate_agent_md.py agents/foo.md
    python3 pss_validate_agent_md.py agents/foo.md --check-index
    python3 pss_validate_agent_md.py agents/foo.md --plugin
    python3 pss_validate_agent_md.py agents/foo.md --json

Exit codes:
    0 = valid
    1 = invalid (errors found)
    2 = file not found or parse error
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Frontmatter keys Claude Code recognizes on a subagent, plus PSS's own
# `auto_skills` (read by the profiler, ignored by the harness).
KNOWN_KEYS = {
    "name",
    "description",
    "tools",
    "disallowedTools",
    "model",
    "permissionMode",
    "maxTurns",
    "skills",
    "mcpServers",
    "memory",
    "background",
    "effort",
    "isolation",
    "color",
    "hooks",
    "auto_skills",
}

# Fields a plugin-shipped agent may not carry — they are dropped at load, so a
# plugin that relies on one behaves differently than the same file used locally.
PLUGIN_FORBIDDEN = {"hooks", "mcpServers", "permissionMode"}

LIST_KEYS = {"tools", "disallowedTools", "skills", "mcpServers", "auto_skills"}

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# A `{}` or `{identifier}` that a format call should have replaced. Deliberately
# narrow: `${VAR}` and `{"json": 1}` are legitimate and must not trip it.
PLACEHOLDER_RE = re.compile(r"(?<!\$)\{[a-z_][a-z0-9_]*\}|(?<!\$)\{\}")


class Frontmatter:
    def __init__(self, keys: dict[str, object], end_line: int):
        self.keys = keys
        self.end_line = end_line


def parse_frontmatter(text: str) -> Frontmatter:
    """Parse the leading `---` block into scalars and block-sequence lists.

    Hand-rolled rather than importing PyYAML: this script is a validation gate
    that must run on a bare interpreter, and a missing optional dependency
    turning into "validation skipped" is the failure mode a gate exists to
    prevent. The subset accepted here (scalars + `- ` block sequences + inline
    `[a, b]` flow lists) is exactly what agent frontmatter uses.
    """
    # CC 2.1.240 honors BOM'd agent files; str.strip() does not remove U+FEFF,
    # so an unstripped BOM fails the fence check with a misleading message.
    text = text.lstrip(chr(0xFEFF))
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("file does not begin with a '---' frontmatter fence")

    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        raise ValueError("frontmatter fence is never closed")

    keys: dict[str, object] = {}
    current_list_key: str | None = None
    for raw in lines[1:end]:
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        stripped = line.lstrip()
        if stripped.startswith("- "):
            if current_list_key is None:
                raise ValueError(f"list item with no key above it: {line!r}")
            item = stripped[2:].strip().strip("\"'")
            bucket = keys.setdefault(current_list_key, [])
            if not isinstance(bucket, list):
                raise ValueError(
                    f"key {current_list_key!r} has both a scalar value and list items"
                )
            bucket.append(item)
            continue

        if ":" not in line:
            raise ValueError(f"frontmatter line is not 'key: value': {line!r}")
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if not value:
            # A key with nothing after the colon opens a block sequence.
            current_list_key = key
            keys.setdefault(key, [])
            continue

        current_list_key = None
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            keys[key] = (
                [v.strip().strip("\"'") for v in inner.split(",") if v.strip()]
                if inner
                else []
            )
        else:
            keys[key] = value.strip("\"'")

    return Frontmatter(keys, end)


def index_has_skill(name: str) -> bool | None:
    """True/False if the index could be consulted, None if it could not.

    Returning None rather than False on a missing binary matters: "I could not
    check" and "it does not exist" lead to opposite actions, and collapsing them
    would make a broken toolchain look like a broken agent.
    """
    binary = None
    root = Path(__file__).resolve().parent.parent
    for candidate in ("pss-darwin-arm64", "pss-linux-x86_64", "pss-darwin-x86_64"):
        p = root / "bin" / candidate
        if p.exists():
            binary = p
            break
    if binary is None:
        return None
    try:
        res = subprocess.run(
            [str(binary), "inspect", name, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return res.returncode == 0


def validate(path: Path, *, plugin: bool, check_index: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    text = path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    keys = fm.keys
    body = "\n".join(text.split("\n")[fm.end_line + 1 :]).strip()

    name = keys.get("name")
    if not name:
        errors.append("missing required field 'name'")
    elif not isinstance(name, str):
        errors.append("'name' must be a scalar, not a list")
    else:
        if not NAME_RE.match(name):
            errors.append(f"'name' must be lowercase-kebab-case, got {name!r}")
        if name != path.stem:
            errors.append(f"'name' is {name!r} but the filename stem is {path.stem!r}")

    description = keys.get("description")
    if not description:
        errors.append("missing required field 'description'")
    elif not isinstance(description, str):
        errors.append("'description' must be a scalar, not a list")
    elif len(description) > 1024:
        warnings.append(f"'description' is {len(description)} chars; keep it to one line")

    for key in keys:
        if key not in KNOWN_KEYS:
            warnings.append(f"unrecognized frontmatter key {key!r}")

    for key in LIST_KEYS:
        if key not in keys:
            continue
        value = keys[key]
        if not isinstance(value, list):
            errors.append(f"{key!r} must be a list")
        elif any(not item for item in value):
            errors.append(f"{key!r} contains an empty entry")

    if plugin:
        for key in sorted(PLUGIN_FORBIDDEN & set(keys)):
            errors.append(
                f"{key!r} is not permitted on a plugin-shipped agent "
                "(Claude Code drops it at load)"
            )

    if not body:
        errors.append("agent body is empty — the frontmatter alone tells it nothing")

    for match in PLACEHOLDER_RE.finditer(text):
        errors.append(
            f"unsubstituted placeholder {match.group(0)!r} — a format call did not run"
        )

    skills = keys.get("skills") or []
    if isinstance(skills, list) and check_index:
        for skill in skills:
            present = index_has_skill(skill)
            if present is None:
                warnings.append(
                    f"could not check {skill!r} against the index (no usable pss binary)"
                )
            elif not present:
                errors.append(
                    f"preloaded skill {skill!r} is not in the index — Claude Code "
                    "would skip it SILENTLY at startup"
                )

    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", help="path to the agent .md file")
    ap.add_argument(
        "--check-index",
        action="store_true",
        help="verify every preloaded skill resolves in the PSS index",
    )
    ap.add_argument(
        "--plugin",
        action="store_true",
        help="apply the plugin-shipped restrictions (no hooks/mcpServers/permissionMode)",
    )
    ap.add_argument("--json", action="store_true", help="emit a JSON report")
    args = ap.parse_args()

    path = Path(args.path)
    if not path.is_file():
        print(f"ERROR: not a file: {path}", file=sys.stderr)
        return 2

    try:
        errors, warnings = validate(path, plugin=args.plugin, check_index=args.check_index)
    except (ValueError, UnicodeDecodeError) as exc:
        if args.json:
            print(json.dumps({"path": str(path), "parse_error": str(exc)}, indent=1))
        else:
            print(f"ERROR: {path}: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "path": str(path),
                    "valid": not errors,
                    "errors": errors,
                    "warnings": warnings,
                },
                indent=1,
            )
        )
    else:
        for w in warnings:
            print(f"WARN  {path}: {w}")
        for e in errors:
            print(f"ERROR {path}: {e}", file=sys.stderr)
        if not errors:
            print(f"OK    {path}: valid ({len(warnings)} warning(s))")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
