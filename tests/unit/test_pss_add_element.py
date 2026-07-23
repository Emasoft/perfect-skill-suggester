"""Tests for scripts/pss_add_element.py — adding elements to an existing plugin.

The script mutates someone else's plugin directory, so the duplicate gate is the
part that matters: it is the only thing standing between "add this agent" and
silently overwriting an agent that is already there. And `add_hook` MERGES into
an existing hooks.json rather than replacing it — a merge that drops the
existing events would disable every other hook in the plugin.

Everything here runs against real files in tmp_path, including a full CLI round
trip through the real argparse dispatch. Only `validate_plugin` (a network uvx
fetch of CPV) is out of reach and is not exercised.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
ADD_ELEMENT = SCRIPTS_DIR / "pss_add_element.py"


def _load_module(name: str, path: Path):
    """Load a script module by path so the test does not depend on PYTHONPATH."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def add_el():
    """Load pss_add_element.py without running its CLI."""
    return _load_module("pss_add_element_under_test", ADD_ELEMENT)


def _make_plugin(tmp_path: Path) -> Path:
    """Create a minimal but real plugin directory the script will accept."""
    plugin = tmp_path / "target-plugin"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "target-plugin", "version": "0.1.0"}), encoding="utf-8"
    )
    return plugin


def test_element_name_comes_from_frontmatter_before_the_filename(
    add_el, tmp_path: Path
) -> None:
    """A renamed file must still be recognised by its declared name, and vice versa."""
    agent = tmp_path / "file-name-differs.md"
    agent.write_text('---\nname: "real-agent"\ndescription: x\n---\n\nbody\n', encoding="utf-8")
    assert add_el.extract_element_name(agent, "agent") == "real-agent"

    # No frontmatter at all → fall back to the stem, never an empty name.
    plain = tmp_path / "plain-agent.md"
    plain.write_text("no frontmatter here\n", encoding="utf-8")
    assert add_el.extract_element_name(plain, "agent") == "plain-agent"

    # A skill is named by its SKILL.md frontmatter, addressed via the directory.
    skill_dir = tmp_path / "dir-name-differs"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: real-skill\n---\n", encoding="utf-8")
    assert add_el.extract_element_name(skill_dir, "skill") == "real-skill"
    assert add_el.extract_element_name(skill_dir / "SKILL.md", "skill") == "real-skill"

    # MCP/LSP names live in the JSON body.
    mcp = tmp_path / "server.json"
    mcp.write_text(json.dumps({"name": "codegraph", "command": "cg"}), encoding="utf-8")
    assert add_el.extract_element_name(mcp, "mcp-server") == "codegraph"


def test_duplicate_gate_catches_both_the_declared_name_and_the_filename(
    add_el, tmp_path: Path
) -> None:
    """An agent collides on frontmatter name OR on the file it would be written to."""
    plugin = _make_plugin(tmp_path)
    agents = plugin / "agents"
    agents.mkdir()
    (agents / "existing.md").write_text("---\nname: reviewer\n---\n", encoding="utf-8")

    # Same declared name, different filename.
    assert "already exists" in (add_el.check_agent_duplicate(plugin, "reviewer") or "")
    # Same filename, different declared name — add_agent writes by filename, so
    # this would overwrite the existing file.
    incoming = tmp_path / "existing.md"
    incoming.write_text("---\nname: different\n---\n", encoding="utf-8")
    assert "already exists" in (add_el.check_agent_duplicate(plugin, "different", incoming) or "")
    # A genuinely new agent is not blocked.
    fresh = tmp_path / "brand-new.md"
    fresh.write_text("---\nname: brand-new\n---\n", encoding="utf-8")
    assert add_el.check_agent_duplicate(plugin, "brand-new", fresh) is None


def test_hook_merge_preserves_existing_events_and_flags_a_duplicate_command(
    add_el, tmp_path: Path
) -> None:
    """Merging adds to hooks.json without dropping what was already registered."""
    plugin = _make_plugin(tmp_path)
    hooks_file = plugin / "hooks" / "hooks.json"
    hooks_file.parent.mkdir(parents=True)
    hooks_file.write_text(
        json.dumps({"hooks": {"UserPromptSubmit": [
            {"hooks": [{"type": "command", "command": "existing-hook.py"}]}]}}),
        encoding="utf-8",
    )

    incoming = tmp_path / "new-hooks.json"
    incoming.write_text(
        json.dumps({"hooks": {
            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "new-hook.py"}]}],
            "SessionStart": [{"hooks": [{"type": "command", "command": "start.py"}]}],
        }}),
        encoding="utf-8",
    )

    assert add_el.check_hook_incompatibility(plugin, incoming) is None
    assert add_el.add_hook(plugin, incoming, dry_run=False) is True

    merged = json.loads(hooks_file.read_text(encoding="utf-8"))
    commands = [h["command"] for g in merged["hooks"]["UserPromptSubmit"] for h in g["hooks"]]
    assert commands == ["existing-hook.py", "new-hook.py"], "merge dropped an existing hook"
    assert "SessionStart" in merged["hooks"]

    # Re-adding the same file is now a duplicate-command conflict.
    conflict = add_el.check_hook_incompatibility(plugin, incoming)
    assert conflict is not None and "already registered" in conflict


def test_cli_adds_an_agent_once_and_then_refuses_the_duplicate(tmp_path: Path) -> None:
    """Real CLI round trip: first add exits 0 and copies; the second exits 1 untouched."""
    plugin = _make_plugin(tmp_path)
    source = tmp_path / "rust-reviewer.md"
    source.write_text("---\nname: rust-reviewer\n---\n\nReviews Rust.\n", encoding="utf-8")

    def run(*extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ADD_ELEMENT), "--plugin", str(plugin),
             "--type", "agent", "--source", str(source), *extra],
            capture_output=True, text=True, timeout=60,
        )

    dry = run("--dry-run")
    assert dry.returncode == 0
    assert not (plugin / "agents").exists(), "--dry-run wrote to disk"

    first = run()
    assert first.returncode == 0, first.stderr
    copied = plugin / "agents" / "rust-reviewer.md"
    assert copied.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")

    second = run()
    assert second.returncode == 1
    assert "Duplicate/incompatibility" in second.stderr

    # --force overrides the gate (documented escape hatch).
    forced = run("--force")
    assert forced.returncode == 0, forced.stderr
