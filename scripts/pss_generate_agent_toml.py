#!/usr/bin/env python3
"""
PSS Agent TOML Generator - Generate .agent.toml configuration files.

Reads an agent .md file, extracts metadata fields, builds a JSON descriptor,
calls the PSS Rust binary in --agent-profile mode, parses the JSON output,
and writes a valid .agent.toml configuration file.

Usage:
    uv run scripts/pss_generate_agent_toml.py /path/to/agent.md \
      [--requirements file1.md file2.md] \
      [--output /path/to/output.agent.toml] \
      [--binary /path/to/pss-binary] \
      [--index /path/to/skill-index.json] \
      [--cwd /project/path] \
      [--validate] \
      [--dry-run]
"""

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

# Platform-to-binary mapping (mirrors pss_hook.py detect_platform)
PLATFORM_MAP = {
    ("Darwin", "arm64"): "pss-darwin-arm64",
    ("Darwin", "x86_64"): "pss-darwin-x86_64",
    ("Linux", "x86_64"): "pss-linux-x86_64",
    ("Linux", "aarch64"): "pss-linux-arm64",
    ("Windows", "AMD64"): "pss-windows-x86_64.exe",
    ("Windows", "x86_64"): "pss-windows-x86_64.exe",
}

# Role keyword mapping: keyword pattern -> role label
ROLE_KEYWORDS = {
    "developer": re.compile(
        r"\b(develop|engineer|cod(e|ing)|program|implement)\b", re.IGNORECASE
    ),
    "tester": re.compile(r"\b(test|qa|quality\s*assurance)\b", re.IGNORECASE),
    "reviewer": re.compile(r"\b(review|audit|code\s*review)\b", re.IGNORECASE),
    "deployer": re.compile(
        r"\b(deploy|devops|infra(structure)?|ci/?cd)\b", re.IGNORECASE
    ),
    "designer": re.compile(
        r"\b(design|ui|ux|user\s*interface|user\s*experience)\b", re.IGNORECASE
    ),
    "security": re.compile(
        r"\b(security|vuln(erability)?|pentest|penetration)\b", re.IGNORECASE
    ),
    "data-scientist": re.compile(
        r"\b(data|ml|machine\s*learning|ai|analytics)\b", re.IGNORECASE
    ),
}

# Domain inference keywords
DOMAIN_KEYWORDS = {
    "security": re.compile(
        r"\b(security|auth|encrypt|vulnerability|pentest)\b", re.IGNORECASE
    ),
    "frontend": re.compile(
        r"\b(frontend|front-end|react|vue|angular|css|html|ui)\b", re.IGNORECASE
    ),
    "backend": re.compile(
        r"\b(backend|back-end|api|server|database|sql)\b", re.IGNORECASE
    ),
    "devops": re.compile(
        r"\b(devops|deploy|ci/?cd|docker|kubernetes|terraform|infra)\b", re.IGNORECASE
    ),
    "data": re.compile(
        r"\b(data|analytics|ml|machine\s*learning|ai|model)\b", re.IGNORECASE
    ),
    "testing": re.compile(
        r"\b(test|qa|quality|e2e|integration\s*test|unit\s*test)\b", re.IGNORECASE
    ),
    "mobile": re.compile(
        r"\b(mobile|ios|android|react\s*native|flutter)\b", re.IGNORECASE
    ),
    "cloud": re.compile(r"\b(aws|gcp|azure|cloud|serverless|lambda)\b", re.IGNORECASE),
}

# Known tool names that may appear in agent .md body text
KNOWN_TOOLS = {
    "Bash",
    "Read",
    "Write",
    "Edit",
    "Grep",
    "Glob",
    "WebSearch",
    "WebFetch",
    "Task",
    "TodoRead",
    "TodoWrite",
    "Agent",
    "Computer",
    "ServerTool",
}

# Common technology names for requirements extraction
TECH_NAMES = {
    "python",
    "javascript",
    "typescript",
    "rust",
    "go",
    "java",
    "kotlin",
    "swift",
    "ruby",
    "php",
    "c#",
    "csharp",
    "c++",
    "cpp",
    "elixir",
    "scala",
    "dart",
    "flutter",
    "react",
    "vue",
    "angular",
    "svelte",
    "next.js",
    "nextjs",
    "nuxt",
    "express",
    "fastapi",
    "django",
    "flask",
    "rails",
    "spring",
    "node",
    "nodejs",
    "deno",
    "bun",
    "docker",
    "kubernetes",
    "terraform",
    "ansible",
    "aws",
    "gcp",
    "azure",
    "postgresql",
    "postgres",
    "mysql",
    "mongodb",
    "redis",
    "sqlite",
    "graphql",
    "rest",
    "grpc",
    "kafka",
    "rabbitmq",
    "nginx",
    "tailwind",
    "bootstrap",
}

