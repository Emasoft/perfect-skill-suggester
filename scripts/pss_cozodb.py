#!/usr/bin/env python3
"""PSS CozoDB Python query helpers.

Thin wrapper around `pycozo[embedded]` that opens the PSS CozoDB index at the
canonical data-dir path (resolved via pss_paths) and exposes query helpers for
Python callers. This module is part of Phase A of the CozoDB unification
migration tracked in TRDD-46ac514e-3627-44a6-b916-f37a1504b969: it lets Python
scripts query the index without full-parsing the 11-MB skill-index.json every
time.

CozoDB schema (written by the Rust binary's `pss --build-db` subcommand, as
of v2.10.0):

    :create skills {
        name: String, source: String =>
        id, path, skill_type, description, tier, boost, category,
        server_type, server_command, server_args_json, language_ids_json,
        negative_kw_json, patterns_json, directories_json, path_patterns_json,
        use_cases_json, co_usage_json, alternatives_json, domain_gates_json,
        file_types_json, keywords_json, intents_json, tools_json, services_json,
        frameworks_json, languages_json, platforms_json, domains_json,
        path_gates_json, first_indexed_at, last_updated_at
    }

Auxiliary normalized relations used for indexed search:
    skill_keywords { skill_name, value }
    skill_intents  { skill_name, value }
    skill_tools    { skill_name, value }
    skill_services { skill_name, value }
    skill_frameworks { skill_name, value }
    skill_languages { skill_name, value }
    skill_platforms { skill_name, value }
    skill_domains   { skill_name, value }
    skill_file_types { skill_name, value }
    kw_lookup { keyword_lower, skill_name }
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover  — Windows has no fcntl
    fcntl = None  # type: ignore[assignment]

# pycozo is the canonical runtime dependency. Historically this module
# sys.exit'd when the import failed — that broke pss_hook.py's graceful
# ImportError fallback by propagating SystemExit past its try/except and
# taking the hook process down with a user-visible stderr error.
#
# Current contract: module load NEVER kills the caller. If pycozo is
# missing, Client is replaced by a stub class whose constructor raises a
# clear ImportError at first use. Type annotations stay valid because
# Client remains a class symbol either way.
#
# hooks/hooks.json now invokes Python scripts via `uv run --script`, so on
# normal installs pycozo is always available. This stub path is reached
# only in legacy dev environments where the module is imported by a plain
# `python3` with no venv.
_PYCOZO_IMPORT_ERROR: ImportError | None = None
try:
    from pycozo.client import Client
except ImportError as _pycozo_import_err:  # pragma: no cover
    _PYCOZO_IMPORT_ERROR = _pycozo_import_err

    class Client:  # type: ignore[no-redef]
        """Stub raised when pycozo is not installed. Real Client is re-exported above when available."""

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise ImportError(
                "pycozo is required for pss_cozodb. hooks/hooks.json invokes "
                "Python via `uv run --script` which provisions pycozo "
                "automatically — make sure `uv` is on your PATH "
                "(https://docs.astral.sh/uv/). To install manually: "
                "`uv pip install 'pycozo[embedded]>=0.7.6'`. "
                f"Original import error: {_PYCOZO_IMPORT_ERROR}"
            )

        def run(self, *_args: Any, **_kwargs: Any) -> dict:
            raise ImportError("pycozo not available")  # defensive; Client() already raised

        def close(self) -> None:
            return None


def _require_pycozo() -> None:
    """Raise a clear error if pycozo failed to import at module load."""
    if _PYCOZO_IMPORT_ERROR is not None:
        raise _PYCOZO_IMPORT_ERROR

# pss_paths lives next to this module
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import pss_paths  # noqa: E402

DB_FILENAME = "pss-skill-index.db"
LOCK_FILENAME = "pss-skill-index.db.lock"


# ----------------------------------------------------------------------------
# DB connection
# ----------------------------------------------------------------------------


def get_db_path() -> Path:
    """Resolve the CozoDB file path via the same logic the Rust binary uses."""
    return pss_paths.get_data_dir() / DB_FILENAME


def open_db(path: Path | None = None) -> Client:
    """Open the CozoDB. Callers are responsible for `db.close()`.

    The DB must already exist — it is built by the Rust binary during
    `/pss-reindex-skills`. Callers that discover the DB is missing should
    trigger a reindex (the hook's auto-reindex path does this).
    """
    _require_pycozo()
    db_path = Path(path) if path else get_db_path()
    if not db_path.exists():
        raise FileNotFoundError(
            f"CozoDB not found at {db_path}. Run /pss-reindex-skills to build it."
        )
    return Client("sqlite", str(db_path))


# ----------------------------------------------------------------------------
# Health check (used by pss_hook.py to replace the 256-byte JSON sanity check)
# ----------------------------------------------------------------------------


def count_skills(db: Client | None = None) -> int:
    """Return the number of rows in the `skills` table.

    Returns 0 if the DB is missing, corrupt, or empty. Never raises — the hook
    needs a lightweight health check, not an exception-throwing path.
    """
    own_db = db is None
    try:
        client = db or open_db()
    except FileNotFoundError:
        return 0
    try:
        result = client.run("?[count(name)] := *skills{ name }")
        rows = result.get("rows", [])
        if not rows or not rows[0]:
            return 0
        return int(rows[0][0])
    except Exception:
        return 0
    finally:
        if own_db:
            try:
                client.close()
            except Exception:
                pass


def db_is_healthy() -> bool:
    """True if the DB exists and has at least one row."""
    return count_skills() > 0


# ----------------------------------------------------------------------------
# Timestamp queries (the user's v2.10.0 feature request)
# ----------------------------------------------------------------------------


def _iso_utc(dt: datetime) -> str:
    """Normalise a datetime to RFC 3339 UTC (matches Rust's to_rfc3339_opts)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def added_since(
    since: datetime | str, db: Client | None = None, limit: int | None = None
) -> list[dict[str, Any]]:
    """Return elements whose `first_indexed_at` is >= `since`.

    `since` can be a datetime (naive or aware) or an ISO 8601 string.
    Useful for "what got installed recently?" queries. Results are sorted
    by first_indexed_at ascending (oldest first).
    """
    since_str = since if isinstance(since, str) else _iso_utc(since)
    own_db = db is None
    client = db or open_db()
    try:
        query = f"""
            ?[name, skill_type, source, path, description, first_indexed_at] := \
                *skills{{ name, skill_type, source, path, description, first_indexed_at }}, \
                first_indexed_at >= '{_escape(since_str)}' \
            :order first_indexed_at
        """
        if limit and limit > 0:
            query = query.strip().rstrip(":order first_indexed_at")
            query = f"{query} :order first_indexed_at :limit {int(limit)}"
        result = client.run(query)
        return _rows_to_dicts(result)
    finally:
        if own_db:
            client.close()


def added_between(
    start: datetime | str,
    end: datetime | str,
    db: Client | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return elements whose `first_indexed_at` is in `[start, end]` inclusive."""
    start_str = start if isinstance(start, str) else _iso_utc(start)
    end_str = end if isinstance(end, str) else _iso_utc(end)
    own_db = db is None
    client = db or open_db()
    try:
        query = f"""
            ?[name, skill_type, source, path, description, first_indexed_at] := \
                *skills{{ name, skill_type, source, path, description, first_indexed_at }}, \
                first_indexed_at >= '{_escape(start_str)}', \
                first_indexed_at <= '{_escape(end_str)}' \
            :order first_indexed_at
        """
        if limit and limit > 0:
            query = query + f" :limit {int(limit)}"
        result = client.run(query)
        return _rows_to_dicts(result)
    finally:
        if own_db:
            client.close()


def updated_since(
    since: datetime | str, db: Client | None = None, limit: int | None = None
) -> list[dict[str, Any]]:
    """Return elements touched by a reindex since `since` (via last_updated_at)."""
    since_str = since if isinstance(since, str) else _iso_utc(since)
    own_db = db is None
    client = db or open_db()
    try:
        query = f"""
            ?[name, skill_type, source, path, description, last_updated_at] := \
                *skills{{ name, skill_type, source, path, description, last_updated_at }}, \
                last_updated_at >= '{_escape(since_str)}' \
            :order -last_updated_at
        """
        if limit and limit > 0:
            query = query + f" :limit {int(limit)}"
        result = client.run(query)
        return _rows_to_dicts(result)
    finally:
        if own_db:
            client.close()


# ----------------------------------------------------------------------------
# Search helpers (the user's v2.10.0 feature request)
# ----------------------------------------------------------------------------


def search_by_name(
    pattern: str, db: Client | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    """Return entries whose `name` contains `pattern` (case-insensitive substring)."""
    p = pattern.lower()
    own_db = db is None
    client = db or open_db()
    try:
        query = f"""
            ?[name, skill_type, source, path, description, first_indexed_at] := \
                *skills{{ name, skill_type, source, path, description, first_indexed_at }}, \
                is_in(lowercase(name), '{_escape(p)}') \
            :limit {int(limit)}
        """
        # Cozo doesn't have native LIKE — we use string substring check.
        # The helper below falls back to Python-side filtering if Cozo rejects the expr.
        try:
            result = client.run(query)
            return _rows_to_dicts(result)
        except Exception:
            all_rows = client.run(
                "?[name, skill_type, source, path, description, first_indexed_at] := "
                "*skills{ name, skill_type, source, path, description, first_indexed_at }"
            )
            filtered = [
                row for row in all_rows.get("rows", []) if p in row[0].lower()
            ][: int(limit)]
            return _rows_to_dicts({"headers": all_rows.get("headers"), "rows": filtered})
    finally:
        if own_db:
            client.close()


def search_by_type(
    elem_type: str, db: Client | None = None, limit: int = 500
) -> list[dict[str, Any]]:
    """Return all entries of a given type: skill / agent / command / rule / mcp / lsp."""
    own_db = db is None
    client = db or open_db()
    try:
        query = f"""
            ?[name, skill_type, source, path, description, first_indexed_at] := \
                *skills{{ name, skill_type, source, path, description, first_indexed_at }}, \
                skill_type = '{_escape(elem_type)}' \
            :limit {int(limit)}
        """
        result = client.run(query)
        return _rows_to_dicts(result)
    finally:
        if own_db:
            client.close()


def search_by_keyword(
    keyword: str, db: Client | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    """Return entries with an exact keyword match via the `skill_keywords` index."""
    kw = keyword.lower()
    own_db = db is None
    client = db or open_db()
    try:
        query = f"""
            ?[name, skill_type, source, path, description] := \
                *skill_keywords{{ skill_name: name, value: '{_escape(kw)}' }}, \
                *skills{{ name, skill_type, source, path, description }} \
            :limit {int(limit)}
        """
        result = client.run(query)
        return _rows_to_dicts(result)
    finally:
        if own_db:
            client.close()


def search_by_domain(
    domain: str, db: Client | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    """Return entries gated by or tagged with the given domain."""
    d = domain.lower()
    own_db = db is None
    client = db or open_db()
    try:
        query = f"""
            ?[name, skill_type, source, path, description] := \
                *skill_domains{{ skill_name: name, value: '{_escape(d)}' }}, \
                *skills{{ name, skill_type, source, path, description }} \
            :limit {int(limit)}
        """
        result = client.run(query)
        return _rows_to_dicts(result)
    finally:
        if own_db:
            client.close()


def search_by_language(
    language: str, db: Client | None = None, limit: int = 500
) -> list[dict[str, Any]]:
    """Return entries targeting a given programming language."""
    lang = language.lower()
    own_db = db is None
    client = db or open_db()
    try:
        query = f"""
            ?[name, skill_type, source, path, description] := \
                *skill_languages{{ skill_name: name, value: '{_escape(lang)}' }}, \
                *skills{{ name, skill_type, source, path, description }} \
            :limit {int(limit)}
        """
        result = client.run(query)
        return _rows_to_dicts(result)
    finally:
        if own_db:
            client.close()


def search_by_description(
    text: str, db: Client | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    """Return entries whose `description` contains the given substring (case-insensitive).

    CozoDB has no native LIKE / substring operator in its public Datalog, so
    this function pulls descriptions and filters in Python. For very large
    indexes this is O(n) — acceptable for an on-demand debugging / admin
    helper, not a hot-path query.
    """
    needle = text.lower()
    own_db = db is None
    client = db or open_db()
    try:
        all_rows = client.run(
            "?[name, skill_type, source, path, description] := "
            "*skills{ name, skill_type, source, path, description }"
        )
        out: list[dict[str, Any]] = []
        headers = all_rows.get("headers", ["name", "skill_type", "source", "path", "description"])
        for row in all_rows.get("rows", []):
            if len(row) >= 5 and needle in (row[4] or "").lower():
                out.append(dict(zip(headers, row)))
                if len(out) >= limit:
                    break
        return out
    finally:
        if own_db:
            client.close()


def search_full_text(
    query: str, db: Client | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """Best-effort full-text search across name, description, and keywords.

    Splits the query into tokens and unions matches from:
        - `skill_keywords` (exact per-token match)
        - name substring
        - description substring
    Results are deduplicated by (name, source) and ranked by match count.
    """
    tokens = [t.lower() for t in query.split() if t.strip()]
    if not tokens:
        return []
    own_db = db is None
    client = db or open_db()
    try:
        all_rows = client.run(
            "?[name, skill_type, source, path, description] := "
            "*skills{ name, skill_type, source, path, description }"
        )
        by_key: dict[tuple, dict[str, Any]] = {}
        for row in all_rows.get("rows", []):
            if len(row) < 5:
                continue
            name, stype, src, path, desc = row[0], row[1], row[2], row[3], row[4] or ""
            name_lc = (name or "").lower()
            desc_lc = desc.lower()
            score = 0
            for tok in tokens:
                if tok in name_lc:
                    score += 3
                if tok in desc_lc:
                    score += 1
            if score > 0:
                key = (name, src)
                entry = by_key.get(key)
                if entry is None or entry["_score"] < score:
                    by_key[key] = {
                        "name": name,
                        "skill_type": stype,
                        "source": src,
                        "path": path,
                        "description": desc,
                        "_score": score,
                    }
        ranked = sorted(by_key.values(), key=lambda r: -r["_score"])[:limit]
        for r in ranked:
            r.pop("_score", None)
        return ranked
    finally:
        if own_db:
            client.close()


def get_by_name(
    name: str, source: str | None = None, db: Client | None = None
) -> dict[str, Any] | None:
    """Return a single entry by (name, source). If `source` is None, returns the first match.

    Note: Cozo's Datalog requires rule-head variables to be bound. When the
    pattern pins `name: 'literal'`, the head cannot reuse `name` — so we
    bind via an equality predicate (`n = '...'`) instead.
    """
    own_db = db is None
    client = db or open_db()
    try:
        if source:
            query = f"""
                ?[name, skill_type, source, path, description, tier, boost, \
                  first_indexed_at, last_updated_at] := \
                    *skills{{ name, source, skill_type, path, description, tier, boost, \
                              first_indexed_at, last_updated_at }}, \
                    name = '{_escape(name)}', source = '{_escape(source)}'
            """
        else:
            query = f"""
                ?[name, skill_type, source, path, description, tier, boost, \
                  first_indexed_at, last_updated_at] := \
                    *skills{{ name, source, skill_type, path, description, tier, boost, \
                              first_indexed_at, last_updated_at }}, \
                    name = '{_escape(name)}'
            """
        result = client.run(query)
        dicts = _rows_to_dicts(result)
        return dicts[0] if dicts else None
    finally:
        if own_db:
            client.close()


# ----------------------------------------------------------------------------
# Phase C full-entry helpers — replace JSON reads in cold-path scripts
# ----------------------------------------------------------------------------
# These helpers return Python-friendly entry dicts with JSON sub-fields
# already deserialized (keywords is a list, not a JSON string). This matches
# the shape `skill-index.json` used to have, so callers that previously read
# JSON can switch to CozoDB with minimal re-wiring.
#
# Why a separate helper family: the `search_by_*` functions return a minimal
# projection (6 columns) for fast UI display; callers like pss_make_plugin /
# pss_verify_profile / pss_generate need the full skill row. Doing a SELECT *
# here is the right trade-off — they run once per command-invocation (cold
# path), not per hook call.


_FULL_ENTRY_COLUMNS: tuple[str, ...] = (
    "name",
    "source",
    "skill_type",
    "path",
    "description",
    "tier",
    "boost",
    "category",
    "server_type",
    "server_command",
    "server_args_json",
    "language_ids_json",
    "patterns_json",
    "directories_json",
    "path_patterns_json",
    "use_cases_json",
    "domain_gates_json",
    "file_types_json",
    "keywords_json",
    "intents_json",
    "tools_json",
    "services_json",
    "frameworks_json",
    "languages_json",
    "platforms_json",
    "domains_json",
    "path_gates_json",
    "first_indexed_at",
    "last_updated_at",
)

# JSON columns in _FULL_ENTRY_COLUMNS — the "_json" suffixed ones are stored
# as serialized JSON strings in CozoDB; we deserialize them here so Python
# callers see the native Python object they had when reading JSON.
_JSON_COLUMNS: frozenset[str] = frozenset(
    c for c in _FULL_ENTRY_COLUMNS if c.endswith("_json")
)


def _row_to_full_entry(row: list[Any], headers: list[str]) -> dict[str, Any]:
    """Convert a raw CozoDB row into the JSON-compatible entry dict.

    - `skill_type` column becomes `type` field (matches the old JSON schema).
    - Columns ending in `_json` are deserialized from their string form.
      The suffix is stripped, so `keywords_json` becomes `keywords`.
    - Empty JSON strings default to [] for list columns and {} for object
      columns — this matches Rust's default behaviour in run_build_db.
    """
    entry: dict[str, Any] = {}
    for col, val in zip(headers, row):
        if col == "skill_type":
            entry["type"] = val
            continue
        if col in _JSON_COLUMNS:
            py_key = col[: -len("_json")]
            if isinstance(val, str) and val:
                try:
                    entry[py_key] = json.loads(val)
                except json.JSONDecodeError:
                    # Corrupt JSON in the column — fall back to a safe default.
                    # domain_gates / path_gates are dicts; everything else is a list.
                    entry[py_key] = {} if py_key in ("domain_gates", "path_gates") else []
            else:
                entry[py_key] = {} if py_key in ("domain_gates", "path_gates") else []
            continue
        entry[col] = val
    return entry


def get_entry_by_name(
    name: str, source: str | None = None, db: Client | None = None
) -> dict[str, Any] | None:
    """Return a full entry dict by name (with deserialized JSON sub-fields).

    Used by Phase C scripts that replaced `json.load(skill-index.json)` +
    linear scan with a single indexed CozoDB query. Returns None if the
    entry does not exist.

    When two sources contain the same name (e.g. a user skill and a plugin
    skill sharing a name), passing `source` disambiguates. Without `source`,
    the first matching row wins — matches the legacy JSON behavior where
    `index["skills"][name]` returned whichever entry the merge queue wrote
    last.
    """
    own_db = db is None
    client = db or open_db()
    try:
        cols = ", ".join(_FULL_ENTRY_COLUMNS)
        if source:
            query = (
                f"?[{cols}] := "
                f"*skills{{ {cols} }}, "
                f"name = '{_escape(name)}', source = '{_escape(source)}'"
            )
        else:
            query = (
                f"?[{cols}] := "
                f"*skills{{ {cols} }}, "
                f"name = '{_escape(name)}'"
            )
        result = client.run(query)
        rows = result.get("rows", [])
        headers = result.get("headers", list(_FULL_ENTRY_COLUMNS))
        if not rows:
            return None
        return _row_to_full_entry(rows[0], headers)
    finally:
        if own_db:
            client.close()


def get_all_entries(
    db: Client | None = None, type_filter: str | None = None
) -> dict[str, dict[str, Any]]:
    """Return every entry as a {name: full_entry_dict} mapping.

    Replaces `json.load(skill-index.json)["skills"]` for cold-path scripts.
    If two sources share a name, the last-enumerated row wins — same as the
    legacy JSON behavior where source::name keys collapsed when reading
    into a plain {name → entry} dict.

    Optional `type_filter` ("skill", "agent", "command", "rule", "mcp",
    "lsp", "output-style", "hook") restricts the scan server-side.
    """
    own_db = db is None
    client = db or open_db()
    try:
        cols = ", ".join(_FULL_ENTRY_COLUMNS)
        if type_filter:
            query = (
                f"?[{cols}] := "
                f"*skills{{ {cols} }}, "
                f"skill_type = '{_escape(type_filter)}'"
            )
        else:
            query = f"?[{cols}] := *skills{{ {cols} }}"
        result = client.run(query)
        headers = result.get("headers", list(_FULL_ENTRY_COLUMNS))
        out: dict[str, dict[str, Any]] = {}
        for row in result.get("rows", []):
            entry = _row_to_full_entry(row, headers)
            name = entry.get("name")
            if name:
                out[str(name)] = entry
        return out
    finally:
        if own_db:
            client.close()


# ----------------------------------------------------------------------------
# Phase B write helpers — Python becomes canonical writer for CozoDB
# ----------------------------------------------------------------------------
# Mirrors the Rust `run_build_db` + `insert_skills_batch` logic. Opens the
# target DB under fcntl.LOCK_EX on a separate .lock file (sqlite will conflict
# if you try to lock the .db file itself), snapshots the existing
# first_indexed_at timestamps to preserve the "installation time" across
# rebuilds, then runs :replace on the skills table + all 9 auxiliary
# relations + kw_lookup + skill_ids + pss_metadata.
#
# Must produce IDENTICAL row contents to the Rust writer because the Rust hot
# path (`load_candidates_from_db`) depends on the exact schema shape.


def _fnv1a_entry_id(name: str, source: str) -> str:
    """Port of Rust's make_entry_id — 13-char base36 FNV-1a 64-bit hash.

    Must match rust/skill-suggester/src/main.rs::make_entry_id byte-for-byte,
    because the Rust hot path treats HashMap<entry_id → SkillEntry> as primary
    key. Drift here means silent lookup failures in `load_candidates_from_db`
    via the skill_ids auxiliary table.
    """
    fnv_offset = 0xCBF29CE484222325
    fnv_prime = 0x100000001B3
    mask64 = 0xFFFFFFFFFFFFFFFF
    h = fnv_offset
    for b in name.encode("utf-8"):
        h ^= b
        h = (h * fnv_prime) & mask64
    # 0xFF separator — prevents collisions between ("ab","cd") and ("abc","d")
    h ^= 0xFF
    h = (h * fnv_prime) & mask64
    for b in source.encode("utf-8"):
        h ^= b
        h = (h * fnv_prime) & mask64
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    digits: list[str] = []
    v = h
    if v == 0:
        digits.append("0")
    else:
        while v > 0:
            digits.append(alphabet[v % 36])
            v //= 36
    # Pad to 13 chars then reverse for consistent ordering — same as Rust
    while len(digits) < 13:
        digits.append("0")
    return "".join(reversed(digits))


def _now_rfc3339() -> str:
    """RFC 3339 UTC timestamp matching Rust's to_rfc3339_opts(Secs, true)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


# All 33 columns on the skills relation, in schema declaration order.
# Mirrors create_db_schema() in rust/skill-suggester/src/main.rs.
_SKILL_SCHEMA_COLS: list[str] = [
    "name", "source", "id", "path", "skill_type", "description",
    "tier", "boost", "category",
    "server_type", "server_command", "server_args_json",
    "language_ids_json", "negative_kw_json",
    "patterns_json", "directories_json", "path_patterns_json",
    "use_cases_json", "co_usage_json", "alternatives_json",
    "domain_gates_json", "file_types_json",
    "keywords_json", "intents_json", "tools_json", "services_json",
    "frameworks_json", "languages_json", "platforms_json", "domains_json",
    "path_gates_json",
    "first_indexed_at", "last_updated_at",
]

# The 9 auxiliary normalised relations that feed kw_lookup.
_AUX_RELATIONS: list[tuple[str, str]] = [
    ("skill_keywords", "keywords"),
    ("skill_intents", "intents"),
    ("skill_tools", "tools"),
    ("skill_services", "services"),
    ("skill_frameworks", "frameworks"),
    ("skill_languages", "languages"),
    ("skill_platforms", "platforms"),
    ("skill_domains", "domains"),
    ("skill_file_types", "file_types"),
]


def _create_db_schema(db: Client) -> None:
    """Create the full PSS CozoDB schema (skills + 9 aux + kw_lookup + meta).

    Mirrors Rust's create_db_schema() exactly. Called on a fresh DB file only
    — if a prior DB exists, atomic_write_cozodb removes it first.
    """
    db.run(
        """
        {:create skills {
            name: String, source: String =>
            id: String,
            path: String,
            skill_type: String,
            description: String,
            tier: String,
            boost: Int,
            category: String,
            server_type: String,
            server_command: String,
            server_args_json: String,
            language_ids_json: String,
            negative_kw_json: String,
            patterns_json: String,
            directories_json: String,
            path_patterns_json: String,
            use_cases_json: String,
            co_usage_json: String,
            alternatives_json: String,
            domain_gates_json: String,
            file_types_json: String,
            keywords_json: String,
            intents_json: String,
            tools_json: String,
            services_json: String,
            frameworks_json: String,
            languages_json: String,
            platforms_json: String,
            domains_json: String,
            path_gates_json: String,
            first_indexed_at: String,
            last_updated_at: String
        }}
        """
    )
    for rel, _field in _AUX_RELATIONS:
        db.run(f"{{:create {rel} {{ skill_name: String, value: String }}}}")
    db.run(
        "{:create domain_registry { canonical_name: String => "
        "has_generic: Bool, skill_count: Int }}"
    )
    db.run("{:create domain_aliases { alias: String, canonical_name: String }}")
    db.run("{:create domain_keywords { canonical_name: String, keyword: String }}")
    db.run("{:create domain_skills { canonical_name: String, skill_name: String }}")
    db.run("{:create kw_lookup { keyword_lower: String, skill_name: String }}")
    db.run("{:create skill_ids { id: String => name: String, source: String }}")
    db.run("{:create pss_metadata { key: String => value: String }}")
    db.run(
        """{:create rules {
            name: String, scope: String =>
            description: String,
            source_path: String,
            summary: String,
            keywords_json: String
        }}"""
    )


def _snapshot_prior_timestamps(db_path: Path) -> dict[tuple[str, str], str]:
    """Read (name, source) → first_indexed_at from the prior DB if it exists.

    Mirrors the snapshot phase in Rust's run_build_db. Preserves "installation
    time" across rebuilds — without it every reindex would reset the timestamp
    to "now" and added_since/added_between would be useless.
    """
    if not db_path.exists():
        return {}
    try:
        client = Client("sqlite", str(db_path))
    except Exception:
        return {}
    result: dict[tuple[str, str], str] = {}
    try:
        rows = client.run(
            "?[name, source, first_indexed_at] := "
            "*skills{ name, source, first_indexed_at }"
        )
        for row in rows.get("rows", []):
            if len(row) >= 3 and row[0] and row[1] and row[2]:
                result[(row[0], row[1])] = row[2]
    except Exception:
        # Legacy DB layout or missing columns — start fresh.
        pass
    finally:
        try:
            client.close()
        except Exception:
            pass
    return result


def _extract_skill_fields(entry: dict[str, Any]) -> dict[str, Any]:
    """Normalise a JSON skill entry into the 33 CozoDB columns.

    Called per-entry by atomic_write_cozodb. The input comes from the merged
    skill-index.json (composite key `source::name` → entry dict), and the
    output is a BTreeMap-ready dict suitable for a Cozo :put parameterised
    query.
    """
    # Defensive getters — JSON structure from pass1_batch can omit any optional
    # field. Mirrors the #[serde(default)] behaviour in SkillEntry.
    def s(key: str, default: str = "") -> str:
        v = entry.get(key, default)
        return v if isinstance(v, str) else default

    def lst(key: str) -> list:
        v = entry.get(key, [])
        return v if isinstance(v, list) else []

    def dct(key: str) -> dict:
        v = entry.get(key, {})
        return v if isinstance(v, dict) else {}

    # Description is capped at 500 chars — same truncation as Rust's
    # insert_skills_batch to keep row size bounded.
    description = s("description")[:500]

    # Type field is stored as `skill_type` in CozoDB but `type` in JSON.
    skill_type = s("type") or s("skill_type")

    co_usage = dct("co_usage")
    # Ensure co_usage has the expected shape (usually_with/precedes/follows).
    co_usage_normalised = {
        "usually_with": co_usage.get("usually_with", []),
        "precedes": co_usage.get("precedes", []),
        "follows": co_usage.get("follows", []),
    }

    return {
        "name": s("name"),
        "source": s("source"),
        "path": s("path"),
        "skill_type": skill_type,
        "description": description,
        "tier": s("tier"),
        "boost": int(entry.get("boost", 0) or 0),
        "category": s("category"),
        "server_type": s("server_type"),
        "server_command": s("server_command"),
        "server_args": lst("server_args"),
        "language_ids": lst("language_ids"),
        "negative_keywords": lst("negative_keywords"),
        "patterns": lst("patterns"),
        "directories": lst("directories"),
        "path_patterns": lst("path_patterns"),
        "use_cases": lst("use_cases"),
        "co_usage": co_usage_normalised,
        "alternatives": lst("alternatives"),
        "domain_gates": dct("domain_gates"),
        "file_types": lst("file_types"),
        "keywords": lst("keywords"),
        "intents": lst("intents"),
        "tools": lst("tools"),
        "services": lst("services"),
        "frameworks": lst("frameworks"),
        "languages": lst("languages"),
        "platforms": lst("platforms"),
        "domains": lst("domains"),
        "path_gates": lst("path_gates"),
    }


def _put_skill_row(
    db: Client,
    norm: dict[str, Any],
    entry_id: str,
    first_indexed_at: str,
    last_updated_at: str,
) -> None:
    """Insert a single skill row via parameterised :put query.

    Mirrors the parameterised insert in Rust's insert_skills_batch. The
    parameter names match the $-prefixed placeholders in the query.
    """
    params = {
        "name": norm["name"],
        "source": norm["source"],
        "id": entry_id,
        "path": norm["path"],
        "skill_type": norm["skill_type"],
        "description": norm["description"],
        "tier": norm["tier"],
        "boost": norm["boost"],
        "category": norm["category"],
        "server_type": norm["server_type"],
        "server_command": norm["server_command"],
        "server_args_json": json.dumps(norm["server_args"]),
        "language_ids_json": json.dumps(norm["language_ids"]),
        "negative_kw_json": json.dumps(norm["negative_keywords"]),
        "patterns_json": json.dumps(norm["patterns"]),
        "directories_json": json.dumps(norm["directories"]),
        "path_patterns_json": json.dumps(norm["path_patterns"]),
        "use_cases_json": json.dumps(norm["use_cases"]),
        "co_usage_json": json.dumps(norm["co_usage"]),
        "alternatives_json": json.dumps(norm["alternatives"]),
        "domain_gates_json": json.dumps(norm["domain_gates"]),
        "file_types_json": json.dumps(norm["file_types"]),
        "keywords_json": json.dumps(norm["keywords"]),
        "intents_json": json.dumps(norm["intents"]),
        "tools_json": json.dumps(norm["tools"]),
        "services_json": json.dumps(norm["services"]),
        "frameworks_json": json.dumps(norm["frameworks"]),
        "languages_json": json.dumps(norm["languages"]),
        "platforms_json": json.dumps(norm["platforms"]),
        "domains_json": json.dumps(norm["domains"]),
        "path_gates_json": json.dumps(norm["path_gates"]),
        "first_indexed_at": first_indexed_at,
        "last_updated_at": last_updated_at,
    }
    script = (
        "?[name, id, path, skill_type, source, description, tier, boost, category, "
        "server_type, server_command, server_args_json, language_ids_json, "
        "negative_kw_json, patterns_json, directories_json, path_patterns_json, "
        "use_cases_json, co_usage_json, alternatives_json, domain_gates_json, "
        "file_types_json, keywords_json, intents_json, tools_json, services_json, "
        "frameworks_json, languages_json, platforms_json, domains_json, "
        "path_gates_json, first_indexed_at, last_updated_at] <- "
        "[[$name, $id, $path, $skill_type, $source, $description, $tier, $boost, "
        "$category, $server_type, $server_command, $server_args_json, "
        "$language_ids_json, $negative_kw_json, $patterns_json, $directories_json, "
        "$path_patterns_json, $use_cases_json, $co_usage_json, $alternatives_json, "
        "$domain_gates_json, $file_types_json, $keywords_json, $intents_json, "
        "$tools_json, $services_json, $frameworks_json, $languages_json, "
        "$platforms_json, $domains_json, $path_gates_json, $first_indexed_at, "
        "$last_updated_at]] "
        ":put skills { name, source => id, path, skill_type, description, tier, "
        "boost, category, server_type, server_command, server_args_json, "
        "language_ids_json, negative_kw_json, patterns_json, directories_json, "
        "path_patterns_json, use_cases_json, co_usage_json, alternatives_json, "
        "domain_gates_json, file_types_json, keywords_json, intents_json, "
        "tools_json, services_json, frameworks_json, languages_json, "
        "platforms_json, domains_json, path_gates_json, first_indexed_at, "
        "last_updated_at }"
    )
    db.run(script, params)


def _escape_cozo_str(s: str) -> str:
    """Escape a string for embedding in a Cozo inline data literal.

    The Cozo parser interprets backslash and double-quote. Matches the escape
    logic Rust uses in build_inline_data.
    """
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _batch_insert_pairs(db: Client, relation: str, pairs: list[tuple[str, str]]) -> None:
    """Batch-insert (skill_name, value) pairs into a 2-column relation.

    Mirrors Rust's batch_insert helper. Chunks of 500 rows per query to stay
    under Cozo's script-size limit.
    """
    if not pairs:
        return
    for i in range(0, len(pairs), 500):
        chunk = pairs[i : i + 500]
        data = ", ".join(
            f'["{_escape_cozo_str(n)}", "{_escape_cozo_str(v)}"]' for n, v in chunk
        )
        if not data:
            continue
        db.run(
            f"?[skill_name, value] <- [{data}] "
            f":put {relation} {{ skill_name, value }}"
        )


def _batch_insert_kw_lookup(db: Client, pairs: list[tuple[str, str]]) -> None:
    """Insert (keyword_lower, skill_name) rows into kw_lookup, 500 per batch."""
    if not pairs:
        return
    for i in range(0, len(pairs), 500):
        chunk = pairs[i : i + 500]
        data = ", ".join(
            f'["{_escape_cozo_str(k)}", "{_escape_cozo_str(n)}"]' for k, n in chunk
        )
        if not data:
            continue
        db.run(
            f"?[keyword_lower, skill_name] <- [{data}] "
            f":put kw_lookup {{ keyword_lower, skill_name }}"
        )


def _batch_insert_skill_ids(db: Client, triples: list[tuple[str, str, str]]) -> None:
    """Insert (id, name, source) triples into skill_ids, 500 per batch."""
    if not triples:
        return
    for i in range(0, len(triples), 500):
        chunk = triples[i : i + 500]
        data = ", ".join(
            f'["{_escape_cozo_str(i_)}", "{_escape_cozo_str(n)}", '
            f'"{_escape_cozo_str(s)}"]'
            for i_, n, s in chunk
        )
        if not data:
            continue
        db.run(
            f"?[id, name, source] <- [{data}] "
            f":put skill_ids {{ id => name, source }}"
        )


def atomic_write_cozodb(
    entries: dict[str, Any],
    db_path: Path | None = None,
    *,
    version: str = "",
    generated: str = "",
) -> int:
    """Replace the entire PSS CozoDB with the given merged index entries.

    `entries` is the `skills` map from skill-index.json — keyed by either the
    composite `source::name` (Python merge output) or by the 13-char entry ID
    (Rust-rehydrated index). Both are accepted because the Rust writer
    rehydrates the HashMap to entry-ID keys anyway; we recompute from
    (name, source) here.

    Acquires an fcntl.LOCK_EX lock on a separate .lock file next to the DB
    (sqlite will itself conflict if you try to flock() the .db), snapshots
    existing first_indexed_at timestamps to preserve installation time across
    rebuilds, removes the old DB, creates the schema fresh, and batch-inserts
    all rows.

    Returns the number of skill rows written.
    """
    if db_path is None:
        db_path = get_db_path()
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = db_path.parent / LOCK_FILENAME

    lock_fd = open(lock_path, "w")  # noqa: SIM115
    try:
        if fcntl is not None:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)

        # Snapshot first_indexed_at before removing the DB so we preserve
        # "installation time" across reindexes.
        prior = _snapshot_prior_timestamps(db_path)

        # Fresh build: remove the old DB file to drop the schema cleanly.
        # SQLite-backed CozoDB also creates -journal/-wal sidecars; clean them.
        for sidecar in (
            db_path,
            db_path.with_name(db_path.name + "-journal"),
            db_path.with_name(db_path.name + "-wal"),
            db_path.with_name(db_path.name + "-shm"),
        ):
            try:
                sidecar.unlink()
            except FileNotFoundError:
                pass

        db = Client("sqlite", str(db_path))
        try:
            _create_db_schema(db)

            # Insert version metadata.
            db.run(
                "?[key, value] <- [[$key, $value]] "
                ":put pss_metadata { key => value }",
                {"key": "version", "value": version or "unknown"},
            )
            if generated:
                db.run(
                    "?[key, value] <- [[$key, $value]] "
                    ":put pss_metadata { key => value }",
                    {"key": "generated", "value": generated},
                )
            db.run(
                "?[key, value] <- [[$key, $value]] "
                ":put pss_metadata { key => value }",
                {"key": "generator", "value": "python-merge-queue"},
            )

            now = _now_rfc3339()
            count = 0
            kw_pairs: list[tuple[str, str]] = []
            intent_pairs: list[tuple[str, str]] = []
            tool_pairs: list[tuple[str, str]] = []
            svc_pairs: list[tuple[str, str]] = []
            fw_pairs: list[tuple[str, str]] = []
            lang_pairs: list[tuple[str, str]] = []
            plat_pairs: list[tuple[str, str]] = []
            domain_pairs: list[tuple[str, str]] = []
            ft_pairs: list[tuple[str, str]] = []
            id_triples: list[tuple[str, str, str]] = []

            for _comp_key, raw_entry in entries.items():
                if not isinstance(raw_entry, dict):
                    continue
                norm = _extract_skill_fields(raw_entry)
                if not norm["name"]:
                    # Skip malformed rows — mirrors Rust behaviour
                    continue

                entry_id = _fnv1a_entry_id(norm["name"], norm["source"])

                # Preserve existing first_indexed_at if this (name, source)
                # was in the prior DB; otherwise stamp with now.
                preserved = prior.get((norm["name"], norm["source"]))
                if preserved:
                    first_at = preserved
                else:
                    json_first = raw_entry.get("first_indexed_at", "")
                    first_at = json_first if json_first else now

                _put_skill_row(db, norm, entry_id, first_at, now)

                # Collect pairs for aux relations (keyed by element name,
                # not entry ID — matches Rust).
                nm = norm["name"]
                for kw in norm["keywords"]:
                    kw_pairs.append((nm, kw))
                for it in norm["intents"]:
                    intent_pairs.append((nm, it))
                for tl in norm["tools"]:
                    tool_pairs.append((nm, tl))
                for sv in norm["services"]:
                    svc_pairs.append((nm, sv))
                for fw in norm["frameworks"]:
                    fw_pairs.append((nm, fw))
                for lg in norm["languages"]:
                    lang_pairs.append((nm, lg))
                for pl in norm["platforms"]:
                    plat_pairs.append((nm, pl))
                for dm in norm["domains"]:
                    domain_pairs.append((nm, dm))
                for ft in norm["file_types"]:
                    ft_pairs.append((nm, ft))
                id_triples.append((entry_id, nm, norm["source"]))

                count += 1

            # Batch-insert the 9 aux relations.
            _batch_insert_pairs(db, "skill_keywords", kw_pairs)
            _batch_insert_pairs(db, "skill_intents", intent_pairs)
            _batch_insert_pairs(db, "skill_tools", tool_pairs)
            _batch_insert_pairs(db, "skill_services", svc_pairs)
            _batch_insert_pairs(db, "skill_frameworks", fw_pairs)
            _batch_insert_pairs(db, "skill_languages", lang_pairs)
            _batch_insert_pairs(db, "skill_platforms", plat_pairs)
            _batch_insert_pairs(db, "skill_domains", domain_pairs)
            _batch_insert_pairs(db, "skill_file_types", ft_pairs)

            # Build kw_lookup (keyword_lower, skill_name) from ALL aux sources
            # plus name-part splits. The Rust hot path depends on this.
            lookup_pairs: set[tuple[str, str]] = set()
            for pairs in (
                kw_pairs, intent_pairs, tool_pairs, svc_pairs,
                fw_pairs, lang_pairs, plat_pairs, domain_pairs, ft_pairs,
            ):
                for name, value in pairs:
                    lower = value.lower()
                    if len(lower) >= 2:
                        lookup_pairs.add((lower, name))
            # Add name-part splits (e.g. "react-query" → "react", "query")
            for entry_id, name, _src in id_triples:
                for part in name.lower().replace("_", "-").replace(" ", "-").split("-"):
                    if len(part) >= 2:
                        lookup_pairs.add((part, name))
            _batch_insert_kw_lookup(db, sorted(lookup_pairs))

            # skill_ids: id => (name, source)
            _batch_insert_skill_ids(db, id_triples)

            return count
        finally:
            try:
                db.close()
            except Exception:
                pass
    finally:
        if fcntl is not None:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        lock_fd.close()


def export_json_snapshot(
    json_path: Path,
    db_path: Path | None = None,
    *,
    include_name_keyed: bool = True,
) -> int:
    """Write a JSON snapshot of the CozoDB to `json_path` atomically.

    Used by `pss export --json` (Rust CLI) and can be called from Python when
    a human-readable mirror of the DB is needed for `git diff` debugging.

    The emitted JSON matches the skill-index.json format written by
    pss_merge_queue so downstream tools can continue reading either.

    Returns the number of skill rows exported.
    """
    if db_path is None:
        db_path = get_db_path()
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"CozoDB not found at {db_path}")

    client = Client("sqlite", str(db_path))
    try:
        cols = ", ".join(_SKILL_SCHEMA_COLS)
        rows = client.run(
            f"?[{cols}] := *skills{{ {cols} }}"
        )
        headers = rows.get("headers") or _SKILL_SCHEMA_COLS
        skills: dict[str, Any] = {}
        for row in rows.get("rows", []):
            rec = dict(zip(headers, row))
            entry: dict[str, Any] = {
                "name": rec.get("name", ""),
                "source": rec.get("source", ""),
                "path": rec.get("path", ""),
                "type": rec.get("skill_type", ""),
                "description": rec.get("description", ""),
                "tier": rec.get("tier", ""),
                "boost": int(rec.get("boost", 0) or 0),
                "category": rec.get("category", ""),
                "server_type": rec.get("server_type", ""),
                "server_command": rec.get("server_command", ""),
                "first_indexed_at": rec.get("first_indexed_at", ""),
                "last_updated_at": rec.get("last_updated_at", ""),
            }
            for col, field in (
                ("server_args_json", "server_args"),
                ("language_ids_json", "language_ids"),
                ("negative_kw_json", "negative_keywords"),
                ("patterns_json", "patterns"),
                ("directories_json", "directories"),
                ("path_patterns_json", "path_patterns"),
                ("use_cases_json", "use_cases"),
                ("co_usage_json", "co_usage"),
                ("alternatives_json", "alternatives"),
                ("domain_gates_json", "domain_gates"),
                ("file_types_json", "file_types"),
                ("keywords_json", "keywords"),
                ("intents_json", "intents"),
                ("tools_json", "tools"),
                ("services_json", "services"),
                ("frameworks_json", "frameworks"),
                ("languages_json", "languages"),
                ("platforms_json", "platforms"),
                ("domains_json", "domains"),
                ("path_gates_json", "path_gates"),
            ):
                raw = rec.get(col, "")
                try:
                    entry[field] = json.loads(raw) if raw else (
                        {} if field in {"co_usage", "domain_gates"} else []
                    )
                except (json.JSONDecodeError, TypeError):
                    entry[field] = (
                        {} if field in {"co_usage", "domain_gates"} else []
                    )
            # Composite key `source::name` — matches pss_merge_queue
            key_src = entry.get("source") or "unknown"
            key_nm = entry.get("name") or "unnamed"
            composite_key = (
                f"{key_src}::{key_nm}" if include_name_keyed else key_nm
            )
            skills[composite_key] = entry

        version_row = client.run(
            "?[value] := *pss_metadata{ key: 'version', value }"
        )
        version_rows = version_row.get("rows") or []
        version = version_rows[0][0] if version_rows and version_rows[0] else "3.0"

        out = {
            "version": version,
            "generated": datetime.now(timezone.utc).isoformat(),
            "generator": "pss-export-json",
            "skill_count": len(skills),
            "skills": skills,
        }

        json_path = Path(json_path)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_str = tempfile.mkstemp(
            dir=str(json_path.parent), prefix=".pss_export_", suffix=".json"
        )
        tmp_path = Path(tmp_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(out, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            os.replace(tmp_path, json_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
        return len(skills)
    finally:
        try:
            client.close()
        except Exception:
            pass


# ----------------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------------


def _escape(s: str) -> str:
    """Minimal string escape for Cozo string literals: single-quote only."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


def _rows_to_dicts(result: dict) -> list[dict[str, Any]]:
    """Turn a pycozo {headers, rows} result into a list of dicts."""
    headers = result.get("headers") or []
    rows = result.get("rows") or []
    return [dict(zip(headers, row)) for row in rows]


# ----------------------------------------------------------------------------
# CLI entry point for ad-hoc inspection: python -m pss_cozodb [subcommand] ...
# ----------------------------------------------------------------------------


def _main(argv: list[str]) -> int:
    if not argv:
        print(
            "Usage: pss_cozodb <subcommand> [args]\n\n"
            "Subcommands:\n"
            "  count                            Print total skill count\n"
            "  added-since <iso-datetime>       Print entries installed since datetime\n"
            "  added-between <start> <end>      Print entries installed between datetimes\n"
            "  updated-since <iso-datetime>     Print entries re-enriched since datetime\n"
            "  name <pattern>                   Substring search on name\n"
            "  type <skill|agent|command|rule|mcp|lsp>\n"
            "  keyword <kw>                     Exact keyword match\n"
            "  domain <domain>                  Domain gate match\n"
            "  language <lang>                  Language match\n"
            "  description <text>               Description substring search\n"
            "  full-text <query>                Multi-token search across name+desc+keywords\n"
            "  get <name> [source]              Fetch full entry by name (and optional source)"
        )
        return 1
    sub, *args = argv
    try:
        if sub == "count":
            print(count_skills())
        elif sub == "added-since" and args:
            rows = added_since(args[0])
            _print_rows(rows)
        elif sub == "added-between" and len(args) >= 2:
            _print_rows(added_between(args[0], args[1]))
        elif sub == "updated-since" and args:
            _print_rows(updated_since(args[0]))
        elif sub == "name" and args:
            _print_rows(search_by_name(args[0]))
        elif sub == "type" and args:
            _print_rows(search_by_type(args[0]))
        elif sub == "keyword" and args:
            _print_rows(search_by_keyword(args[0]))
        elif sub == "domain" and args:
            _print_rows(search_by_domain(args[0]))
        elif sub == "language" and args:
            _print_rows(search_by_language(args[0]))
        elif sub == "description" and args:
            _print_rows(search_by_description(" ".join(args)))
        elif sub == "full-text" and args:
            _print_rows(search_full_text(" ".join(args)))
        elif sub == "get" and args:
            source = args[1] if len(args) > 1 else None
            entry = get_by_name(args[0], source)
            print(json.dumps(entry, indent=2) if entry else "(not found)")
        else:
            print(f"Unknown or malformed subcommand: {sub}", file=sys.stderr)
            return 2
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Query error: {e}", file=sys.stderr)
        return 1
    return 0


def _print_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("(no matches)")
        return
    for r in rows:
        name = r.get("name", "?")
        stype = r.get("skill_type", "?")
        src = r.get("source", "?")
        ts = r.get("first_indexed_at") or r.get("last_updated_at") or ""
        desc = (r.get("description") or "")[:80]
        print(f"  [{stype:7s}] {name:35s}  {src:40s}  {ts}  {desc}")


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
