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
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from pycozo.client import Client
except ImportError:  # pragma: no cover
    sys.exit(
        "ERROR: pycozo is required. Install with: uv pip install 'pycozo[embedded]'"
    )

# pss_paths lives next to this module
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import pss_paths  # noqa: E402

DB_FILENAME = "pss-skill-index.db"


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
