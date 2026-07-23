"""Tests for scripts/pss_agent_benchmark.py — the scoring half of the benchmark.

The benchmark's number is only trustworthy if the extraction and scoring are:
  * capped at TYPE_LIMITS (an uncapped list inflates hits for free),
  * de-duplicated (the same skill in two tiers must not score twice),
  * tolerant of a partial/empty profile (the binary returns `{}` on failure, and
    a crash there would silently drop agents from the denominator).
Those are pure functions, so they are exercised directly with real profile
shapes. Running the actual Rust binary is out of scope here (it needs a built
index); the parts that do NOT need it are what these tests cover.
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
def bench():
    """Load pss_agent_benchmark.py without running its CLI."""
    return _load_module(
        "pss_agent_benchmark_under_test", SCRIPTS_DIR / "pss_agent_benchmark.py"
    )


def test_extraction_dedups_across_tiers_and_caps_at_the_type_limit(bench) -> None:
    """Skills flow primary→secondary→specialized, dropping repeats, capped at 5."""
    profile = {
        "skills": {
            "primary": [{"name": "rust"}, {"name": "testing"}],
            "secondary": [{"name": "testing"}, {"name": "python"}, {"name": "docker"}],
            "specialized": [{"name": "kubernetes"}, {"name": "terraform"}],
        },
        "complementary_agents": [{"name": f"agent-{i}"} for i in range(12)],
        "commands": [{"name": "c1"}, {"name": "c2"}],
        "rules": [{"name": "r1"}, {"name": "r2"}, {"name": "r3"}, {"name": "r4"}],
        "mcp": [{"name": "m1"}],
    }

    got = bench.extract_names_from_profile(profile)

    # Tier order preserved, 'testing' counted once, truncated at TYPE_LIMITS.
    assert got["skills"] == ["rust", "testing", "python", "docker", "kubernetes"]
    assert len(got["skills"]) == bench.TYPE_LIMITS["skills"]
    assert len(got["agents"]) == bench.TYPE_LIMITS["agents"] == 10
    assert got["rules"] == ["r1", "r2", "r3"]  # capped at 3
    assert got["commands"] == ["c1", "c2"]
    assert got["mcp"] == ["m1"]


def test_extraction_survives_an_empty_or_null_profile(bench) -> None:
    """A failed binary run yields `{}`; extraction must return empty lists, not raise."""
    empty = bench.extract_names_from_profile({})
    assert empty == {"skills": [], "agents": [], "commands": [], "rules": [], "mcp": []}

    # Explicit JSON nulls and bare-string items are both real shapes from the binary.
    partial = bench.extract_names_from_profile(
        {"skills": {"primary": None, "secondary": ["plain-string"]},
         "complementary_agents": None, "commands": [{"name": ""}], "rules": [], "mcp": None}
    )
    assert partial["skills"] == ["plain-string"]
    assert partial["agents"] == [] and partial["commands"] == []


def test_scoring_counts_only_suggestions_present_in_that_type_s_gold(bench) -> None:
    """A hit in the wrong type never scores — the per-type sets are independent."""
    suggested = {"skills": ["rust", "python"], "agents": ["rust"], "commands": [],
                 "rules": ["r1"], "mcp": []}
    gold = {"skills": ["rust", "docker"], "agents": ["reviewer"], "commands": ["c1"],
            "rules": ["r1", "r2"], "mcp": ["m1"]}

    hits = bench.score_agent(suggested, gold)

    assert hits == {"skills": 1, "agents": 0, "commands": 0, "rules": 1, "mcp": 0}
    assert set(hits) == set(bench.TYPE_LIMITS)


def test_saved_report_names_the_gold_items_that_were_missed(bench, tmp_path: Path) -> None:
    """The per-agent file records MISSED gold, which is what makes it diagnosable."""
    results = {
        "total_hits": {"skills": 1, "agents": 0, "commands": 0, "rules": 0, "mcp": 0},
        "total_max": {"skills": 2, "agents": 1, "commands": 0, "rules": 0, "mcp": 0},
        "combined_hits": 1,
        "combined_max": 3,
        "agent_count": 1,
        "per_agent": [
            {
                "id": 7,
                "name": "rust-reviewer",
                "hits": {"skills": 1, "agents": 0, "commands": 0, "rules": 0, "mcp": 0},
                "suggested": {"skills": ["rust"], "agents": [], "commands": [],
                              "rules": [], "mcp": []},
                "gold": {"skills": ["rust", "cargo"], "agents": ["reviewer"],
                         "commands": [], "rules": [], "mcp": []},
            }
        ],
    }
    out = tmp_path / "results.md"

    bench.save_per_agent_results(results, str(out))

    text = out.read_text(encoding="utf-8")
    assert "### A7 (rust-reviewer)" in text
    assert "combined  : 1/3" in text
    assert "MISSED:    ['cargo']" in text
    assert "MISSED:    ['reviewer']" in text
