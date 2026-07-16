"""Parity + contract pins from the 2026-07-16 xhigh review.

Covers:
  - scope_path_from_discovery_source (pss_discover) mirrors
    temporal.rs::scope_path_from_discovery_source byte-for-byte — silent
    drift re-introduces the DI-4 manifest no-op bug fixed in ea09f30
  - detect_platform (pss_paths) returns a full binary FILENAME, the
    load-bearing contract resolve_binary (pss_reindex) depends on
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pss_discover import scope_path_from_discovery_source  # noqa: E402
from pss_paths import detect_platform  # noqa: E402


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # The five recognized prefixes strip to the remainder — must match
        # the Rust impl at rust/skill-suggester/src/temporal.rs (the mirror
        # this function documents byte-parity with).
        ("project:/Users/me/proj", "/Users/me/proj"),
        ("local:/Users/me/proj", "/Users/me/proj"),
        ("plugin:pss@emasoft-plugins", "pss@emasoft-plugins"),
        ("user:/Users/me/.claude", "/Users/me/.claude"),
        ("marketplace:emasoft-plugins", "emasoft-plugins"),
        # Composite remainders pass through UNSPLIT (mirrors the Rust test
        # scope_path_from_discovery_source_preserves_composite).
        ("project:projA/plugin:foo", "projA/plugin:foo"),
        # Colon-less legacy sources (bare "user") yield "" on BOTH sides —
        # a consistent-by-design blind spot of the removal manifest (F7).
        ("user", ""),
        ("project", ""),
        ("", ""),
        ("unknown:thing", ""),
    ],
)
def test_scope_path_parity_with_rust(source: str, expected: str) -> None:
    """Each source maps exactly as the Rust mirror does — drift breaks DI-4."""
    assert scope_path_from_discovery_source(source) == expected


def test_detect_platform_returns_binary_filename() -> None:
    """resolve_binary joins plugin_root/bin/<name> directly — the name MUST be
    the full binary filename (pss-<os>-<arch>[.exe]), never a bare platform
    slug like 'darwin-arm64'."""
    name = detect_platform()
    assert name.startswith("pss-"), name
    assert "/" not in name and "\\" not in name, name
