"""Tests for scripts/pss_qualitative_benchmark.py — eval-task generation.

`write_eval_task` builds a filename out of an agent name that comes from a JSONL
fixture, so the sanitizer is a real path-traversal boundary: an unsanitized
`../../x` would write the eval task outside the report directory. `format_suggestions`
is what the evaluating subagent actually reads — if a section silently vanishes
(or a float score raises on a non-numeric value) the human grade is made against
incomplete data. Both are pure and are driven directly here; the PSS binary
invocation needs a built index and is not exercised.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


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
def qual():
    """Load pss_qualitative_benchmark.py without running its CLI."""
    return _load_module(
        "pss_qualitative_benchmark_under_test",
        SCRIPTS_DIR / "pss_qualitative_benchmark.py",
    )


def test_every_populated_section_reaches_the_evaluator(qual) -> None:
    """Skills tiers, agents, commands, rules and MCP each render with name + score."""
    profile = {
        "skills": {
            "primary": [{"name": "rust", "score": 0.9123, "confidence": "high",
                         "description": "Rust systems programming"}],
            "secondary": [],
            "specialized": [{"name": "wasm", "score": 0.4, "confidence": "low"}],
        },
        "complementary_agents": [{"name": "reviewer", "score": 0.7, "confidence": "medium"}],
        "commands": [{"name": "/build", "score": 0.5, "description": "build it"}],
        "rules": [{"name": "commit-discipline", "description": "commit often"}],
        "mcp": [{"name": "codegraph", "description": "code graph"}],
    }

    text = qual.format_suggestions(profile)

    assert "### Skills (primary) — 1 items" in text
    assert "**rust** (score: 0.912, high)" in text
    assert "_Rust systems programming_" in text
    assert "### Skills (specialized) — 1 items" in text
    # An empty tier must not emit a heading — it would read as "PSS found nothing"
    # rather than "this tier was not populated".
    assert "(secondary)" not in text
    assert "**reviewer** (score: 0.700, medium)" in text
    assert "**/build** (score: 0.500) — build it" in text
    assert "**commit-discipline** — commit often" in text
    assert "**codegraph** — code graph" in text


def test_missing_fields_and_empty_profile_do_not_break_rendering(qual) -> None:
    """A `{}` profile (failed binary run) renders as empty, and null fields fall back."""
    assert qual.format_suggestions({}) == ""

    text = qual.format_suggestions(
        {"skills": {"primary": [{"name": None, "score": None,
                                 "description": None, "confidence": None}]}}
    )
    assert "**?** (score: 0.000, ?)" in text


def test_eval_filename_is_sanitized_against_path_traversal(qual, tmp_path: Path) -> None:
    """A hostile agent name cannot escape the output dir or plant a nested path."""
    hostile = "../../../etc/passwd"

    written = qual.write_eval_task(tmp_path, 3, hostile, "definition", "suggestions")

    assert written.parent == tmp_path, "eval task escaped the output directory"
    assert written.name == "eval-A003-.._.._.._etc_passwd.md"
    assert written.exists()


def test_eval_task_carries_instructions_definition_and_suggestions(qual, tmp_path: Path) -> None:
    """The task file is self-contained: a subagent needs no other input to grade it."""
    written = qual.write_eval_task(
        tmp_path, 12, "rust-reviewer", "AGENT-DEFINITION-BODY", "\n### Skills (primary) — 1 items"
    )

    text = written.read_text(encoding="utf-8")
    assert written.name == "eval-A012-rust-reviewer.md"
    assert text.startswith("# Evaluation Task: A12 — rust-reviewer")
    assert qual.EVAL_INSTRUCTIONS in text
    assert "AGENT-DEFINITION-BODY" in text
    assert "### Skills (primary) — 1 items" in text
    assert "## Your Evaluation" in text
