"""Escape-function tests for pss_cozodb.

Covers the edge cases the v3.2.0 audit flagged:
  - null bytes can't reach the CozoDB parser unescaped
  - newlines/CR/tab become literal escape sequences so single-line queries stay single-line
  - backslashes double up exactly once (no double-escape)
  - single quotes are escaped in _escape; double quotes in _escape_cozo_str
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from pss_cozodb import _escape, _escape_cozo_str  # noqa: E402


class TestEscapeSingleQuoteMode:
    """`_escape` is used inside Cozo single-quoted string literals."""

    def test_plain_ascii_unchanged(self) -> None:
        assert _escape("hello world") == "hello world"

    def test_single_quote_escaped(self) -> None:
        assert _escape("it's") == r"it\'s"

    def test_double_quote_untouched(self) -> None:
        # We're in single-quoted mode — double-quotes are fine as-is
        assert _escape('say "hi"') == 'say "hi"'

    def test_backslash_doubled_once(self) -> None:
        assert _escape("a\\b") == "a\\\\b"

    def test_null_byte_escaped(self) -> None:
        assert _escape("a\x00b") == "a\\u0000b"

    def test_newline_escaped(self) -> None:
        assert _escape("line1\nline2") == "line1\\nline2"

    def test_crlf_escaped(self) -> None:
        assert _escape("a\r\nb") == "a\\r\\nb"

    def test_tab_escaped(self) -> None:
        assert _escape("col1\tcol2") == "col1\\tcol2"

    def test_backslash_then_single_quote_does_not_double_escape(self) -> None:
        # Backslash must be escaped FIRST so later single-quote escape does
        # not become a doubled backslash.
        assert _escape("a\\'b") == "a\\\\\\'b"

    def test_unicode_passes_through(self) -> None:
        # Non-ASCII Unicode is valid inside Cozo string literals
        assert _escape("café → λ") == "café → λ"


class TestEscapeCozoStrDoubleQuoteMode:
    """`_escape_cozo_str` is used inside `<- [[...]]` inline data (double-quoted)."""

    def test_plain_ascii_unchanged(self) -> None:
        assert _escape_cozo_str("hello") == "hello"

    def test_double_quote_escaped(self) -> None:
        assert _escape_cozo_str('say "hi"') == 'say \\"hi\\"'

    def test_single_quote_untouched(self) -> None:
        # Double-quoted mode — single quotes are fine as-is
        assert _escape_cozo_str("it's fine") == "it's fine"

    def test_backslash_doubled_once(self) -> None:
        assert _escape_cozo_str("a\\b") == "a\\\\b"

    def test_null_byte_escaped(self) -> None:
        assert _escape_cozo_str("a\x00b") == "a\\u0000b"

    def test_newline_escaped(self) -> None:
        assert _escape_cozo_str("a\nb") == "a\\nb"

    def test_control_chars_all_escaped(self) -> None:
        # Combined — ensure none of NUL/CR/LF/tab slip through
        inp = "x\x00\r\n\tx"
        out = _escape_cozo_str(inp)
        for dangerous in ("\x00", "\r", "\n", "\t"):
            assert dangerous not in out, (
                f"escape_cozo_str leaked control char {dangerous!r}"
            )


class TestEscapeReversibility:
    """Round-trip: after escaping, the backslash count must equal the expected
    increase (no silent double-escape that would lose info on unescape)."""

    def test_no_double_escape(self) -> None:
        orig = "a\\b\\\\c"
        escaped = _escape(orig)
        # Each backslash doubles exactly once → 3 backslashes become 6
        assert escaped.count("\\") == orig.count("\\") * 2
