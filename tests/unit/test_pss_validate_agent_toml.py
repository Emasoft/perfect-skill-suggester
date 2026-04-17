"""Tests for pss_validate_agent_toml.py.

Covers:
  - `effort` enum accepts `low`, `medium`, `high`, `xhigh` (CC v2.1.111+ Opus 4.7)
  - `effort` enum rejects bogus values with an actionable message
  - `maxTurns` must be a positive integer
  - `disallowedTools` must be a list of strings
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _run_validator(toml_content: str, tmp_path: Path) -> tuple[int, str]:
    """Write a TOML fixture to a temp file and run the validator.

    The validator also checks that [agent].path exists on disk, so we create
    a sibling fake-agent.md file and point the TOML at it.

    Returns (exit_code, combined stdout+stderr) — the validator prints to both.
    """
    fake_agent = tmp_path / "fixture.md"
    fake_agent.write_text("# Fixture agent\n")
    toml_file = tmp_path / "fixture.agent.toml"
    toml_file.write_text(toml_content.replace("<AGENT_PATH>", str(fake_agent)))
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "pss_validate_agent_toml.py"), str(toml_file)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, result.stdout + result.stderr


MINIMAL_TOML = """
[agent]
name = "fixture"
path = "<AGENT_PATH>"
{extra}

[skills]
primary = ["testing"]
secondary = []
specialized = []
"""


class TestEffortEnum:
    """`[agent].effort` must be one of the CC-recognised values."""

    def test_low_accepted(self, tmp_path: Path) -> None:
        rc, _ = _run_validator(MINIMAL_TOML.format(extra='effort = "low"'), tmp_path)
        assert rc == 0, "effort='low' must pass validation"

    def test_medium_accepted(self, tmp_path: Path) -> None:
        rc, _ = _run_validator(MINIMAL_TOML.format(extra='effort = "medium"'), tmp_path)
        assert rc == 0, "effort='medium' must pass validation"

    def test_high_accepted(self, tmp_path: Path) -> None:
        rc, _ = _run_validator(MINIMAL_TOML.format(extra='effort = "high"'), tmp_path)
        assert rc == 0, "effort='high' must pass validation"

    def test_xhigh_accepted(self, tmp_path: Path) -> None:
        """CC v2.1.111+ Opus 4.7 extension — other models fall back to 'high'."""
        rc, _ = _run_validator(MINIMAL_TOML.format(extra='effort = "xhigh"'), tmp_path)
        assert rc == 0, "effort='xhigh' must pass validation (CC v2.1.111+)"

    def test_bogus_value_rejected(self, tmp_path: Path) -> None:
        rc, out = _run_validator(
            MINIMAL_TOML.format(extra='effort = "ludicrous"'), tmp_path
        )
        assert rc != 0, "bogus effort value must fail"
        assert "effort" in out
        # Message should list the allowed values for actionable guidance
        assert "low" in out and "medium" in out and "high" in out
        assert "xhigh" in out, "error message must mention xhigh"

    def test_non_string_rejected(self, tmp_path: Path) -> None:
        rc, out = _run_validator(MINIMAL_TOML.format(extra="effort = 42"), tmp_path)
        assert rc != 0, "non-string effort value must fail"
        assert "effort" in out


class TestMaxTurns:
    def test_positive_int_accepted(self, tmp_path: Path) -> None:
        rc, _ = _run_validator(MINIMAL_TOML.format(extra="maxTurns = 40"), tmp_path)
        assert rc == 0

    def test_zero_rejected(self, tmp_path: Path) -> None:
        rc, out = _run_validator(MINIMAL_TOML.format(extra="maxTurns = 0"), tmp_path)
        assert rc != 0
        assert "maxTurns" in out


class TestDisallowedTools:
    def test_list_of_strings_accepted(self, tmp_path: Path) -> None:
        rc, _ = _run_validator(
            MINIMAL_TOML.format(extra='disallowedTools = ["WebFetch", "WebSearch"]'),
            tmp_path,
        )
        assert rc == 0

    def test_empty_list_accepted(self, tmp_path: Path) -> None:
        rc, _ = _run_validator(
            MINIMAL_TOML.format(extra="disallowedTools = []"), tmp_path
        )
        assert rc == 0
