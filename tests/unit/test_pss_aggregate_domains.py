"""Tests for scripts/pss_aggregate_domains.py — domain-gate normalization.

The registry is what lets the suggester compare a skill's `domain_gates` against
domains inferred from a prompt. If two skills spell the same gate differently
(`target_language` vs `lang_target`) and the normalizer does not fold them into
one canonical name, they become two unrelated domains and each skill only ever
matches half the corpus. These tests pin the folding rules and drive the real
CLI end-to-end on a fixture index (no mocks — the file I/O and the exit codes
are part of what publish/reindex depends on).
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
AGGREGATOR = SCRIPTS_DIR / "pss_aggregate_domains.py"


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
def agg():
    """Load pss_aggregate_domains.py without running its CLI."""
    return _load_module("pss_aggregate_domains_under_test", AGGREGATOR)


def test_gate_names_fold_to_one_canonical_spelling(agg) -> None:
    """Word order, abbreviations, and case all collapse onto the same domain name."""
    # Order-independent: the canonical ordering table wins over alphabetical.
    assert agg.normalize_gate_name("target_language") == "target_language"
    assert agg.normalize_gate_name("language_target") == "target_language"
    # Abbreviations expand first, then the ordering table applies.
    assert agg.normalize_gate_name("tgt_lang") == "target_language"
    assert agg.normalize_gate_name("lang_input") == "input_language"
    # A single-token abbreviation that expands to two tokens still normalizes.
    assert agg.normalize_gate_name("os") == "operating_system"
    assert agg.normalize_gate_name("db") == "database"
    assert agg.normalize_gate_name("  Programming_Language ") == "programming_language"
    # Unknown token sets fall back to alphabetical, which is still deterministic.
    assert agg.normalize_gate_name("my_custom_gate") == "custom_gate_my"


def test_collect_gathers_aliases_across_skills_and_index_key_formats(agg) -> None:
    """Differently-spelled gates from different skills land under one canonical key."""
    index = {
        "skills": {
            # New source::name key format, name present in the entry.
            "user::alpha": {
                "name": "alpha",
                "domain_gates": {"target_language": ["python", "rust"]},
            },
            # Legacy name-only key, no `name` field — the key is the fallback.
            "beta": {"domain_gates": {"lang_target": ["python", "GENERIC"]}},
            # Malformed entries must be skipped, not crash the aggregation.
            "gamma": {"domain_gates": {"target_language": "not-a-list"}},
            "delta": "not-a-dict",
            "epsilon": {"domain_gates": None},
        }
    }

    collected = agg.collect_domain_gates(index)

    assert set(collected) == {"target_language"}
    entries = collected["target_language"]
    assert {skill for skill, _, _ in entries} == {"alpha", "beta"}
    assert {original for _, original, _ in entries} == {"target_language", "lang_target"}


def test_registry_lists_generic_first_and_dedups_keywords_case_insensitively(agg) -> None:
    """`generic` is hoisted to the front and keyword casing is folded before dedup."""
    index = {
        "skills": {
            "a": {"name": "a", "domain_gates": {"target_language": ["Python", "rust"]}},
            "b": {"name": "b", "domain_gates": {"lang_target": ["python", "GENERIC"]}},
        }
    }

    registry = agg.build_registry(index, Path("/tmp/skill-index.json"))
    domain = registry["domains"]["target_language"]

    assert registry["domain_count"] == 1
    assert domain["example_keywords"] == ["generic", "python", "rust"]
    assert domain["has_generic"] is True
    assert domain["aliases"] == ["lang_target", "target_language"]
    assert domain["skill_count"] == 2 and domain["skills"] == ["a", "b"]


def test_cli_writes_a_registry_and_fails_loudly_on_a_missing_index(tmp_path: Path) -> None:
    """The real script exits 0 + writes JSON, and exits 1 when the index is absent."""
    index_path = tmp_path / "skill-index.json"
    index_path.write_text(
        json.dumps({"skills": {"a": {"name": "a", "domain_gates": {"tgt_lang": ["rust"]}}}}),
        encoding="utf-8",
    )
    out_path = tmp_path / "nested" / "domain-registry.json"

    ok = subprocess.run(
        [sys.executable, str(AGGREGATOR), "--index", str(index_path),
         "--output", str(out_path), "--json"],
        capture_output=True, text=True, timeout=60,
    )
    assert ok.returncode == 0, ok.stderr
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["domains"]["target_language"]["example_keywords"] == ["rust"]
    assert json.loads(ok.stdout)["domain_count"] == 1

    missing = subprocess.run(
        [sys.executable, str(AGGREGATOR), "--index", str(tmp_path / "nope.json"),
         "--output", str(out_path)],
        capture_output=True, text=True, timeout=60,
    )
    assert missing.returncode == 1
    assert "not found" in missing.stderr
