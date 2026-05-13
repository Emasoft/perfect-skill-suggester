#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pycozo[embedded]>=0.7.6",
# ]
# ///
"""Generate a Claude Code plugin from an .agent.toml profile.

Reads the profile, resolves all element paths from the skill index,
copies them into a standard plugin directory structure following the
Anthropic plugin specification.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomllib  # Python 3.11+ (required)


def load_profile(profile_path: Path) -> dict:
    """Load and parse the .agent.toml file."""
    with open(profile_path, "rb") as f:
        return tomllib.load(f)


def load_skill_index() -> dict:
    """Load the skill index to resolve element paths.

    As of Phase C (v3.0.0): CozoDB is the single source of truth. This reads
    every row once and builds a {name: entry} dict compatible with the
    legacy JSON shape. Kept as a helper for callers that need the full
    dict; new code should prefer resolve_element_path() which does a single
    indexed lookup per call.
    """
    # Lazy import so callers that don't need the index avoid paying the
    # pycozo import cost.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import pss_cozodb
    except ImportError:
        print(
            "ERROR: pycozo is required. Install with: uv pip install 'pycozo[embedded]'",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        return pss_cozodb.get_all_entries()
    except FileNotFoundError:
        print(
            "ERROR: CozoDB not found. Run /pss-reindex-skills first.",
            file=sys.stderr,
        )
        sys.exit(1)


def resolve_element_path(name: str, index: dict) -> str | None:
    """Resolve an element name to its file path via the skill index.

    Phase C: index is the {name: entry} dict built by load_skill_index().
    When the path in the index points at a file that no longer exists on
    disk, returns None — matches the pre-C behaviour that skipped stale
    entries.
    """
    entry = index.get(name)
    if isinstance(entry, dict):
        path = entry.get("path", "")
        if path and Path(path).exists():
            return path
    return None


def resolve_element_type(name: str, index: dict) -> str:
    """Get the type of an element from the index."""
    entry = index.get(name)
    if isinstance(entry, dict):
        return entry.get("type", "skill")
    return "skill"


def copy_skill(name: str, source_path: str, dest_skills_dir: Path) -> bool:
    """Copy a skill directory (SKILL.md + references/ + scripts/ + examples/)."""
    source = Path(source_path)

    # Skills are directories containing SKILL.md
    if source.name == "SKILL.md":
        skill_dir = source.parent
    else:
        skill_dir = source

    if not skill_dir.is_dir():
        print(f"  WARNING: Skill directory not found: {skill_dir}", file=sys.stderr)
        return False

    # Use the skill directory name as the destination name
    dest_dir = dest_skills_dir / skill_dir.name
    if dest_dir.exists():
        print(
            f"  WARNING: Skill directory already exists, skipping: {dest_dir.name}",
            file=sys.stderr,
        )
        return False

    # Copy the entire skill directory (SKILL.md + references/ + scripts/ + assets/)
    shutil.copytree(skill_dir, dest_dir, symlinks=True, dirs_exist_ok=False)
    return True


def copy_agent(name: str, source_path: str, dest_agents_dir: Path) -> bool:
    """Copy an agent .md file."""
    source = Path(source_path)
    if not source.exists():
        print(f"  WARNING: Agent file not found: {source}", file=sys.stderr)
        return False

    dest = dest_agents_dir / source.name
    if dest.exists():
        print(
            f"  WARNING: Agent file already exists, skipping: {source.name}",
            file=sys.stderr,
        )
        return False

    shutil.copy2(source, dest)
    return True


def copy_command(name: str, source_path: str, dest_commands_dir: Path) -> bool:
    """Copy a command .md file and its subdirectory (if any)."""
    source = Path(source_path)
    if not source.exists():
        print(f"  WARNING: Command file not found: {source}", file=sys.stderr)
        return False

    dest = dest_commands_dir / source.name
    if dest.exists():
        print(
            f"  WARNING: Command file already exists, skipping: {source.name}",
            file=sys.stderr,
        )
        return False

    shutil.copy2(source, dest)

    # Check for command subdirectory (e.g., pss-setup-agent/execution.md)
    subdir = source.parent / source.stem
    if subdir.is_dir():
        dest_subdir = dest_commands_dir / source.stem
        shutil.copytree(subdir, dest_subdir, symlinks=True, dirs_exist_ok=False)

    return True


def copy_rule(name: str, source_path: str, dest_rules_dir: Path) -> bool:
    """Copy a rule .md file."""
    source = Path(source_path)
    if not source_path or not source.exists():
        # Try common rule locations
        for candidate in [
            Path.home() / ".claude" / "rules" / f"{name}.md",
            Path(".claude") / "rules" / f"{name}.md",
        ]:
            if candidate.exists():
                source = candidate
                break
        else:
            print(f"  WARNING: Rule file not found: {name}", file=sys.stderr)
            return False

    dest = dest_rules_dir / source.name
    if dest.exists():
        return False

    shutil.copy2(source, dest)
    return True


def _normalize_plugin_dependency(entry: Any) -> Any | None:
    """Normalize one entry from [dependencies].plugins into plugin.json's
    `dependencies` array shape.

    Accepts:
      - bare string -> kept as-is
      - dict with {name, version?, marketplace?} -> kept verbatim,
        unknown keys filtered out, `name` required

    Returns the normalized entry, or None if the input is invalid (caller
    should skip and emit a warning).
    """
    if isinstance(entry, str):
        stripped = entry.strip()
        if not stripped:
            return None
        return stripped
    if isinstance(entry, dict):
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        obj: dict[str, str] = {"name": name.strip()}
        version = entry.get("version")
        if isinstance(version, str) and version.strip():
            obj["version"] = version.strip()
        marketplace = entry.get("marketplace")
        if isinstance(marketplace, str) and marketplace.strip():
            obj["marketplace"] = marketplace.strip()
        # If the entry has only `name` and no other fields, collapse to bare
        # string form for terser plugin.json output (matches the docs idiom).
        if set(obj.keys()) == {"name"}:
            return obj["name"]
        return obj
    return None


def generate_plugin_json(
    plugin_name: str,
    agent_name: str,
    description: str,
    profile: dict,
    version: str = "0.1.0",
) -> dict:
    """Generate the plugin.json manifest.

    Emits a manifest conforming to the Claude Code plugins-reference schema
    at https://code.claude.com/docs/en/plugins-reference and the dependency
    rules at https://code.claude.com/docs/en/plugin-dependencies.

    Top-level keys emitted (when source data is present):
      - name, version, description, author, keywords
      - homepage, repository, license (from [metadata])
      - userConfig (verbatim from [userConfig])
      - channels (verbatim from [[channels]])
      - dependencies (normalized from [dependencies].plugins — CC v2.1.110+)
      - experimental.themes (verbatim from [themes] — CC v2.1.129+ nesting)
      - experimental.monitors (verbatim from [monitors] — CC v2.1.129+ nesting)

    NOTE: per CC v2.1.129 the experimental components (themes, monitors)
    moved under `experimental.{key}`. Top-level keys still work but emit a
    warning in `claude plugin validate`; new plugins should use the nested
    form.
    """
    manifest: dict[str, Any] = {
        "name": plugin_name,
        "description": description,
        "version": version,
        "author": {
            "name": os.environ.get("GIT_AUTHOR", os.environ.get("USER", "Unknown")),
        },
    }

    # Add keywords from the profile's tech stack and domains
    keywords = []
    req = profile.get("requirements", {})
    if isinstance(req, dict) and req.get("tech_stack"):
        keywords.extend(req["tech_stack"])
    keywords.append(agent_name)
    if keywords:
        manifest["keywords"] = keywords[:10]  # Cap at 10

    # Propagate optional provenance fields from [metadata] section, if present.
    # These become plugin.json homepage/repository/license per plugins-reference.md.
    # Guard with isinstance(dict) — if a user writes `metadata = "foo"` at top
    # level, profile.get returns a string and .get(key) would crash.
    metadata = profile.get("metadata", {})
    if isinstance(metadata, dict):
        for key in ("homepage", "repository", "license"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                manifest[key] = value.strip()

    # Propagate the optional [userConfig] section verbatim into plugin.json.
    # PSS does NOT validate the nested structure — consumers must follow the
    # Claude Code plugins-reference.md userConfig schema. Pass-through only.
    user_config = profile.get("userConfig")
    if isinstance(user_config, dict) and user_config:
        manifest["userConfig"] = user_config

    # Propagate the optional [[channels]] array verbatim into plugin.json.
    # Each channel binds to an MCP server in this plugin's mcpServers and can
    # carry its own userConfig per the plugins-reference channels schema.
    channels = profile.get("channels")
    if isinstance(channels, list) and channels:
        manifest["channels"] = channels

    # Plugin dependencies (CC v2.1.110+). Translate [dependencies].plugins —
    # which accepts either bare strings or {name, version?, marketplace?}
    # objects — directly into plugin.json's `dependencies` array. Claude Code
    # resolves these against `{plugin-name}--v{version}` git tags in the
    # marketplace repo and auto-installs missing ones at plugin install time.
    deps_section = profile.get("dependencies", {})
    if isinstance(deps_section, dict):
        plugin_deps = deps_section.get("plugins", [])
        if isinstance(plugin_deps, list) and plugin_deps:
            normalized: list[Any] = []
            for entry in plugin_deps:
                norm = _normalize_plugin_dependency(entry)
                if norm is not None:
                    normalized.append(norm)
                else:
                    print(
                        f"WARNING: Skipping malformed plugin dependency entry: {entry!r}",
                        file=sys.stderr,
                    )
            if normalized:
                manifest["dependencies"] = normalized

    # CC v2.1.129+ requires experimental components (themes, monitors) to be
    # nested under `experimental`. Top-level still works but emits a
    # `claude plugin validate` warning. PSS emits the nested form for both.
    experimental: dict[str, Any] = {}
    themes = profile.get("themes")
    if isinstance(themes, dict) and themes:
        experimental["themes"] = themes
    monitors = profile.get("monitors")
    if isinstance(monitors, dict) and monitors:
        experimental["monitors"] = monitors
    if experimental:
        manifest["experimental"] = experimental

    return manifest


def generate_readme(
    plugin_name: str,
    agent_name: str,
    description: str,
    profile: dict,
    stats: dict,
) -> str:
    """Generate a README.md for the plugin."""
    lines = [
        f"# {plugin_name}",
        "",
        f"> {description}",
        "",
        f"Claude Code plugin generated from `{agent_name}.agent.toml` profile by [PSS](https://github.com/Emasoft/perfect-skill-suggester).",
        "",
        "## Contents",
        "",
    ]

    if stats.get("skills"):
        lines.append(f"### Skills ({stats['skills']})")
        for name in profile.get("skills", {}).get("primary", []):
            lines.append(f"- **{name}** (primary)")
        for name in profile.get("skills", {}).get("secondary", []):
            lines.append(f"- {name} (secondary)")
        for name in profile.get("skills", {}).get("specialized", []):
            lines.append(f"- {name} (specialized)")
        lines.append("")

    if stats.get("agents"):
        lines.append(f"### Agents ({stats['agents']})")
        for sect in ("subagents", "agents"):
            for name in profile.get(sect, {}).get("recommended", []):
                lines.append(f"- {name}")
        lines.append("")

    if stats.get("commands"):
        lines.append(f"### Commands ({stats['commands']})")
        for name in profile.get("commands", {}).get("recommended", []):
            lines.append(f"- `/{plugin_name}:{name}`")
        lines.append("")

    if stats.get("rules"):
        lines.append(f"### Rules ({stats['rules']})")
        for name in profile.get("rules", {}).get("recommended", []):
            lines.append(f"- {name}")
        lines.append("")
        lines.append(
            "> Rules are symlinked into `.claude/rules/` at session start and cleaned up at session end."
        )
        lines.append(
            f"> Symlinks are prefixed with `_plugin_{plugin_name}_` for identification."
        )
        lines.append("")

    lines.extend(
        [
            "## Installation",
            "",
            "```bash",
            f"claude plugin install /path/to/{plugin_name}",
            "```",
            "",
            "## Generated",
            "",
            f"- **Date**: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
            f"- **Source profile**: `{agent_name}.agent.toml`",
            "- **Generator**: PSS `/pss-make-plugin-from-profile`",
            "",
        ]
    )

    return "\n".join(lines)


def generate_rules_hook_scripts(plugin_name: str, scripts_dir: Path) -> None:
    """Generate the SessionStart/SessionEnd hook scripts for rule symlinks.

    Rules are not a native plugin component, so we use hooks to symlink
    them into the project's .claude/rules/ at session start and clean up
    at session end.
    """
    # Prefix used to identify symlinks created by this plugin
    prefix = f"_plugin_{plugin_name}_"

    install_script = scripts_dir / "install-rules.sh"
    install_script.write_text(
        f"""#!/usr/bin/env bash
