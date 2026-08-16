"""Currency guard for `docs/CC-COMPATIBILITY.md`.

That document is the tracked, authoritative record of which Claude Code releases
PSS has been assessed against. It is maintained BY HAND — `docs/CC-COMPATIBILITY.md`
("How to verify PSS compatibility with a new CC release") describes a purely manual
procedure, and until this module existed nothing checked the result.

The failure mode is silent and it has already happened: on 2026-08-04 the matrix
carried entries through v2.1.218 while CC had shipped through v2.1.221, and the
range sentence at the top still advertised `2.1.69 → 2.1.218`. Nothing was red.
A stale range is worse than no range, because it reads as a positive claim
("assessed through 2.1.218") that no longer corresponds to any assessment.

The three invariants below are what a human actually gets wrong when hand-editing
a reverse-chronological log: bumping the header but forgetting an entry (or the
reverse), pasting a new entry into the wrong place, and adding a version twice.

No mocks — every assertion reads the real shipped document.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "docs" / "CC-COMPATIBILITY.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

MATRIX_HEADING = "## Version-by-version compatibility matrix"

# "PSS ... is tested against Claude Code **2.1.69 → 2.1.221**."
DOC_RANGE_RE = re.compile(r"tested against Claude Code \*\*(\d+\.\d+\.\d+) → (\d+\.\d+\.\d+)\*\*")
# "Tested with Claude Code 2.1.69 → 2.1.221. ... Latest: v2.1.221."
CLAUDE_RANGE_RE = re.compile(r"Tested with Claude Code (\d+\.\d+\.\d+) → (\d+\.\d+\.\d+)")
CLAUDE_LATEST_RE = re.compile(r"Latest: v(\d+\.\d+\.\d+)")

VERSION_RE = re.compile(r"\d+\.\d+\.\d+")


def _ver(text: str) -> tuple[int, ...]:
    return tuple(int(p) for p in text.split("."))


def _matrix_section() -> str:
    """The matrix only — later sections have their own `###` headings."""
    body = DOC.read_text(encoding="utf-8")
    assert MATRIX_HEADING in body, f"{DOC.name} lost its {MATRIX_HEADING!r} section"
    after = body.split(MATRIX_HEADING, 1)[1]
    # Stop at the next top-level section so unrelated `###` headings stay out.
    return re.split(r"^## ", after, maxsplit=1, flags=re.M)[0]


def _entry_versions() -> list[list[str]]:
    """CC releases named by each matrix entry heading, in document order.

    A heading may name several releases — a collapsed range
    (`### v2.1.210–2.1.212`) or a grab-bag (`### v2.1.184 / v2.1.188 / ...`).

    Only the version-list prefix is read. Everything from the first `(` or `—`
    onward is prose, and it contains OTHER version numbers that are not entries:
    PSS's own releases ("two PSS adaptations: v3.10.9 and v3.12.3") and asides
    ("no 2.1.213 release"). Scanning the whole line swept those up, which made
    the newest "documented CC release" come out as a PSS version.
    """
    out: list[list[str]] = []
    for line in _matrix_section().splitlines():
        if not re.match(r"^### v?\d", line):
            continue
        head = re.split(r"[(—]", line[len("### ") :], maxsplit=1)[0]
        out.append(VERSION_RE.findall(head))
    return out


def test_matrix_has_entries() -> None:
    """The matrix parses and is non-empty — guards the regexes themselves."""
    entries = _entry_versions()
    assert len(entries) > 10, f"only parsed {len(entries)} matrix entries; regex likely broke"
    assert all(entries), "a `### v...` heading named no parseable version"


def test_stated_range_upper_bound_matches_newest_documented_release() -> None:
    """The advertised range must not outrun, or lag behind, the actual entries.

    This is the exact drift that went unnoticed: entries stopped at v2.1.218 and
    so did the header, while CC had shipped three releases past it. Adding the
    entries without bumping the header (or vice versa) now fails here.
    """
    body = DOC.read_text(encoding="utf-8")
    match = DOC_RANGE_RE.search(body)
    assert match, "could not find the 'tested against Claude Code **X → Y**' sentence"
    _, stated_max = match.groups()

    newest = max((v for entry in _entry_versions() for v in entry), key=_ver)
    assert stated_max == newest, (
        f"the header advertises coverage through {stated_max} but the newest "
        f"documented entry is {newest} — bump whichever is stale"
    )


def test_matrix_entries_are_in_descending_order_without_duplicates() -> None:
    """Newest first, each version documented once.

    Ordering is judged on each heading's FIRST version: a collapsed heading is
    filed under the release it starts at, so `### v2.1.184 / v2.1.188 / ...`
    correctly sits between v2.1.185 and v2.1.183.
    """
    firsts = [entry[0] for entry in _entry_versions()]
    for newer, older in zip(firsts, firsts[1:]):
        assert _ver(newer) > _ver(older), (
            f"matrix entry v{older} follows v{newer} — entries must be newest-first, "
            "and a new entry pasted into the wrong place is invisible otherwise"
        )

    seen: dict[str, int] = {}
    for entry in _entry_versions():
        for version in entry:
            seen[version] = seen.get(version, 0) + 1
    duplicates = sorted(v for v, n in seen.items() if n > 1)
    assert not duplicates, f"these releases are documented more than once: {duplicates}"


def test_claude_md_agrees_with_the_tracked_doc() -> None:
    """`CLAUDE.md` restates the range, so it can drift away from the real record.

    It is gitignored and user-managed (see `.gitignore`), so it is legitimately
    absent for a fresh clone and in CI — skip rather than fail there. When it IS
    present it must not contradict the tracked document.
    """
    if not CLAUDE_MD.exists():
        pytest.skip("CLAUDE.md is gitignored and user-managed; absent in this checkout")

    doc_match = DOC_RANGE_RE.search(DOC.read_text(encoding="utf-8"))
    assert doc_match, "could not parse the range from the tracked doc"
    doc_min, doc_max = doc_match.groups()

    body = CLAUDE_MD.read_text(encoding="utf-8")
    range_match = CLAUDE_RANGE_RE.search(body)
    if range_match is None:
        pytest.skip("this CLAUDE.md does not restate the CC compatibility range")

    assert range_match.groups() == (doc_min, doc_max), (
        f"CLAUDE.md claims {range_match.group(1)} → {range_match.group(2)} but "
        f"docs/CC-COMPATIBILITY.md is the record and says {doc_min} → {doc_max}"
    )

    latest_match = CLAUDE_LATEST_RE.search(body)
    if latest_match is not None:
        assert latest_match.group(1) == doc_max, (
            f"CLAUDE.md says 'Latest: v{latest_match.group(1)}' but the newest "
            f"documented release is {doc_max}"
        )
