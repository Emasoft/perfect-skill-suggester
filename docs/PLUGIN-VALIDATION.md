# Plugin Validation Guide

This document describes how to write validation scripts for Claude Code plugins, using atlas-orchestrator and perfect-skill-suggester as examples.

---

## Why Every Plugin Needs Validation

1. **Manifest errors** cause silent plugin failures (won't load)
2. **Frontmatter errors** cause skills/agents/commands to not register
3. **Hook errors** cause silent failures or blocking errors at runtime
4. **Script errors** cause hook execution failures
5. **Version drift** causes inconsistent behavior across components

Validation scripts catch these issues BEFORE they reach users.

---

## Validation Architecture

### Severity Levels

| Level | Exit Code | Meaning |
|-------|-----------|---------|
| CRITICAL | 1 | Plugin will not load or function |
| MAJOR | 2 | Significant functionality broken |
| MINOR | 3 | Non-blocking issues, may affect UX |
| INFO | 0 | Suggestions, best practices |
| PASSED | 0 | Check completed successfully |

### Exit Code Convention

```python
def get_exit_code(results: list[ValidationResult]) -> int:
    """Determine exit code from validation results."""
    if any(r.level == "CRITICAL" for r in results):
        return 1
    if any(r.level == "MAJOR" for r in results):
        return 2
    if any(r.level == "MINOR" for r in results):
        return 3
    return 0
```

---

## Required Checks (All Plugins)

### 1. Plugin Manifest (`plugin.json`)

**Location**: `.claude-plugin/plugin.json`

**Required fields**:
- `name` (kebab-case, lowercase)
- `version` (semver format)
- `description`

**Validation rules**:
```python
def validate_manifest(plugin_root: Path) -> list[ValidationResult]:
    manifest_path = plugin_root / ".claude-plugin" / "plugin.json"

    # Check existence
    if not manifest_path.exists():
        return [ValidationResult("CRITICAL", "plugin.json not found")]

    # Parse JSON
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as e:
        return [ValidationResult("CRITICAL", f"Invalid JSON: {e}")]

    results = []

    # Required fields
    for field in ["name", "version", "description"]:
        if field not in manifest:
            results.append(ValidationResult("CRITICAL", f"Missing required field: {field}"))

    # Name format
    if "name" in manifest:
        name = manifest["name"]
        if name != name.lower() or " " in name:
            results.append(ValidationResult("MAJOR", "name must be kebab-case lowercase"))

    # Version format
    if "version" in manifest:
        if not re.match(r"^\d+\.\d+\.\d+", manifest["version"]):
            results.append(ValidationResult("MAJOR", "version must be semver format"))

    # agents must be array of .md files
    if "agents" in manifest:
        if not isinstance(manifest["agents"], list):
            results.append(ValidationResult("CRITICAL", "agents must be an array"))
        else:
            for agent in manifest["agents"]:
                if not agent.endswith(".md"):
                    results.append(ValidationResult("MAJOR", f"Agent must be .md file: {agent}"))
                if not agent.startswith("./"):
                    results.append(ValidationResult("MINOR", f"Agent path should start with ./: {agent}"))

    # Invalid fields
    invalid_fields = ["scripts", "templates"]
    for field in invalid_fields:
        if field in manifest:
            results.append(ValidationResult("MAJOR", f"Invalid manifest field: {field}"))

    return results
```

### 2. Directory Structure

**Required directories** (at plugin ROOT, not in .claude-plugin/):
- `commands/` if commands are defined
- `agents/` if agents are defined
- `skills/` if skills are defined
- `hooks/` if hooks are defined

**Validation**:
```python
def validate_structure(plugin_root: Path) -> list[ValidationResult]:
    results = []

    # .claude-plugin must exist
    if not (plugin_root / ".claude-plugin").is_dir():
        results.append(ValidationResult("CRITICAL", ".claude-plugin directory not found"))

    # Components must be at root, NOT in .claude-plugin
    for component in ["commands", "agents", "skills", "hooks"]:
        wrong_path = plugin_root / ".claude-plugin" / component
        if wrong_path.exists():
            results.append(ValidationResult("CRITICAL",
                f"{component}/ must be at plugin root, not in .claude-plugin/"))

    return results
```

### 3. Agent Definitions

**Location**: `agents/*.md`

**Required frontmatter fields**:
- `name` (matches filename without .md)
- `description` (when to use this agent)

**Validation**:
```python
def validate_agent(agent_path: Path) -> list[ValidationResult]:
    results = []
    content = agent_path.read_text()

    # Parse YAML frontmatter
    if not content.startswith("---"):
        results.append(ValidationResult("CRITICAL", f"No frontmatter in {agent_path.name}"))
        return results

    try:
        frontmatter = yaml.safe_load(content.split("---")[1])
    except yaml.YAMLError as e:
        results.append(ValidationResult("CRITICAL", f"Invalid YAML: {e}"))
        return results

    # Required fields
    if "name" not in frontmatter:
        results.append(ValidationResult("CRITICAL", "Missing 'name' in frontmatter"))
    if "description" not in frontmatter:
        results.append(ValidationResult("MAJOR", "Missing 'description' in frontmatter"))

    # Name must match filename
    expected_name = agent_path.stem
    if frontmatter.get("name") != expected_name:
        results.append(ValidationResult("MAJOR",
            f"Agent name '{frontmatter.get('name')}' doesn't match filename '{expected_name}'"))

    return results
```

### 4. Command Definitions

**Location**: `commands/*.md`

**Required frontmatter fields**:
- `name` (matches filename without .md)
- `description`

**Validation**: Same pattern as agents.

### 5. Skill Definitions

**Location**: `skills/<skill-name>/SKILL.md`

**Required frontmatter fields**:
- `name` (matches directory name)
- `description` (when to use this skill)

**Claude Code-specific fields** (optional but validated if present):
- `context`: valid value is `fork`
- `agent`: valid values depend on plugin (e.g., `api-coordinator`, `test-engineer`)
- `user-invocable`: valid values are `true` or `false`

**Validation**:
```python
def validate_skill(skill_dir: Path) -> list[ValidationResult]:
    results = []
    skill_md = skill_dir / "SKILL.md"

    if not skill_md.exists():
        results.append(ValidationResult("CRITICAL", f"SKILL.md not found in {skill_dir.name}"))
        return results

    content = skill_md.read_text()

    # Parse frontmatter
    if not content.startswith("---"):
        results.append(ValidationResult("CRITICAL", "No frontmatter in SKILL.md"))
        return results

    try:
        frontmatter = yaml.safe_load(content.split("---")[1])
    except yaml.YAMLError as e:
        results.append(ValidationResult("CRITICAL", f"Invalid YAML: {e}"))
        return results

    # Required fields
    if "name" not in frontmatter:
        results.append(ValidationResult("CRITICAL", "Missing 'name' in frontmatter"))
    if "description" not in frontmatter:
        results.append(ValidationResult("MAJOR", "Missing 'description' in frontmatter"))

    # Name must match directory
    if frontmatter.get("name") != skill_dir.name:
        results.append(ValidationResult("MAJOR",
            f"Skill name doesn't match directory: {frontmatter.get('name')} vs {skill_dir.name}"))

    # Claude Code-specific fields
    if "context" in frontmatter:
        if frontmatter["context"] != "fork":
            results.append(ValidationResult("MAJOR",
                f"Invalid context value: {frontmatter['context']} (must be 'fork')"))

    if "user-invocable" in frontmatter:
        if frontmatter["user-invocable"] not in [True, False, "true", "false"]:
            results.append(ValidationResult("MAJOR", "user-invocable must be true or false"))

    return results
```

### 6. Hook Configuration

**Location**: `hooks/hooks.json`

**Validation**:
```python
def validate_hooks(plugin_root: Path) -> list[ValidationResult]:
    hooks_path = plugin_root / "hooks" / "hooks.json"

    if not hooks_path.exists():
        return []  # Hooks are optional

    results = []

    try:
        hooks_config = json.loads(hooks_path.read_text())
    except json.JSONDecodeError as e:
        results.append(ValidationResult("CRITICAL", f"Invalid hooks.json: {e}"))
        return results

    if "hooks" not in hooks_config:
        results.append(ValidationResult("MAJOR", "Missing 'hooks' key in hooks.json"))
        return results

    valid_events = [
        "PreToolUse", "PostToolUse", "PostToolUseFailure",
        "PermissionRequest", "UserPromptSubmit", "Notification",
        "Stop", "SubagentStop", "SessionStart", "SessionEnd", "PreCompact"
    ]

    for event, handlers in hooks_config["hooks"].items():
        if event not in valid_events:
            results.append(ValidationResult("MAJOR", f"Invalid hook event: {event}"))

        # Validate script references
        for handler in handlers:
            if "hooks" in handler:
                for hook in handler["hooks"]:
                    if hook.get("type") == "command":
                        cmd = hook.get("command", "")
                        # Extract script path from command
                        if "${CLAUDE_PLUGIN_ROOT}" in cmd:
                            script = cmd.replace("${CLAUDE_PLUGIN_ROOT}/", "")
                            script_path = plugin_root / script
                            if not script_path.exists():
                                results.append(ValidationResult("CRITICAL",
                                    f"Hook script not found: {script}"))
                            elif not os.access(script_path, os.X_OK):
                                results.append(ValidationResult("MAJOR",
                                    f"Hook script not executable: {script}"))

    return results
```

### 7. Script Validation

**Python scripts**: Use `ruff` and `mypy`
**Bash scripts**: Use `shellcheck`

```python
def validate_scripts(plugin_root: Path) -> list[ValidationResult]:
    results = []
    scripts_dir = plugin_root / "scripts"

    if not scripts_dir.exists():
        return []

    # Python scripts
    py_files = list(scripts_dir.glob("*.py"))
    if py_files:
        # Ruff check
        result = subprocess.run(
            ["ruff", "check", "--select", "E,F,W"] + [str(f) for f in py_files],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            for line in result.stdout.strip().split("\n"):
                if line:
                    results.append(ValidationResult("MAJOR", f"Ruff: {line}"))

        # Mypy check
        result = subprocess.run(
            ["mypy", "--ignore-missing-imports"] + [str(f) for f in py_files],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            for line in result.stdout.strip().split("\n"):
                if line and not line.startswith("Success"):
                    results.append(ValidationResult("MINOR", f"Mypy: {line}"))

    # Bash scripts
    sh_files = list(scripts_dir.glob("*.sh"))
    for sh_file in sh_files:
        result = subprocess.run(
            ["shellcheck", str(sh_file)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            results.append(ValidationResult("MINOR", f"Shellcheck {sh_file.name}: issues found"))

    return results
```

### 8. Version Consistency

Check version is consistent across:
- `plugin.json`
- `package.json` (if exists)
- Any other version references

```python
def validate_version_consistency(plugin_root: Path) -> list[ValidationResult]:
    results = []
    versions = {}

    # plugin.json
    manifest = plugin_root / ".claude-plugin" / "plugin.json"
    if manifest.exists():
        data = json.loads(manifest.read_text())
        versions["plugin.json"] = data.get("version")

    # package.json
    package = plugin_root / "package.json"
    if package.exists():
        data = json.loads(package.read_text())
        versions["package.json"] = data.get("version")

    # Check consistency
    unique_versions = set(v for v in versions.values() if v)
    if len(unique_versions) > 1:
        results.append(ValidationResult("MINOR",
            f"Version mismatch: {versions}"))

    return results
```

---

## Plugin-Specific Checks

### Perfect Skill Suggester (PSS)

PSS has additional validation requirements:

1. **Schema files**:
   - `schemas/pss-categories.json` must exist and be valid
   - `schemas/pss-schema.json` must exist
   - `schemas/pss-skill-index-schema.json` must exist

2. **Binary files**:
   - `bin/pss-darwin-arm64` (macOS ARM)
   - `bin/pss-darwin-x86_64` (macOS Intel)
   - `bin/pss-linux-x86_64` (Linux x86_64)
   - `bin/pss-linux-arm64` (Linux ARM64)
   - `bin/pss-windows-x86_64.exe` (Windows)
   - `bin/pss-wasm32.wasm` (WebAssembly)
   - At least one native binary must exist

3. **Categories validation**:
   - All 16 predefined categories must be present
   - `co_usage_matrix` must reference valid categories only

4. **Command validation**:
   - `pss-reindex-skills` must exist
   - `pss-status` must exist
   - `pss-setup-agent` must exist

5. **Agent validation**:
   - `pss-agent-profiler.md` must exist in `agents/`

6. **Schema validation**:
   - `schemas/pss-skill-index-schema.json` must exist
   - `schemas/pss-agent-toml-schema.json` must exist
   - `schemas/pss-categories.json` must exist

See `scripts/validate_plugin.py` for implementation.

---

## Validation Script Template

```python
#!/usr/bin/env python3
"""Plugin validation script template."""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

@dataclass
class ValidationResult:
    level: Literal["CRITICAL", "MAJOR", "MINOR", "INFO", "PASSED"]
    message: str
    file: str | None = None
    line: int | None = None

def validate_plugin(plugin_root: Path) -> list[ValidationResult]:
    """Run all validation checks."""
    results = []

    # Add your validation calls here
    results.extend(validate_manifest(plugin_root))
    results.extend(validate_structure(plugin_root))
    results.extend(validate_hooks(plugin_root))
    results.extend(validate_scripts(plugin_root))
    # ... plugin-specific checks

    return results

def main():
    parser = argparse.ArgumentParser(description="Validate plugin")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    plugin_root = Path(__file__).parent.parent
    results = validate_plugin(plugin_root)

    # Output results
    if args.json:
        print(json.dumps([{
            "level": r.level,
            "message": r.message,
            "file": r.file,
            "line": r.line
        } for r in results], indent=2))
    else:
        for r in results:
            if r.level == "PASSED" and not args.verbose:
                continue
            print(f"[{r.level}] {r.message}")

    # Exit code
    if any(r.level == "CRITICAL" for r in results):
        sys.exit(1)
    if any(r.level == "MAJOR" for r in results):
        sys.exit(2)
    if any(r.level == "MINOR" for r in results):
        sys.exit(3)
    sys.exit(0)

if __name__ == "__main__":
    main()
```

---

## Running Validation

### During Development

```bash
# Validate after every change
uv run python scripts/validate_plugin.py . --verbose

# Verbose output
uv run python scripts/validate_plugin.py . --verbose

# JSON output for CI
uv run python scripts/validate_plugin.py . --json
```

### In CI/CD

```yaml
# .github/workflows/validate.yml
name: Validate Plugin
on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv run python scripts/validate_plugin.py . --json
```

---

## Common Validation Errors

| Error | Cause | Fix |
|-------|-------|-----|
| "plugin.json not found" | Missing manifest | Create `.claude-plugin/plugin.json` |
| "agents must be an array" | Wrong manifest format | Change `"agents": "./agents/"` to `"agents": ["./agents/my-agent.md"]` |
| "components in wrong location" | Structure error | Move `commands/`, `agents/`, etc. to plugin root |
| "Hook script not found" | Path error | Use `${CLAUDE_PLUGIN_ROOT}` in command paths |
| "Script not executable" | Permission error | Run `chmod +x scripts/*.sh` |
| "Invalid frontmatter" | YAML syntax | Check for proper indentation, quotes |
