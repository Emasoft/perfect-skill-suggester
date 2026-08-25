"""Regression test: a UTF-8 BOM'd SKILL.md must discover cleanly end-to-end.

`_safe_read_text` decodes as plain "utf-8" (not "utf-8-sig"), so a BOM'd file
used to return text starting with U+FEFF + "---". `parse_frontmatter()`
stripped the BOM but only in its own local rebind, so `_extract_body_preview`
and `extract_use_context` (both called with the SAME raw `content` string,
not `parse_frontmatter`'s output) still saw the BOM and their bare
`content.startswith("---")` check failed -- the frontmatter block leaked into
the body preview and `extract_use_context` never found the "When to use"
section. Fixed by stripping the BOM once, in `_safe_read_text` itself.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_BOM = b"\xef\xbb\xbf"


def _load_discover():
    spec = importlib.util.spec_from_file_location("pss_discover", _SCRIPTS / "pss_discover.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_bom_skill(tmp_path: Path) -> Path:
    skill_dir = tmp_path / "skills" / "bom-skill"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    body = (
        "---\n"
        "name: bom-skill\n"
        "description: A skill whose SKILL.md starts with a UTF-8 BOM.\n"
        "---\n\n"
        "## When to use\n"
        "Use this skill when testing BOM handling in the discovery pipeline.\n"
    )
    skill_md.write_bytes(_BOM + body.encode("utf-8"))
    return tmp_path / "skills"


def test_bom_skill_discovered_via_real_pipeline(tmp_path: Path) -> None:
    """discover_elements() on a BOM'd SKILL.md parses name/description cleanly."""
    discover = _load_discover()
    skills_dir = _write_bom_skill(tmp_path)

    elements = discover.discover_elements([("user", "skill", skills_dir)])

    assert len(elements) == 1
    entry = elements[0]
    assert entry["name"] == "bom-skill"
    assert entry["description"] == "A skill whose SKILL.md starts with a UTF-8 BOM."


def test_bom_skill_body_preview_excludes_frontmatter(tmp_path: Path) -> None:
    """The discovered body preview must not contain the raw frontmatter block."""
    discover = _load_discover()
    skills_dir = _write_bom_skill(tmp_path)

    elements = discover.discover_elements([("user", "skill", skills_dir)])

    preview = elements[0]["preview"]
    assert "name: bom-skill" not in preview
    assert "description:" not in preview
    assert "When to use" in preview


def test_bom_skill_use_context_finds_heading_section(tmp_path: Path) -> None:
    """extract_use_context() must find the 'When to use' section past the BOM."""
    discover = _load_discover()
    skills_dir = _write_bom_skill(tmp_path)

    elements = discover.discover_elements([("user", "skill", skills_dir)])

    assert "testing BOM handling" in elements[0]["use_context"]
