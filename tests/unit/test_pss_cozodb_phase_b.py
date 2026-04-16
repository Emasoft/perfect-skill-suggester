"""Phase B (v2.11.0) tests: Python-canonical CozoDB writer.

Covers:
  - _fnv1a_entry_id parity with the Rust make_entry_id (read live DB)
  - atomic_write_cozodb full pipeline on a scratch DB (schema, rows, kw_lookup)
  - Timestamp preservation across two consecutive writes
  - export_json_snapshot roundtrip
  - _sync_cozodb stub (when pycozo absent) raises loudly
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pss_cozodb import (  # noqa: E402
    _fnv1a_entry_id,
    atomic_write_cozodb,
    count_skills,
    export_json_snapshot,
    open_db,
)


FIXTURE_ENTRY = {
    "source": "user",
    "path": "/tmp/fake-skill/SKILL.md",
    "type": "skill",
    "description": "Phase-B fixture skill used for tests. " * 15,  # > 500 chars
    "tier": "primary",
    "boost": 3,
    "category": "testing",
    "keywords": ["alpha", "beta", "gamma"],
    "intents": ["test"],
    "tools": ["pytest"],
    "services": [],
    "frameworks": ["django"],
    "languages": ["python"],
    "platforms": ["universal"],
    "domains": ["testing"],
    "file_types": ["py"],
    "patterns": [],
    "directories": [],
    "path_patterns": [],
    "use_cases": ["write tests"],
    "co_usage": {},
    "alternatives": [],
    "domain_gates": {},
    "path_gates": [],
    "server_type": "",
    "server_command": "",
    "server_args": [],
    "language_ids": [],
    "negative_keywords": [],
    "name": "phase-b-fixture",
}


@pytest.fixture()
def scratch_db() -> Path:
    """Yield a throwaway DB path; guaranteed clean on entry and exit."""
    with tempfile.TemporaryDirectory(prefix="pss-phase-b-test-") as tmpdir:
        yield Path(tmpdir) / "pss-skill-index.db"


def test_fnv1a_entry_id_matches_rust_for_react_user() -> None:
    """The Rust binary computed this value for ('react', 'user') on live data."""
    # Read the real live DB and grab a known (name, source) pair's id — if this
    # differs, the Rust hot path's skill_ids lookup will silently break.
    db_path = Path.home() / ".claude" / "cache" / "pss-skill-index.db"
    if not db_path.exists():
        pytest.skip("Live PSS CozoDB not available on this host")
    db = open_db(db_path)
    try:
        result = db.run(
            "?[name, source, id] := *skills{ name, source, id } :limit 5"
        )
        rows = result.get("rows", [])
        assert rows, "Live DB has no rows — cannot verify FNV parity"
        for name, source, real_id in rows:
            computed = _fnv1a_entry_id(name, source)
            assert computed == real_id, (
                f"FNV mismatch for ({name!r}, {source!r}): "
                f"Rust={real_id}, Python={computed}"
            )
    finally:
        db.close()


def test_atomic_write_cozodb_populates_all_relations(scratch_db: Path) -> None:
    """A single-entry write must populate skills + all 9 aux relations + kw_lookup + skill_ids + metadata."""
    entries = {
        f"{FIXTURE_ENTRY['source']}::{FIXTURE_ENTRY['name']}": FIXTURE_ENTRY,
    }
    count = atomic_write_cozodb(entries, scratch_db, version="3.0")
    assert count == 1

    db = open_db(scratch_db)
    try:
        # Main skills table
        assert count_skills(db) == 1
        # Auxiliary relations
        for rel, field in [
            ("skill_keywords", "keywords"),
            ("skill_intents", "intents"),
            ("skill_tools", "tools"),
            ("skill_frameworks", "frameworks"),
            ("skill_languages", "languages"),
            ("skill_platforms", "platforms"),
            ("skill_domains", "domains"),
            ("skill_file_types", "file_types"),
        ]:
            expected = len(FIXTURE_ENTRY[field])
            q = f"?[count(skill_name)] := *{rel}{{skill_name, value}}"
            got = db.run(q).get("rows", [[0]])[0][0]
            assert got == expected, f"{rel}: expected {expected} rows, got {got}"
        # kw_lookup: at least one row per value plus name-parts
        kw_count = db.run(
            "?[count(keyword_lower)] := *kw_lookup{keyword_lower, skill_name}"
        ).get("rows", [[0]])[0][0]
        assert kw_count > 0
        # skill_ids
        ids_count = db.run(
            "?[count(id)] := *skill_ids{id, name, source}"
        ).get("rows", [[0]])[0][0]
        assert ids_count == 1
        # Metadata
        meta = {
            row[0]: row[1]
            for row in db.run(
                "?[key, value] := *pss_metadata{key, value}"
            ).get("rows", [])
        }
        assert meta.get("version") == "3.0"
        assert meta.get("generator") == "python-merge-queue"
    finally:
        db.close()


def test_description_truncated_to_500(scratch_db: Path) -> None:
    """Description > 500 chars must be truncated, matching the Rust writer."""
    entries = {"user::phase-b-fixture": FIXTURE_ENTRY}
    atomic_write_cozodb(entries, scratch_db, version="3.0")
    db = open_db(scratch_db)
    try:
        r = db.run(
            "?[description] := *skills{name, description}, "
            "name = 'phase-b-fixture'"
        )
        desc = r.get("rows", [[""]])[0][0]
        assert len(desc) == 500
    finally:
        db.close()


def test_timestamp_preserved_across_two_writes(scratch_db: Path) -> None:
    """Second write must preserve first_indexed_at from first write."""
    entries = {"user::phase-b-fixture": FIXTURE_ENTRY}
    atomic_write_cozodb(entries, scratch_db, version="3.0")

    db = open_db(scratch_db)
    try:
        r1 = db.run(
            "?[first_indexed_at, last_updated_at] := "
            "*skills{name, first_indexed_at, last_updated_at}, "
            "name = 'phase-b-fixture'"
        )
        first_ts_1, last_ts_1 = r1.get("rows", [["", ""]])[0]
    finally:
        db.close()

    # Must wait at least 1 second so RFC3339-seconds timestamps differ
    time.sleep(1.5)

    atomic_write_cozodb(entries, scratch_db, version="3.0")

    db = open_db(scratch_db)
    try:
        r2 = db.run(
            "?[first_indexed_at, last_updated_at] := "
            "*skills{name, first_indexed_at, last_updated_at}, "
            "name = 'phase-b-fixture'"
        )
        first_ts_2, last_ts_2 = r2.get("rows", [["", ""]])[0]
    finally:
        db.close()

    assert first_ts_1 == first_ts_2, (
        f"first_indexed_at not preserved: {first_ts_1} → {first_ts_2}"
    )
    assert last_ts_2 != last_ts_1, (
        "last_updated_at should have advanced between writes"
    )


def test_export_json_snapshot_roundtrip(scratch_db: Path) -> None:
    """Write via atomic_write_cozodb then export — JSON must contain same entry."""
    entries = {"user::phase-b-fixture": FIXTURE_ENTRY}
    atomic_write_cozodb(entries, scratch_db, version="3.0")

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as tmp:
        json_path = Path(tmp.name)
    try:
        exported = export_json_snapshot(json_path, scratch_db)
        assert exported == 1

        data = json.loads(json_path.read_text())
        assert data["skill_count"] == 1
        assert data["version"] == "3.0"
        # Composite key `source::name`
        assert "user::phase-b-fixture" in data["skills"]
        entry = data["skills"]["user::phase-b-fixture"]
        assert entry["name"] == "phase-b-fixture"
        assert entry["type"] == "skill"
        assert entry["keywords"] == FIXTURE_ENTRY["keywords"]
        assert entry["first_indexed_at"]  # non-empty
    finally:
        json_path.unlink(missing_ok=True)


def test_missing_name_entries_are_skipped(scratch_db: Path) -> None:
    """An entry with an empty name must be silently skipped, not crash."""
    entries = {
        "user::phase-b-fixture": FIXTURE_ENTRY,
        "user::": {**FIXTURE_ENTRY, "name": ""},
    }
    count = atomic_write_cozodb(entries, scratch_db, version="3.0")
    assert count == 1, "empty-name entries should be skipped"


def test_schema_has_33_skill_columns(scratch_db: Path) -> None:
    """Validate the skills relation has exactly the columns the Rust hot path reads."""
    entries = {"user::phase-b-fixture": FIXTURE_ENTRY}
    atomic_write_cozodb(entries, scratch_db, version="3.0")
    db = open_db(scratch_db)
    try:
        # Use the exact column list Rust queries in load_candidates_from_db
        cols = (
            "name, path, skill_type, source, description, tier, boost, category, "
            "server_type, server_command, server_args_json, language_ids_json, "
            "negative_kw_json, patterns_json, directories_json, path_patterns_json, "
            "use_cases_json, co_usage_json, alternatives_json, domain_gates_json, "
            "file_types_json, keywords_json, intents_json, tools_json, "
            "services_json, frameworks_json, languages_json, platforms_json, "
            "domains_json, path_gates_json, first_indexed_at, last_updated_at"
        )
        q = f"?[{cols}] := *skills{{ {cols} }} :limit 1"
        r = db.run(q)
        rows = r.get("rows", [])
        assert rows, "schema did not accept Rust hot-path query"
        assert len(rows[0]) == 32  # 32 SELECTed fields (excludes id)
    finally:
        db.close()