# Project type keywords for requirements extraction
PROJECT_TYPE_KEYWORDS = {
    "web": re.compile(
        r"\b(web\s*(app|application|site|page)|website|frontend|backend)\b",
        re.IGNORECASE,
    ),
    "mobile": re.compile(
        r"\b(mobile\s*(app|application)|ios|android|react\s*native|flutter)\b",
        re.IGNORECASE,
    ),
    "cli": re.compile(
        r"\b(cli|command[- ]line|terminal|console\s*app)\b", re.IGNORECASE
    ),
    "library": re.compile(
        r"\b(library|lib|package|module|sdk|framework)\b", re.IGNORECASE
    ),
    "api": re.compile(
        r"\b(api|rest\s*api|graphql\s*api|microservice)\b", re.IGNORECASE
    ),
    "microservice": re.compile(r"\b(microservice|micro[- ]service)\b", re.IGNORECASE),
}


def die(msg: str) -> NoReturn:
    """Print error message and exit with code 1."""
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def detect_binary_name() -> str:
    """Detect the platform-specific binary name using PLATFORM_MAP."""
    system = platform.system()
    machine = platform.machine()
    binary_name = PLATFORM_MAP.get((system, machine))
    if binary_name is None:
        die(
            f"Unsupported platform: {system} {machine}. "
            f"Supported: {', '.join(f'{s}-{m}' for s, m in PLATFORM_MAP)}"
        )
    return binary_name


def resolve_binary(binary_arg: str | None) -> Path:
    """Resolve the PSS binary path. Uses explicit --binary arg, or auto-detects."""
    if binary_arg:
        # Explicit path provided
        p = Path(binary_arg).resolve()
        if not p.exists():
            die(f"Binary not found at explicit path: {p}")
        return p

    binary_name = detect_binary_name()

    # Try CLAUDE_PLUGIN_ROOT env var first
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        p = Path(plugin_root) / "rust" / "skill-suggester" / "bin" / binary_name
        if p.exists():
            return p.resolve()

    # Fall back to relative path from this script
    script_dir = Path(__file__).parent.resolve()
    p = script_dir.parent / "rust" / "skill-suggester" / "bin" / binary_name
    if p.exists():
        return p.resolve()

    die(
        f"PSS binary not found. Searched:\n"
        f"  - $CLAUDE_PLUGIN_ROOT/rust/skill-suggester/bin/{binary_name}\n"
        f"  - {script_dir.parent / 'rust' / 'skill-suggester' / 'bin' / binary_name}\n"
        f"Build it with: uv run python scripts/pss_build.py"
    )
    return Path()  # unreachable, satisfies type checker


def resolve_index(index_arg: str | None) -> Path:
    """Resolve the skill index path."""
    if index_arg:
        p = Path(index_arg).resolve()
    else:
        p = Path.home() / ".claude" / "cache" / "skill-index.json"

    if not p.exists():
        die(f"Skill index not found at: {p}\nRun /pss-reindex-skills first")
    return p


def parse_frontmatter(content: str) -> dict[str, str | list[str]]:
    """Parse YAML frontmatter from markdown content (between --- markers).

    Returns a dict with string values. Lists (YAML arrays) are parsed into
    Python lists. Simple key: value pairs become strings.
    """
    if not content.startswith("---"):
        return {}

    end_idx = content.find("\n---", 3)
    if end_idx == -1:
        return {}

    frontmatter_text = content[3:end_idx].strip()
    result: dict[str, str | list[str]] = {}
    current_key: str | None = None
    current_list: list[str] | None = None

    for line in frontmatter_text.split("\n"):
        stripped = line.strip()

        # Check if this is a list continuation item (indented "- value")
        if current_key and current_list is not None and stripped.startswith("- "):
            item = stripped[2:].strip().strip('"').strip("'")
            current_list.append(item)
            continue

        # If we were collecting a list, save it
        if current_key and current_list is not None:
            result[current_key] = current_list
            current_key = None
            current_list = None

        # Parse key: value
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()

            if not value:
                # Could be start of a YAML list
                current_key = key
                current_list = []
            elif value.startswith("[") and value.endswith("]"):
                # Inline YAML array: [item1, item2]
                items = [
                    i.strip().strip('"').strip("'")
                    for i in value[1:-1].split(",")
                    if i.strip()
                ]
                result[key] = items
            else:
                result[key] = value.strip('"').strip("'")

    # Flush any trailing list
    if current_key and current_list is not None:
        result[current_key] = current_list

    return result


