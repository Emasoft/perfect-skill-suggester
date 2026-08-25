"""Tests that a UTF-8 BOM'd .md file is accepted by both frontmatter parsers.

CC 2.1.240 stopped silently dropping BOM'd skill/agent/command files, so PSS's
own parsers must stop rejecting them too: `pss_add_element.parse_frontmatter`
used to return {} (no name/description/tools indexed) and
`pss_validate_agent_md.parse_frontmatter` used to raise ValueError (str.strip()
does not remove U+FEFF). Both are fixed with an explicit BOM strip.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

BOM = b"\xef\xbb\xbf"
AGENT_MD = b"""---
name: bom-agent
description: A test agent whose file starts with a BOM.
---

Body text.
"""


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


def test_add_element_parses_frontmatter_from_bom_prefixed_file(tmp_path: Path) -> None:
    """pss_add_element.parse_frontmatter must not drop frontmatter behind a BOM."""
    add_el = _load_module("pss_add_element_bom_test", SCRIPTS_DIR / "pss_add_element.py")
    md_path = tmp_path / "bom-agent.md"
    md_path.write_bytes(BOM + AGENT_MD)

    result = add_el.parse_frontmatter(md_path)

    assert result.get("name") == "bom-agent"
    assert result.get("description") == "A test agent whose file starts with a BOM."


def test_validate_agent_md_parses_frontmatter_from_bom_prefixed_file() -> None:
    """pss_validate_agent_md.parse_frontmatter must not raise on a BOM'd file."""
    validator = _load_module(
        "pss_validate_agent_md_bom_test", SCRIPTS_DIR / "pss_validate_agent_md.py"
    )
    # Mirror Path.read_text(encoding="utf-8") (not "utf-8-sig"): the BOM bytes
    # decode to a literal U+FEFF character prepended to the text.
    text_with_bom = (BOM + AGENT_MD).decode("utf-8")
    assert text_with_bom[0] == chr(0xFEFF)

    fm = validator.parse_frontmatter(text_with_bom)

    assert fm.keys.get("name") == "bom-agent"
    assert fm.keys.get("description") == "A test agent whose file starts with a BOM."