# Auto-generated by PSS — symlinks plugin rules into project .claude/rules/
# Runs on SessionStart. Reads JSON from stdin to get project cwd.
set -euo pipefail

PLUGIN_ROOT="${{CLAUDE_PLUGIN_ROOT}}"
RULES_SRC="${{PLUGIN_ROOT}}/rules"

# Read cwd from stdin JSON (SessionStart provides it)
CWD="$(cat | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null || echo "")"
[ -z "$CWD" ] && exit 0
[ ! -d "$RULES_SRC" ] && exit 0

RULES_DST="${{CWD}}/.claude/rules"
mkdir -p "$RULES_DST"

# Clean stale/broken symlinks from this plugin (e.g. after crash)
for link in "$RULES_DST"/{prefix}*.md; do
    [ -L "$link" ] && [ ! -e "$link" ] && rm -f "$link"
done

# Create fresh symlinks for each rule
for rule in "$RULES_SRC"/*.md; do
    [ -f "$rule" ] || continue
    basename="$(basename "$rule")"
    target="${{RULES_DST}}/{prefix}${{basename}}"
    ln -sf "$rule" "$target"
done

exit 0
""",
    )
    install_script.chmod(0o755)

    cleanup_script = scripts_dir / "cleanup-rules.sh"
    cleanup_script.write_text(
        f"""#!/usr/bin/env bash
# Auto-generated by PSS — removes plugin rule symlinks from project .claude/rules/
# Runs on SessionEnd (1.5s timeout — must be fast).
set -euo pipefail

CWD="$(cat | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null || echo "")"
[ -z "$CWD" ] && exit 0

RULES_DST="${{CWD}}/.claude/rules"
[ ! -d "$RULES_DST" ] && exit 0

# Remove only symlinks created by this plugin (matching our prefix)
for link in "$RULES_DST"/{prefix}*.md; do
    [ -L "$link" ] && rm -f "$link"
done

exit 0
""",
    )
    cleanup_script.chmod(0o755)


def generate_data_dir_hook_script(
    plugin_name: str,
    data_dir_spec: dict,
    scripts_dir: Path,
    output_dir: Path,
) -> bool:
    """Generate a SessionStart hook that lazily installs runtime deps into
    ${CLAUDE_PLUGIN_DATA} on first session start and after manifest bumps.

    The hook compares the bundled manifest in ${CLAUDE_PLUGIN_ROOT} against a
    copy in ${CLAUDE_PLUGIN_DATA}; if they differ (or the copy is missing),
    it runs the appropriate install command and updates the copy. If the
    install fails, the copy is removed so the next session retries.

    Per CC plugins-reference: ${CLAUDE_PLUGIN_DATA} survives plugin updates,
    is created on first reference, and is deleted on uninstall (unless
    --keep-data is passed).

    Returns True if the script was generated (data_dir_spec had at least one
    handled directive), False otherwise.
    """
    npm_manifest = data_dir_spec.get("npm")
    pip_manifest = data_dir_spec.get("pip")
    cargo_manifest = data_dir_spec.get("rust_cargo")
    downloads = data_dir_spec.get("downloads")

    if not any([npm_manifest, pip_manifest, cargo_manifest, downloads]):
        return False

    # Copy bundled manifests into the plugin tree so ${CLAUDE_PLUGIN_ROOT}/
    # references resolve at install time.
    for relpath in (npm_manifest, pip_manifest, cargo_manifest):
        if not isinstance(relpath, str):
            continue
        # Strip leading ./ and verify the file exists somewhere we can copy
        # it from. The plugin generator runs in two contexts: from the dev
        # tree where these files live next to the profile, OR from a
        # finished plugin. We can't auto-copy them — surface the requirement
        # and let the author drop them in manually.
        cleaned = relpath.lstrip("./")
        if not (output_dir / cleaned).exists():
            print(
                f"WARNING: [data_dir] references '{relpath}' but the file is "
                f"not present in the generated plugin. Drop the file at "
                f"{output_dir / cleaned} before publishing.",
                file=sys.stderr,
            )

    blocks: list[str] = []
    if isinstance(npm_manifest, str) and npm_manifest:
        rel = npm_manifest.lstrip("./")
        blocks.append(
            f'# npm: install from {rel} into ${{CLAUDE_PLUGIN_DATA}}/node_modules\n'
            f'NPM_SRC="${{CLAUDE_PLUGIN_ROOT}}/{rel}"\n'
            f'NPM_CACHE="${{CLAUDE_PLUGIN_DATA}}/{rel.rsplit("/", 1)[-1]}"\n'
            f'if [ -f "$NPM_SRC" ]; then\n'
            f'    if ! diff -q "$NPM_SRC" "$NPM_CACHE" >/dev/null 2>&1; then\n'
            f'        mkdir -p "${{CLAUDE_PLUGIN_DATA}}"\n'
            f'        cp "$NPM_SRC" "$NPM_CACHE"\n'
            f'        (cd "${{CLAUDE_PLUGIN_DATA}}" && npm install --silent 2>&1) || rm -f "$NPM_CACHE"\n'
            f'    fi\n'
            f'fi'
        )
    if isinstance(pip_manifest, str) and pip_manifest:
        rel = pip_manifest.lstrip("./")
        blocks.append(
            f'# pip: install from {rel} into ${{CLAUDE_PLUGIN_DATA}}/.venv via uv\n'
            f'PIP_SRC="${{CLAUDE_PLUGIN_ROOT}}/{rel}"\n'
            f'PIP_CACHE="${{CLAUDE_PLUGIN_DATA}}/{rel.rsplit("/", 1)[-1]}"\n'
            f'if [ -f "$PIP_SRC" ]; then\n'
            f'    if ! diff -q "$PIP_SRC" "$PIP_CACHE" >/dev/null 2>&1; then\n'
            f'        mkdir -p "${{CLAUDE_PLUGIN_DATA}}"\n'
            f'        cp "$PIP_SRC" "$PIP_CACHE"\n'
            f'        VENV="${{CLAUDE_PLUGIN_DATA}}/.venv"\n'
            f'        [ -d "$VENV" ] || uv venv --python 3.12 "$VENV" >/dev/null 2>&1\n'
            f'        if ! uv pip install --python "$VENV/bin/python" -r "$PIP_CACHE" --quiet 2>&1; then\n'
            f'            rm -f "$PIP_CACHE"\n'
            f'        fi\n'
            f'    fi\n'
            f'fi'
        )
    if isinstance(cargo_manifest, str) and cargo_manifest:
        rel = cargo_manifest.lstrip("./")
        blocks.append(
            f'# rust_cargo: build {rel} into ${{CLAUDE_PLUGIN_DATA}}/bin\n'
            f'CARGO_SRC="${{CLAUDE_PLUGIN_ROOT}}/{rel}"\n'
            f'CARGO_CACHE="${{CLAUDE_PLUGIN_DATA}}/{rel.rsplit("/", 1)[-1]}"\n'
            f'if [ -f "$CARGO_SRC" ]; then\n'
            f'    if ! diff -q "$CARGO_SRC" "$CARGO_CACHE" >/dev/null 2>&1; then\n'
            f'        mkdir -p "${{CLAUDE_PLUGIN_DATA}}/bin"\n'
            f'        cp "$CARGO_SRC" "$CARGO_CACHE"\n'
            f'        CARGO_DIR="$(dirname "$CARGO_SRC")"\n'
            f'        (cd "$CARGO_DIR" && cargo build --release --target-dir "${{CLAUDE_PLUGIN_DATA}}/target" 2>&1 && cp "${{CLAUDE_PLUGIN_DATA}}/target/release/"* "${{CLAUDE_PLUGIN_DATA}}/bin/" 2>/dev/null) || rm -f "$CARGO_CACHE"\n'
            f'    fi\n'
            f'fi'
        )
    if isinstance(downloads, list) and downloads:
        for dl in downloads:
            if not isinstance(dl, dict):
                continue
            url = dl.get("url")
            sha256 = dl.get("sha256")
            dest = dl.get("dest")
            if not (
                isinstance(url, str)
                and isinstance(sha256, str)
                and isinstance(dest, str)
            ):
                continue
            blocks.append(
                f'# download: {url} -> ${{CLAUDE_PLUGIN_DATA}}/{dest}\n'
                f'DL_DEST="${{CLAUDE_PLUGIN_DATA}}/{dest}"\n'
                f'mkdir -p "$(dirname "$DL_DEST")"\n'
                f'if [ ! -f "$DL_DEST" ] || ! echo "{sha256}  $DL_DEST" | sha256sum -c --status 2>/dev/null; then\n'
                f'    curl -fsSL -o "$DL_DEST.tmp" "{url}" && \\\n'
                f'        echo "{sha256}  $DL_DEST.tmp" | sha256sum -c --status && \\\n'
                f'        mv "$DL_DEST.tmp" "$DL_DEST" || rm -f "$DL_DEST.tmp" "$DL_DEST"\n'
                f'fi'
            )

    install_script = scripts_dir / "install-data-deps.sh"
    body = "\n\n".join(blocks)
    install_script.write_text(
        f"""#!/usr/bin/env bash
# Auto-generated by PSS — lazily installs runtime deps for plugin '{plugin_name}'
# into ${{CLAUDE_PLUGIN_DATA}} on first SessionStart and after manifest bumps.
# Re-runs only when bundled manifests in ${{CLAUDE_PLUGIN_ROOT}} differ from
# the cached copy in ${{CLAUDE_PLUGIN_DATA}}.
set -uo pipefail

# CLAUDE_PLUGIN_DATA must be set; CC provides it for hook subprocesses.
[ -z "${{CLAUDE_PLUGIN_DATA:-}}" ] && exit 0
[ -z "${{CLAUDE_PLUGIN_ROOT:-}}" ] && exit 0

{body}

exit 0
"""
    )
    install_script.chmod(0o755)
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Generate a Claude Code plugin from an .agent.toml profile"
    )
    parser.add_argument("profile", help="Path to .agent.toml file")
    parser.add_argument(
        "--output", required=True, help="Output directory for the plugin"
    )
    parser.add_argument("--name", help="Override plugin name (default: agent name)")
    args = parser.parse_args()

    profile_path = Path(args.profile).resolve()
    output_dir = Path(args.output).resolve()

    # Validate input
    if not profile_path.exists():
        print(f"ERROR: Profile not found: {profile_path}", file=sys.stderr)
        sys.exit(1)
    if not profile_path.suffix == ".toml":
        print(
            f"ERROR: Expected .agent.toml file, got: {profile_path.name}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Check output doesn't already have a plugin
    if (output_dir / ".claude-plugin").exists():
        print(
            "ERROR: Output directory already contains .claude-plugin/. Use a fresh directory.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load profile
    print(f"Loading profile: {profile_path}")
    profile = load_profile(profile_path)

    agent_section = profile.get("agent", {})
    agent_name = agent_section.get("name", profile_path.stem.replace(".agent", ""))
    agent_path = agent_section.get("path", "")
    plugin_name = args.name or agent_name

    # Quad-match check: plugin name should match agent name for AI Maestro compatibility
    if plugin_name != agent_name:
        print(
            f"WARNING: Plugin name '{plugin_name}' differs from agent name '{agent_name}'. AI Maestro requires these to match.",
            file=sys.stderr,
        )

    # Validate plugin name is kebab-case
    if not re.match(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$", plugin_name):
        print(
            f"ERROR: Plugin name must be kebab-case: '{plugin_name}'", file=sys.stderr
        )
        sys.exit(1)

    # Load skill index for path resolution
    print("Loading skill index...")
    index = load_skill_index()

    # Collect all element names from the profile
    skills_section = profile.get("skills", {})
    all_skill_names = (
        skills_section.get("primary", [])
        + skills_section.get("secondary", [])
        + skills_section.get("specialized", [])
    )
    agent_names = profile.get("subagents", profile.get("agents", {})).get(
        "recommended", []
    )
    command_names = profile.get("commands", {}).get("recommended", [])
    rule_names = profile.get("rules", {}).get("recommended", [])
    mcp_names = profile.get("mcp", {}).get("recommended", [])
    hook_names = profile.get("hooks", {}).get("recommended", [])

    print(
        f"Profile: {len(all_skill_names)} skills, {len(agent_names)} agents, {len(command_names)} commands, {len(rule_names)} rules, {len(mcp_names)} MCPs"
    )

    # Create plugin directory structure
    print(f"Creating plugin at: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / ".claude-plugin").mkdir(exist_ok=True)

    # Track stats for README
    stats = {
        "skills": 0,
        "agents": 0,
        "commands": 0,
        "rules": 0,
        "mcp": 0,
        "output_styles": 0,
    }

    # Copy skills
    if all_skill_names:
        skills_dir = output_dir / "skills"
        skills_dir.mkdir(exist_ok=True)
        for name in all_skill_names:
            path = resolve_element_path(name, index)
            if path:
                if copy_skill(name, path, skills_dir):
                    stats["skills"] += 1
                    print(f"  ✓ skill: {name}")
            else:
                print(f"  ✗ skill: {name} — not found in index", file=sys.stderr)

    # Copy the agent definition itself
    agents_dir = output_dir / "agents"
    agents_dir.mkdir(exist_ok=True)
    if agent_path and Path(agent_path).exists():
        shutil.copy2(agent_path, agents_dir / Path(agent_path).name)
        stats["agents"] += 1
        print(f"  ✓ agent: {agent_name} (main agent definition)")

    # Copy recommended agents
    for name in agent_names:
        path = resolve_element_path(name, index)
        if path:
            if copy_agent(name, path, agents_dir):
                stats["agents"] += 1
                print(f"  ✓ agent: {name}")
        else:
            print(f"  ✗ agent: {name} — not found in index", file=sys.stderr)

    # Copy commands
    if command_names:
        commands_dir = output_dir / "commands"
        commands_dir.mkdir(exist_ok=True)
        for name in command_names:
            path = resolve_element_path(name, index)
            if path:
                if copy_command(name, path, commands_dir):
                    stats["commands"] += 1
                    print(f"  ✓ command: {name}")
            else:
                print(f"  ✗ command: {name} — not found in index", file=sys.stderr)

    # Copy rules to plugin's rules/ dir (not a standard plugin component).
    # A SessionStart hook will symlink them into the project's .claude/rules/.
    if rule_names:
        rules_dir = output_dir / "rules"
        rules_dir.mkdir(exist_ok=True)
        for name in rule_names:
            path = resolve_element_path(name, index)
            if path:
                if copy_rule(name, path, rules_dir):
                    stats["rules"] += 1
                    print(f"  ✓ rule: {name}")
            else:
                # Try direct path for rules (they may not be in the skill index)
                if copy_rule(name, "", rules_dir):
                    stats["rules"] += 1
                    print(f"  ✓ rule: {name} (from user rules)")
                else:
                    print(f"  ✗ rule: {name} — not found", file=sys.stderr)

    # Copy output styles to plugin's output-styles/ dir
    output_style_names = profile.get("output_styles", {}).get("recommended", [])
    if output_style_names:
        output_styles_dir = output_dir / "output-styles"
        output_styles_dir.mkdir(exist_ok=True)
        for name in output_style_names:
            path = resolve_element_path(name, index)
            if path and Path(path).exists():
                shutil.copy2(Path(path), output_styles_dir / Path(path).name)
                stats["output_styles"] += 1
                print(f"  ✓ output-style: {name}")
            else:
                print(f"  ✗ output-style: {name} — not found in index", file=sys.stderr)

    # Generate MCP config from index metadata
    if mcp_names:
        mcp_configs: dict[str, Any] = {}
        for name in mcp_names:
            path = resolve_element_path(name, index)
            if path and Path(path).exists():
                # Try to read actual MCP config from the source
                try:
                    with open(path, encoding="utf-8") as mf:
                        src_data = json.load(mf)
                    # Extract server config if it's an MCP descriptor
                    if "command" in src_data or "url" in src_data:
                        mcp_configs[name] = src_data
                        continue
                except (json.JSONDecodeError, OSError):
                    pass
            # Fallback: placeholder requiring manual config
            mcp_configs[name] = {
                "command": f"TODO: configure {name}",
                "args": [],
            }
        if mcp_configs:
            mcp_json = {"mcpServers": mcp_configs}
            with open(output_dir / ".mcp.json", "w") as f:
                json.dump(mcp_json, f, indent=2)
                f.write("\n")
            stats["mcp"] = len(mcp_names)
            print(
                f"  ✓ .mcp.json placeholder ({len(mcp_names)} MCP servers — configure manually)"
            )

    # Generate hooks.json — includes rules symlink hooks if rules exist
    has_rules = stats.get("rules", 0) > 0
    has_user_hooks = bool(hook_names)
    data_dir_spec = profile.get("data_dir") or {}
    has_data_dir = isinstance(data_dir_spec, dict) and any(
        data_dir_spec.get(k) for k in ("npm", "pip", "rust_cargo", "downloads")
    )
    if has_rules or has_user_hooks or has_data_dir:
        hooks_dir = output_dir / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        hooks_json: dict = {"hooks": {}}
        # Use a list so we can append multiple SessionStart entries (rules +
        # data_dir) without overwriting one with the other.
        session_start_entries: list[dict] = []

        # Rules symlink hooks: SessionStart installs, SessionEnd cleans up
        if has_rules:
            scripts_dir = output_dir / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            generate_rules_hook_scripts(plugin_name, scripts_dir)
            session_start_entries.append(
                {
                    "matcher": "startup|resume|clear|compact",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "bash ${CLAUDE_PLUGIN_ROOT}/scripts/install-rules.sh",
                            "timeout": 5000,
                        }
                    ],
                }
            )
            hooks_json["hooks"]["SessionEnd"] = [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "bash ${CLAUDE_PLUGIN_ROOT}/scripts/cleanup-rules.sh",
                            "timeout": 1500,
                        }
                    ],
                }
            ]
            print(
                "  ✓ scripts/install-rules.sh + cleanup-rules.sh (rule symlink hooks)"
            )

        # data_dir runtime deps: SessionStart lazily installs npm/pip/cargo
        # manifests + sha256-verified downloads into ${CLAUDE_PLUGIN_DATA}.
        # Skipped on plugin update unless the bundled manifest changed.
        if has_data_dir:
            scripts_dir = output_dir / "scripts"
            scripts_dir.mkdir(exist_ok=True)
            if generate_data_dir_hook_script(
                plugin_name, data_dir_spec, scripts_dir, output_dir
            ):
                session_start_entries.append(
                    {
                        "matcher": "startup|resume",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "bash ${CLAUDE_PLUGIN_ROOT}/scripts/install-data-deps.sh",
                                "timeout": 60000,
                            }
                        ],
                    }
                )
                print(
                    "  ✓ scripts/install-data-deps.sh (${CLAUDE_PLUGIN_DATA} runtime deps hook)"
                )

        if session_start_entries:
            hooks_json["hooks"]["SessionStart"] = session_start_entries

        if has_user_hooks:
            print(
                f"  ✓ hooks/hooks.json placeholder ({len(hook_names)} hooks — configure manually)"
            )

        with open(hooks_dir / "hooks.json", "w") as f:
            json.dump(hooks_json, f, indent=2)
            f.write("\n")
        print("  ✓ hooks/hooks.json")

    # Generate plugin.json
    # Use [description].text from profile if available, otherwise generate default
    desc_section = profile.get("description", {})
    description = (
        desc_section.get("text", "").strip()
        or f"Plugin for {agent_name} agent — auto-generated from .agent.toml profile"
    )
    manifest = generate_plugin_json(plugin_name, agent_name, description, profile)
    with open(output_dir / ".claude-plugin" / "plugin.json", "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print("  ✓ .claude-plugin/plugin.json")

    # Copy the .agent.toml itself for reference
    shutil.copy2(profile_path, output_dir / profile_path.name)
    print(f"  ✓ {profile_path.name} (profile reference)")

    # Generate README
    readme = generate_readme(plugin_name, agent_name, description, profile, stats)
    with open(output_dir / "README.md", "w") as f:
        f.write(readme)
    print("  ✓ README.md")

    # Summary
    total = sum(stats.values())
    print(f"\n{'=' * 50}")
    print(f"Plugin '{plugin_name}' created at: {output_dir}")
    print(
        f"  Skills: {stats['skills']}, Agents: {stats['agents']}, Commands: {stats['commands']}, Rules: {stats['rules']}, MCP: {stats['mcp']}"
    )
    print(f"  Total elements copied: {total}")
    print(f"\nInstall with: claude plugin install {output_dir}")
    print(f"Test with:    claude --plugin-dir {output_dir}")


if __name__ == "__main__":
    main()