def extract_agent_name(frontmatter: dict[str, str | list[str]], md_path: Path) -> str:
    """Extract agent name from frontmatter or derive from filename."""
    fm_name = frontmatter.get("name")
    if fm_name and isinstance(fm_name, str):
        return fm_name.lower().replace(" ", "-")
    # Derive from filename stem (lowercase, spaces to hyphens)
    return md_path.stem.lower().replace(" ", "-").replace("_", "-")


def extract_description(frontmatter: dict[str, str | list[str]], content: str) -> str:
    """Extract description from frontmatter or first non-heading paragraph."""
    fm_desc = frontmatter.get("description")
    if fm_desc and isinstance(fm_desc, str):
        return fm_desc

    # Skip frontmatter in body
    body = content
    if content.startswith("---"):
        end_idx = content.find("\n---", 3)
        if end_idx != -1:
            body = content[end_idx + 4 :].strip()

    # Find first non-heading, non-empty paragraph
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
            return stripped
    return ""


def extract_role(description: str) -> str:
    """Infer agent role from description text using keyword matching."""
    for role, pattern in ROLE_KEYWORDS.items():
        if pattern.search(description):
            return role
    return "general"


def extract_duties(content: str) -> list[str]:
    """Extract duties from bullet lists under relevant headings.

    Looks for headings containing: responsib, duties, tasks, capabilities, features.
    Collects up to 10 bullet items from those sections.
    """
    # Skip frontmatter
    body = content
    if content.startswith("---"):
        end_idx = content.find("\n---", 3)
        if end_idx != -1:
            body = content[end_idx + 4 :]

    duty_heading_pattern = re.compile(
        r"^#+\s+.*\b(responsib|duties|tasks|capabilities|features)\b", re.IGNORECASE
    )
    any_heading_pattern = re.compile(r"^#+\s+")
    bullet_pattern = re.compile(r"^\s*[-*]\s+(.+)")

    duties: list[str] = []
    in_duty_section = False

    for line in body.split("\n"):
        if duty_heading_pattern.match(line):
            in_duty_section = True
            continue
        if in_duty_section and any_heading_pattern.match(line):
            in_duty_section = False
            continue
        if in_duty_section:
            m = bullet_pattern.match(line)
            if m:
                duty_text = m.group(1).strip()
                if duty_text:
                    duties.append(duty_text)
                if len(duties) >= 10:
                    break

    # Fallback: split description into sentences if no duties found
    if not duties:
        desc = extract_description({}, content)
        sentences = re.split(r"[.!?]+", desc)
        duties = [s.strip() for s in sentences if s.strip()][:5]

    return duties


def extract_tools(frontmatter: dict[str, str | list[str]], content: str) -> list[str]:
    """Extract tool names from frontmatter and body text scanning."""
    tools: set[str] = set()

    # From frontmatter fields
    for key in ("tools", "allowed-tools", "allowed_tools"):
        val = frontmatter.get(key)
        if isinstance(val, list):
            tools.update(val)
        elif isinstance(val, str):
            # Comma-separated or single value
            tools.update(t.strip() for t in val.split(",") if t.strip())

    # Scan body for known tool mentions
    for tool in KNOWN_TOOLS:
        # Match tool name as a word boundary (case-sensitive for tool names)
        if re.search(rf"\b{re.escape(tool)}\b", content):
            tools.add(tool)

    return sorted(tools)


def extract_domains(
    frontmatter: dict[str, str | list[str]], description: str
) -> list[str]:
    """Extract domains from frontmatter or infer from description keywords."""
    # From frontmatter
    fm_domains = frontmatter.get("domains")
    if isinstance(fm_domains, list) and fm_domains:
        return fm_domains
    if isinstance(fm_domains, str) and fm_domains:
        return [d.strip() for d in fm_domains.split(",") if d.strip()]

    # Infer from description
    domains: list[str] = []
    for domain, pattern in DOMAIN_KEYWORDS.items():
        if pattern.search(description):
            domains.append(domain)

    return domains if domains else ["general"]


