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
    _KNOWN_SCHEMA_RELATIONS,
    _create_db_schema,
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
            ("skill_services", "services"),
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


def test_atomic_write_uses_staging_and_write_lock(scratch_db: Path) -> None:
    """Verify the staging-file + atomic-rename pattern (v3.5.0+):

    - Writer creates `<db>.write.lock` (not the legacy `<db>.lock`)
    - The staging file `<db>.staging` is wiped after a successful rename
    - The final live DB file exists at the original `db_path`
    """
    entries = {"user::phase-b-fixture": FIXTURE_ENTRY}
    count = atomic_write_cozodb(entries, scratch_db, version="3.0")
    assert count == 1

    write_lock = scratch_db.with_name(scratch_db.name + ".write.lock")
    staging = scratch_db.with_name(scratch_db.name + ".staging")
    legacy_lock = scratch_db.with_name(scratch_db.name + ".lock")

    assert scratch_db.exists(), "live DB must exist after atomic rename"
    assert write_lock.exists(), "writer must leave its lock file behind"
    assert not staging.exists(), "staging file must be removed after rename"
    assert not legacy_lock.exists(), (
        "legacy .lock should NOT be touched by the new writer pathway"
    )


def test_concurrent_reader_not_blocked_by_writer_lock(scratch_db: Path) -> None:
    """The whole point of the staging-file design: a reader can open the
    live DB even while a writer holds LOCK_EX on the *write* lock. Models
    the production race where the hook fires during a `/pss-reindex-skills`.
    """
    import fcntl
    import threading

    # Seed the live DB so the reader has something to read.
    atomic_write_cozodb({"user::phase-b-fixture": FIXTURE_ENTRY}, scratch_db, version="3.0")

    write_lock = scratch_db.with_name(scratch_db.name + ".write.lock")
    writer_held = threading.Event()
    writer_release = threading.Event()

    def hold_writer_lock() -> None:
        with open(write_lock, "w") as fd:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
            writer_held.set()
            writer_release.wait(timeout=5)

    t = threading.Thread(target=hold_writer_lock, daemon=True)
    t.start()
    writer_held.wait(timeout=2)

    # Reader path: opens the live DB without taking the write lock. Must
    # not block on the writer.
    t0 = time.monotonic()
    db = open_db(scratch_db)
    try:
        rows = db.run("?[name] := *skills{ name } :limit 1").get("rows", [])
        assert rows, "reader must see at least the seed row"
    finally:
        db.close()
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0, f"reader was blocked for {elapsed:.2f}s — should be immediate"

    writer_release.set()
    t.join(timeout=2)


def _seed_temporal_relations(db_path: Path) -> None:
    """Create the Rust temporal-index tables directly on a live DB, mirroring
    temporal.rs::TEMPORAL_DDL (events / elements_state / scan_runs), and
    insert one row each. Used to prove atomic_write_cozodb preserves them.
    """
    db = open_db(db_path)
    try:
        db.run(
            """
            {:create events {
                event_id: String =>
                observed_at: String,
                scan_id: String,
                event_type: String,
                element_type: String,
                element_name: String,
                element_id: String,
                scope: String,
                scope_path: String,
                source: String,
                path: String,
                content_hash: String,
                file_size: Int default -1,
                token_count: Int default -1,
                enabled: Bool default true,
                override_status: String default "none",
                diff_json: String default "{}",
                snapshot_ref: String default "",
            }}
            """
        )
        db.run(
            """
            {:create elements_state {
                element_id: String =>
                last_event_id: String,
                current_path: String,
                current_hash: String,
                current_size: Int default -1,
                current_token_count: Int default -1,
                enabled: Bool default true,
                override_status: String default "none",
                installed_at: String,
                last_changed_at: String,
                exists: Bool default true,
            }}
            """
        )
        db.run(
            """
            {:create scan_runs {
                scan_id: String =>
                started_at: String,
                finished_at: String,
                scope_paths_json: String,
                events_emitted: Int default 0,
                rust_binary_version: String,
                pss_version: String,
            }}
            """
        )
        db.run(
            """
            ?[event_id, observed_at, scan_id, event_type, element_type, element_name,
              element_id, scope, scope_path, source, path, content_hash, file_size,
              token_count, enabled, override_status, diff_json, snapshot_ref] <- [[
              "01EVT0000000000000000001", "2026-01-01T00:00:00+00:00", "scan-1",
              "installed", "skill", "phase-b-fixture", "abc123fnv", "user", "/",
              "user", "/tmp/fake-skill/SKILL.md", "deadbeef", 42, 7, true, "none",
              "{}", ""
            ]]
            :put events { event_id => observed_at, scan_id, event_type, element_type,
              element_name, element_id, scope, scope_path, source, path,
              content_hash, file_size, token_count, enabled, override_status,
              diff_json, snapshot_ref }
            """
        )
        db.run(
            """
            ?[element_id, last_event_id, current_path, current_hash, current_size,
              current_token_count, enabled, override_status, installed_at,
              last_changed_at, exists] <- [[
              "abc123fnv", "01EVT0000000000000000001", "/tmp/fake-skill/SKILL.md",
              "deadbeef", 42, 7, true, "none", "2026-01-01T00:00:00+00:00",
              "2026-01-01T00:00:00+00:00", true
            ]]
            :put elements_state { element_id => last_event_id, current_path,
              current_hash, current_size, current_token_count, enabled,
              override_status, installed_at, last_changed_at, exists }
            """
        )
        db.run(
            """
            ?[scan_id, started_at, finished_at, scope_paths_json, events_emitted,
              rust_binary_version, pss_version] <- [[
              "scan-1", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:01+00:00",
              "[]", 1, "3.10.0", "3.10.0"
            ]]
            :put scan_runs { scan_id => started_at, finished_at, scope_paths_json,
              events_emitted, rust_binary_version, pss_version }
            """
        )
    finally:
        db.close()


