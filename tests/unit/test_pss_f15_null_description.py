"""F15 (TRDD-1Z8SGQ7N): a null `description:` frontmatter value must not crash
the whole discovery run.

`frontmatter.get("description", "")[:200]` looks safe, but the `""` default
applies ONLY when the key is ABSENT. A YAML `description:` with no value parses
to None, `.get` returns None (the key is present), and `None[:200]` raises
`TypeError: 'NoneType' object is not subscriptable`. The exception is uncaught,
so a SINGLE third-party skill/agent/command with an empty description aborts the
entire `pss_discover` run — a total indexing outage from one bad file.

Two crash sites (post-F13 line numbers): the dedicated skill branch
(discover_elements ~L1929) and the generic .md branch (~L2010). The rule branch
is already guarded (`if element_type == "rule" and not frontmatter.get(...)`
routes null-description rules to paragraph extraction), so only non-rule
elements reach the vulnerable slice.

Fix: `(frontmatter.get("description") or "")[:200]` at both sites — a null value
degrades to an empty description, exactly as an absent key already does.

Conventions follow tests/unit/test_pss_f13_scan_error_routing.py: call the real
discover_elements with (scope, element_type, dir) location tuples; no mocks.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pss_discover  # noqa: E402


def test_skill_with_null_description_does_not_crash(tmp_path: Path) -> None:
    """REGRESSION: a SKILL.md whose `description:` is null must not abort the
    scan; the skill is emitted with an empty description. Crashes on the
    unfixed skill branch (~L1929)."""
    skills = tmp_path / "skills"
    (skills / "nulldesc").mkdir(parents=True)
    (skills / "nulldesc" / "SKILL.md").write_text(
        "---\nname: nulldesc\ndescription:\n---\n\nBody.\n", encoding="utf-8"
    )
    # A healthy sibling proves the loop survives the bad file rather than the
    # bad file simply being absent from an otherwise-empty scan.
    (skills / "healthy").mkdir()
    (skills / "healthy" / "SKILL.md").write_text(
        "---\nname: healthy\ndescription: fine\n---\n\nBody.\n", encoding="utf-8"
    )

    elements = pss_discover.discover_elements([("user", "skill", skills)])

    by_name = {e["name"]: e for e in elements}
    assert "nulldesc" in by_name, "null-description skill must still be emitted"
    assert by_name["nulldesc"]["description"] == "", (
        "a null description degrades to empty, like an absent key"
    )
    assert "healthy" in by_name, "one bad file must not abort the directory"
    assert by_name["healthy"]["description"] == "fine"


def test_command_with_null_description_does_not_crash(tmp_path: Path) -> None:
    """REGRESSION: a command .md whose `description:` is null must not abort the
    scan. Crashes on the unfixed generic .md branch (~L2010) — the site the rule
    guard does NOT cover for non-rule elements."""
    cmds = tmp_path / "commands"
    cmds.mkdir()
    (cmds / "nulldesc.md").write_text(
        "---\nname: nulldesc\ndescription:\n---\n\nBody.\n", encoding="utf-8"
    )
    (cmds / "healthy.md").write_text(
        "---\nname: healthy\ndescription: fine\n---\n\nBody.\n", encoding="utf-8"
    )

    elements = pss_discover.discover_elements([("user", "command", cmds)])

    by_name = {e["name"]: e for e in elements}
    assert "nulldesc" in by_name, "null-description command must still be emitted"
    assert by_name["nulldesc"]["description"] == ""
    assert "healthy" in by_name, "one bad file must not abort the directory"