def extract_requirements(req_files: list[str]) -> dict[str, str | list[str]]:
    """Read requirement files and extract project_type, tech_stack, and summary."""
    all_text = ""
    for filepath in req_files:
        p = Path(filepath).resolve()
        if not p.exists():
            die(f"Requirements file not found: {p}")
        all_text += p.read_text(encoding="utf-8") + "\n"

    # Detect project type
    project_type = "unknown"
    for ptype, pattern in PROJECT_TYPE_KEYWORDS.items():
        if pattern.search(all_text):
            project_type = ptype
            break

    # Detect tech stack
    lower_text = all_text.lower()
    tech_stack = sorted(t for t in TECH_NAMES if t.lower() in lower_text)

    # Condense to summary (first 2000 chars)
    summary = all_text[:2000].strip()

    return {
        "project_type": project_type,
        "tech_stack": tech_stack,
        "requirements_summary": summary,
    }


def build_descriptor(
    md_path: Path,
    req_files: list[str],
    cwd: str,
) -> dict[str, str | list[str]]:
    """Build the JSON descriptor dict from the agent .md file and requirements."""
    content = md_path.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(content)
    name = extract_agent_name(frontmatter, md_path)
    description = extract_description(frontmatter, content)
    role = extract_role(description)
    duties = extract_duties(content)
    tools = extract_tools(frontmatter, content)
    domains = extract_domains(frontmatter, description)

    descriptor: dict[str, str | list[str]] = {
        "name": name,
        "description": description,
        "role": role,
        "duties": duties,
        "tools": tools,
        "domains": domains,
        "cwd": cwd,
    }

    # Add requirements info if provided
    if req_files:
        req_info = extract_requirements(req_files)
        descriptor["requirements_summary"] = req_info["requirements_summary"]
        descriptor["project_type"] = req_info["project_type"]
        descriptor["tech_stack"] = req_info["tech_stack"]
    else:
        descriptor["requirements_summary"] = ""

    return descriptor