def test_atomic_write_preserves_temporal_relations(scratch_db: Path) -> None:
    """The P0 data-loss bug: a full reindex must NOT wipe the Rust
    temporal-index tables (events/elements_state/scan_runs). Seed a live DB
    with one row in each, run atomic_write_cozodb, and assert the rows and
    schema survive the staging swap untouched.
    """
    entries = {"user::phase-b-fixture": FIXTURE_ENTRY}
    atomic_write_cozodb(entries, scratch_db, version="3.0")
    _seed_temporal_relations(scratch_db)

    # A second full reindex is exactly the operation that used to destroy
    # the temporal tables (brand-new staging DB, no knowledge of them).
    atomic_write_cozodb(entries, scratch_db, version="3.1")

    db = open_db(scratch_db)
    try:
        events = db.run(
            "?[event_id, element_name, event_type] := "
            "*events{event_id, element_name, event_type}"
        ).get("rows", [])
        assert events == [
            ["01EVT0000000000000000001", "phase-b-fixture", "installed"]
        ], f"events table not preserved across reindex: {events}"

        state = db.run(
            "?[element_id, current_hash, exists] := "
            "*elements_state{element_id, current_hash, exists}"
        ).get("rows", [])
        assert state == [["abc123fnv", "deadbeef", True]], (
            f"elements_state not preserved across reindex: {state}"
        )

        runs = db.run(
            "?[scan_id, events_emitted] := *scan_runs{scan_id, events_emitted}"
        ).get("rows", [])
        assert runs == [["scan-1", 1]], f"scan_runs not preserved: {runs}"
    finally:
        db.close()


def test_atomic_write_fresh_db_has_no_temporal_relations(scratch_db: Path) -> None:
    """A brand-new install (no prior DB at all) must still swap cleanly —
    there is nothing to preserve, and that must not raise.
    """
    entries = {"user::phase-b-fixture": FIXTURE_ENTRY}
    count = atomic_write_cozodb(entries, scratch_db, version="3.0")
    assert count == 1

    db = open_db(scratch_db)
    try:
        # None of the temporal tables should exist; querying one must fail
        # (relation not found) rather than silently returning rows.
        with pytest.raises(Exception):  # noqa: PT011 — cozo raises its own error type
            db.run("?[event_id] := *events{event_id}")
    finally:
        db.close()


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


def test_known_schema_relations_matches_create_db_schema(tmp_path: Path) -> None:
    """Drift guard: _KNOWN_SCHEMA_RELATIONS lists EXACTLY what _create_db_schema creates.

    If a relation is added to _create_db_schema without updating the constant,
    _snapshot_extra_relations would classify it as Rust-owned and re-:create it
    in staging over the schema's copy — failing every subsequent reindex at
    runtime. Conversely a stale constant entry (schema no longer creates it)
    would silently DROP that relation's rows on the next swap. Catch both in CI.
    """
    from pycozo.client import Client  # local: only this test needs a raw client

    db = Client("sqlite", str(tmp_path / "schema-only.db"), dataframe=False)
    try:
        _create_db_schema(db)
        rows = db.run("::relations").get("rows", [])
        created = {r[0] for r in rows if r[2] == "normal"}
    finally:
        db.close()
    assert created == set(_KNOWN_SCHEMA_RELATIONS), (
        "drift between _create_db_schema and _KNOWN_SCHEMA_RELATIONS — "
        f"missing from constant: {sorted(created - set(_KNOWN_SCHEMA_RELATIONS))}; "
        f"stale in constant: {sorted(set(_KNOWN_SCHEMA_RELATIONS) - created)}"
    )