def call_binary(binary: Path, descriptor: dict, index: Path) -> dict:
    """Call the PSS binary with --agent-profile and return parsed JSON output."""
    # Write descriptor to tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        json.dump(descriptor, tmp, indent=2)
        tmp_path = tmp.name

    try:
        cmd = [
            str(binary),
            "--agent-profile",
            tmp_path,
            "--index",
            str(index),
            "--format",
            "json",
            "--top",
            "30",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            die(
                f"Binary exited with code {result.returncode}.\nstderr: {result.stderr}"
            )

        stdout = result.stdout.strip()
        if not stdout:
            die("Binary returned empty output")

        try:
            return json.loads(stdout)
        except json.JSONDecodeError as e:
            die(f"Binary returned invalid JSON: {e}\nOutput: {stdout[:500]}")
            return {}  # unreachable
    finally:
        os.unlink(tmp_path)


def _toml_list(items: list[str]) -> str:
    """Format a Python list of strings as a TOML inline array."""
    if not items:
        return "[]"
    escaped = [f'"{item}"' for item in items]
    # If short enough, single line
    joined = ", ".join(escaped)
    if len(joined) < 80:
        return f"[{joined}]"
    # Multi-line for long lists
    lines = ",\n  ".join(escaped)
    return f"[\n  {lines},\n]"


def write_toml(
    output_path: Path,
    name: str,
    md_path: Path,
    req_files: list[str],
    req_info: dict,
    binary_output: dict,
) -> None:
    """Write the .agent.toml file from binary output and metadata."""
    now = datetime.now(timezone.utc).isoformat()
    req_basenames = [Path(f).name for f in req_files] if req_files else []

    # Extract lists from binary output
    skills = binary_output.get("skills", {})
    primary_names = [s["name"] for s in skills.get("primary", []) if "name" in s]
    secondary_names = [s["name"] for s in skills.get("secondary", []) if "name" in s]
    specialized_names = [
        s["name"] for s in skills.get("specialized", []) if "name" in s
    ]

    complementary = binary_output.get("complementary_agents", [])
    command_names = [
        c["name"] for c in binary_output.get("commands", []) if "name" in c
    ]
    rule_names = [r["name"] for r in binary_output.get("rules", []) if "name" in r]
    mcp_names = [m["name"] for m in binary_output.get("mcp", []) if "name" in m]
    lsp_names = [
        entry["name"] for entry in binary_output.get("lsp", []) if "name" in entry
    ]

    # Build TOML content
    req_files_str = _toml_list(req_basenames)
    project_type = req_info.get("project_type", "unknown") if req_info else "unknown"
    tech_stack = req_info.get("tech_stack", []) if req_info else []

    lines = [
        "# Auto-generated by pss_generate_agent_toml.py",
        f"# Agent: {name}",
        f"# Generated: {now}",
        f"# Requirements: {', '.join(req_basenames) if req_basenames else 'none'}",
        "",
        "[agent]",
        f'name = "{name}"',
        'source = "path"',
        f'path = "{md_path.resolve()}"',
        "",
        "[requirements]",
        f"files = {req_files_str}",
        f'project_type = "{project_type}"',
        f"tech_stack = {_toml_list(tech_stack)}",
        "",
        "[skills]",
        f"primary = {_toml_list(primary_names)}",
        f"secondary = {_toml_list(secondary_names)}",
        f"specialized = {_toml_list(specialized_names)}",
        "",
        "[agents]",
        f"recommended = {_toml_list(complementary)}",
        "",
        "[commands]",
        f"recommended = {_toml_list(command_names)}",
        "",
        "[rules]",
        f"recommended = {_toml_list(rule_names)}",
        "",
        "[mcp]",
        f"recommended = {_toml_list(mcp_names)}",
        "",
        "[hooks]",
        "recommended = []",
        "",
        "[lsp]",
        f"recommended = {_toml_list(lsp_names)}",
        "",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote: {output_path}", file=sys.stderr)


def run_validator(output_path: Path) -> int:
    """Run pss_validate_agent_toml.py on the generated file. Returns exit code."""
    script_dir = Path(__file__).parent.resolve()
    validator = script_dir / "pss_validate_agent_toml.py"
    cmd = [
        sys.executable,
        str(validator),
        str(output_path),
        "--check-index",
        "--verbose",
    ]
    result = subprocess.run(cmd)
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="pss_generate_agent_toml",
        description="Generate .agent.toml configuration from an agent .md file using the PSS binary.",
    )
    parser.add_argument("agent_md", type=str, help="Path to the agent .md file")
    parser.add_argument(
        "--requirements",
        nargs="+",
        default=[],
        metavar="FILE",
        help="Requirement .md files to include in analysis",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output path for .agent.toml (default: team/agents-cfg/<name>.agent.toml)",
    )
    parser.add_argument(
        "--binary",
        type=str,
        default=None,
        help="Explicit path to PSS binary",
    )
    parser.add_argument(
        "--index",
        type=str,
        default=None,
        help="Path to skill-index.json (default: ~/.claude/cache/skill-index.json)",
    )
    parser.add_argument(
        "--cwd",
        type=str,
        default=None,
        help="Working directory context (default: os.getcwd())",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run pss_validate_agent_toml.py on the output after generation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the JSON descriptor to stdout and exit without calling binary or writing TOML",
    )
    return parser


def main() -> None:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    # Validate agent .md file exists
    md_path = Path(args.agent_md).resolve()
    if not md_path.exists():
        die(f"Agent .md file not found: {md_path}")

    cwd = args.cwd if args.cwd else os.getcwd()

    # Build the JSON descriptor
    descriptor = build_descriptor(md_path, args.requirements, cwd)

    # Dry-run: print descriptor and exit
    if args.dry_run:
        print(json.dumps(descriptor, indent=2))
        sys.exit(0)

    # Resolve binary and index paths (only needed for non-dry-run)
    binary = resolve_binary(args.binary)
    index = resolve_index(args.index)

    # Call the PSS binary
    binary_output = call_binary(binary, descriptor, index)

    # Determine output path
    name = descriptor["name"]
    if args.output:
        output_path = Path(args.output).resolve()
    else:
        output_path = Path(cwd) / "team" / "agents-cfg" / f"{name}.agent.toml"

    # Extract requirements info for TOML writing
    req_info = extract_requirements(args.requirements) if args.requirements else {}

    # Write the TOML file
    req_files: list[str] = args.requirements if args.requirements else []
    write_toml(output_path, str(name), md_path, req_files, req_info, binary_output)

    # Optionally validate
    if args.validate:
        exit_code = run_validator(output_path)
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
