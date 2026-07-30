"""Contract tests for every slash command shipped under ``commands/``.

Closes the CPV ``[RC-TEST-COVERAGE]`` gap for the command surface. Each of the
11 commands is a markdown file that Claude Code loads verbatim: its frontmatter
is parsed by the plugin loader, and its body tells the model which script or
binary to invoke with which flags. Nothing in that chain is compiled, so a
renamed script, a dropped binary, or a flag that was removed from an argparse
parser stays silently broken until a user runs the command.

These tests exercise the real artifacts — real YAML, real files on disk, real
``--help`` output from the real scripts and the real Rust binary. Nothing is
mocked.

Covered commands (all of ``commands/*.md``):
    pss-add-element, pss-add-to-index, pss-added-since, pss-change-agent-profile,
    pss-get-description, pss-make-plugin-from-profile, pss-reindex-skills,
    pss-search, pss-setup-agent, pss-status
"""

from __future__ import annotations

import platform
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
COMMANDS = ROOT / "commands"
SCRIPTS = ROOT / "scripts"
BIN = ROOT / "bin"

#: Top-level command definitions — one markdown file per slash command.
COMMAND_FILES = sorted(COMMANDS.glob("*.md"))

#: Every markdown file under commands/, including the per-command reference
#: subdirectories (e.g. commands/pss-status/execution-protocol.md).
ALL_COMMAND_DOCS = sorted(COMMANDS.rglob("*.md"))

#: Tool names the Claude Code loader accepts in `allowed-tools`. Anything else
#: must be an MCP tool id (`mcp__<server>__<tool>`).
KNOWN_TOOLS = {
    "Agent",
    "Bash",
    "BashOutput",
    "Edit",
    "Glob",
    "Grep",
    "KillShell",
    "NotebookEdit",
    "Read",
    "Skill",
    "SlashCommand",
    "Task",
    "TodoWrite",
    "WebFetch",
    "WebSearch",
    "Write",
}

VALID_EFFORT = {"low", "medium", "high"}

# MCP tool ids are `mcp__<server>__<tool>`; the server segment routinely contains
# hyphens (e.g. mcp__plugin_llm-externalizer_llm-externalizer__code_task).
MCP_TOOL_RE = re.compile(r"^mcp__[A-Za-z0-9_-]+__[A-Za-z0-9_-]+$")
#: Concrete (non-templated) binary references such as `bin/pss-darwin-arm64`.
#: Templated forms (`bin/pss-${OS}-${ARCH}`, `bin/pss-<platform>`) cannot match
#: because `$`, `{` and `<` are outside the character class.
BINARY_REF_RE = re.compile(r"bin/(pss-[a-z0-9_]+-[a-z0-9_]+(?:\.exe)?)")
SCRIPT_REF_RE = re.compile(r"scripts/([a-z0-9_]+\.py)")
FLAG_IN_BACKTICKS_RE = re.compile(r"`(--[a-z][a-z0-9-]*)")


def _frontmatter(path: Path) -> dict:
    """Parse the YAML frontmatter block of a command markdown file."""
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.name}: no frontmatter opening fence"
    end = text.find("\n---", 4)
    assert end != -1, f"{path.name}: unterminated frontmatter block"
    data = yaml.safe_load(text[4:end])
    assert isinstance(data, dict), f"{path.name}: frontmatter is not a mapping"
    return data


def _body(path: Path) -> str:
    """Return the command markdown body with the frontmatter block stripped."""
    text = path.read_text(encoding="utf-8")
    end = text.find("\n---", 4)
    return text[end + 4 :] if end != -1 else text


@lru_cache(maxsize=None)
def _script_help(script: str) -> str:
    """Run `<script> --help` in the test interpreter and return its output."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / script), "--help"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"{script} --help exited {proc.returncode}: {proc.stderr}"
    return proc.stdout


def _platform_binary() -> Path | None:
    """Resolve the pss binary for the running platform, or None if absent."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    arch = {"aarch64": "arm64", "amd64": "x86_64"}.get(machine, machine)
    name = "pss-windows-x86_64.exe" if system == "windows" else f"pss-{system}-{arch}"
    candidate = BIN / name
    return candidate if candidate.is_file() else None


@lru_cache(maxsize=None)
def _binary_help(subcommand: str = "") -> str:
    """Run `pss [subcommand] --help` against the real binary for this platform."""
    binary = _platform_binary()
    if binary is None:
        pytest.skip(f"no pss binary for {platform.system()}/{platform.machine()}")
    argv = [str(binary)] + ([subcommand] if subcommand else []) + ["--help"]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, f"pss {subcommand} --help exited {proc.returncode}"
    return proc.stdout


@lru_cache(maxsize=None)
def _binary_subcommands() -> frozenset[str]:
    """Parse the subcommand list out of the binary's top-level --help."""
    verbs = set()
    for line in _binary_help().splitlines():
        match = re.match(r"^  ([a-z][a-z0-9-]*)\s{2,}\S", line)
        if match:
            verbs.add(match.group(1))
    assert "search" in verbs, "failed to parse subcommands from pss --help"
    return frozenset(verbs)


#: Commands that legitimately accept NO arguments, and therefore must not
#: declare an `argument-hint`. The suggestion-mode toggles are pure switches:
#: the verb itself carries the whole intent.
NO_ARGUMENT_COMMANDS = frozenset(
    {
        "pss-suggest-agents-off",
        "pss-suggest-agents-on",
        "pss-suggest-skills-off",
        "pss-suggest-skills-on",
    }
)


def _cmd(name: str) -> Path:
    path = COMMANDS / f"{name}.md"
    assert path.is_file(), f"missing command file {path}"
    return path


def test_command_set_is_the_expected_fifteen() -> None:
    """Every shipped slash command is covered by this module's contract tests."""
    assert {p.stem for p in COMMAND_FILES} == {
        "pss-add-element",
        "pss-add-to-index",
        "pss-added-since",
        "pss-change-agent-profile",
        "pss-get-description",
        "pss-make-agent",
        "pss-make-plugin-from-profile",
        "pss-reindex-skills",
        "pss-search",
        "pss-setup-agent",
        "pss-status",
        # Suggestion-mode toggles (v3.11): one mutually-exclusive setting
        # driven by four verbs — see rust/skill-suggester/src/suggest_mode.rs.
        "pss-suggest-agents-off",
        "pss-suggest-agents-on",
        "pss-suggest-skills-off",
        "pss-suggest-skills-on",
    }


@pytest.mark.parametrize("path", COMMAND_FILES, ids=lambda p: p.stem)
def test_command_frontmatter_is_valid(path: Path) -> None:
    """Command frontmatter declares a filename-matching name, description and effort."""
    fm = _frontmatter(path)
    assert fm.get("name") == path.stem, f"{path.name}: name must equal the filename stem"
    description = fm.get("description")
    assert isinstance(description, str) and description.strip(), "description must be non-empty"
    assert fm.get("effort") in VALID_EFFORT, f"{path.name}: effort={fm.get('effort')!r}"
    hint = fm.get("argument-hint")
    if path.stem in NO_ARGUMENT_COMMANDS:
        # A command that takes no arguments must not invent a hint — an
        # argument-hint on an argument-less command tells the user to type
        # something the command ignores. Asserting its ABSENCE (rather than
        # merely skipping) keeps NO_ARGUMENT_COMMANDS honest: give one of these
        # an argument later and this test forces the set to be updated.
        assert hint is None, f"{path.name}: takes no arguments, so it must not declare argument-hint"
        return
    assert isinstance(hint, str) and hint.strip(), f"{path.name}: argument-hint missing"
    assert hint.count("[") == hint.count("]"), f"{path.name}: unbalanced [] in argument-hint"
    assert hint.count("<") == hint.count(">"), f"{path.name}: unbalanced <> in argument-hint"


@pytest.mark.parametrize("path", COMMAND_FILES, ids=lambda p: p.stem)
def test_command_allowed_tools_are_well_formed(path: Path) -> None:
    """`allowed-tools` is a duplicate-free list of real Claude Code or MCP tool ids."""
    tools = _frontmatter(path).get("allowed-tools")
    assert isinstance(tools, list) and tools, f"{path.name}: allowed-tools must be a non-empty list"
    assert len(tools) == len(set(tools)), f"{path.name}: duplicate entries in allowed-tools"
    for tool in tools:
        assert isinstance(tool, str) and tool.strip(), f"{path.name}: blank allowed-tools entry"
        assert tool in KNOWN_TOOLS or MCP_TOOL_RE.match(tool), f"{path.name}: unknown tool {tool!r}"


@pytest.mark.parametrize("path", COMMAND_FILES, ids=lambda p: p.stem)
def test_command_relative_markdown_links_resolve(path: Path) -> None:
    """Every relative .md reference link in a command body points at a real file."""
    for target in re.findall(r"\]\((?!https?:)([A-Za-z0-9_./-]+\.md)\)", _body(path)):
        assert (path.parent / target).is_file(), f"{path.name}: dangling link {target}"


def test_every_referenced_script_exists() -> None:
    """Every `scripts/*.py` path named in any command doc exists on disk."""
    referenced = {
        (doc, script)
        for doc in ALL_COMMAND_DOCS
        for script in SCRIPT_REF_RE.findall(doc.read_text(encoding="utf-8"))
    }
    # Guard against a vacuous pass if the extraction regex ever stops matching.
    assert len(referenced) >= 8, f"script reference extraction regressed: {len(referenced)} hits"
    missing = sorted(
        f"{doc.relative_to(ROOT)} -> scripts/{script}"
        for doc, script in referenced
        if not (SCRIPTS / script).is_file()
    )
    assert not missing, f"commands reference nonexistent scripts: {missing}"


def test_every_referenced_binary_exists() -> None:
    """Every concrete `bin/pss-<os>-<arch>` path named in a command doc is shipped."""
    referenced = {
        name
        for doc in ALL_COMMAND_DOCS
        for name in BINARY_REF_RE.findall(doc.read_text(encoding="utf-8"))
    }
    assert referenced, "expected at least one concrete binary reference in commands/"
    missing = sorted(name for name in referenced if not (BIN / name).is_file())
    assert not missing, f"commands reference nonexistent binaries: {missing}"


def test_every_referenced_binary_subcommand_exists() -> None:
    """Rust subcommands invoked by the commands are real verbs of the shipped binary."""
    verbs = _binary_subcommands()
    # The bare `pss <verb>` alternative matters: a fenced ```bash block is the
    # most natural way to document a CLI, and without it such an invocation is
    # never extracted — so this test would PASS BY NOT LOOKING at the newest
    # command. The lookbehind keeps `bin/pss-darwin-arm64 …` and `pss.py …`
    # from being read as the bare form.
    referenced = {
        verb
        for doc in ALL_COMMAND_DOCS
        for verb in re.findall(
            r'(?:\$\{?BINARY\}?|\$\{?BIN\}?|"\$BIN"|"\$\{BINARY\}"|`pss'
            r'|(?<![\w./-])pss)"?\s+([a-z][a-z0-9-]*)',
            doc.read_text(encoding="utf-8"),
        )
    }
    # `pss --pass1-batch` style global flags never match the verb regex.
    assert {"search", "health", "get", "make-agent"} <= referenced, "verb extraction regressed"
    unknown = sorted(v for v in referenced if v not in verbs)
    assert not unknown, f"commands invoke unknown pss subcommands: {unknown}"


# --------------------------------------------------------------------------
# Per-command argument contracts: documented flags vs. what the target accepts
# --------------------------------------------------------------------------


def test_pss_add_element_flags_and_types_match_script() -> None:
    """/pss-add-element documents only flags and --type values pss_add_element.py accepts."""
    doc = _cmd("pss-add-element").read_text(encoding="utf-8")
    help_text = _script_help("pss_add_element.py")
    for flag in ("--type", "--source", "--plugin", "--validate", "--force", "--dry-run"):
        assert flag in doc, f"pss-add-element.md stopped documenting {flag}"
        assert flag in help_text, f"pss_add_element.py no longer accepts {flag}"
    documented_types = re.search(r"Element type: (`[^|]+)", doc)
    assert documented_types, "pss-add-element.md lost its --type value table row"
    for element_type in re.findall(r"`([a-z-]+)`", documented_types.group(1)):
        assert element_type in help_text, f"pss_add_element.py rejects documented type {element_type}"


def test_pss_make_plugin_from_profile_contract_matches_script() -> None:
    """/pss-make-plugin-from-profile's positional profile plus --output/--name are accepted."""
    doc = _cmd("pss-make-plugin-from-profile").read_text(encoding="utf-8")
    help_text = _script_help("pss_make_plugin.py")
    assert "profile" in help_text, "pss_make_plugin.py lost its positional profile argument"
    for flag in ("--output", "--name"):
        assert flag in doc, f"command doc stopped documenting {flag}"
        assert flag in help_text, f"pss_make_plugin.py no longer accepts {flag}"


def test_pss_reindex_skills_argument_hint_matches_script() -> None:
    """/pss-reindex-skills' only documented flag is the one pss_reindex.py accepts."""
    fm = _frontmatter(_cmd("pss-reindex-skills"))
    hint_flags = set(re.findall(r"--[a-z][a-z0-9-]*", fm["argument-hint"]))
    assert hint_flags == {"--exclude-inactive-plugins"}, f"unexpected hint flags {hint_flags}"
    help_text = _script_help("pss_reindex.py")
    for flag in hint_flags:
        assert flag in help_text, f"pss_reindex.py no longer accepts {flag}"


def test_pss_status_run_tests_invokes_a_real_e2e_entrypoint() -> None:
    """/pss-status --run-tests maps to pss_test_e2e.py --verbose, which is runnable."""
    proto = (COMMANDS / "pss-status" / "execution-protocol.md").read_text(encoding="utf-8")
    assert "scripts/pss_test_e2e.py" in proto, "status protocol lost its e2e script reference"
    assert re.search(r"pss_test_e2e\.py['\"]?\s+--verbose", proto), "e2e call lost --verbose"
    assert "--verbose" in _script_help("pss_test_e2e.py")


def test_pss_search_documented_options_are_accepted_by_the_binary() -> None:
    """Every flag in /pss-search's option table is a real `pss search` option."""
    doc = _cmd("pss-search").read_text(encoding="utf-8")
    documented = set(FLAG_IN_BACKTICKS_RE.findall(doc))
    assert {"--top", "--type", "--domain", "--language", "--format"} <= documented
    help_text = _binary_help("search")
    unknown = sorted(flag for flag in documented if flag not in help_text)
    assert not unknown, f"/pss-search documents flags `pss search` rejects: {unknown}"


def test_pss_added_since_options_and_sibling_verbs_exist() -> None:
    """/pss-added-since maps to `list-added-since` and its documented siblings exist."""
    doc = _cmd("pss-added-since").read_text(encoding="utf-8")
    assert re.search(r'"\$BIN"\s+list-added-since', doc), "execution block lost the verb"
    help_text = _binary_help("list-added-since")
    for flag in ("--limit", "--json"):
        assert flag in doc and flag in help_text, f"{flag} drifted for list-added-since"
    verbs = _binary_subcommands()
    for sibling in ("list-added-between", "list-updated-since"):
        assert sibling in doc, f"pss-added-since.md stopped mentioning {sibling}"
        assert sibling in verbs, f"binary no longer provides {sibling}"


def test_pss_get_description_options_are_accepted_by_the_binary() -> None:
    """/pss-get-description's --batch and --format map onto `pss get-description`."""
    doc = _cmd("pss-get-description").read_text(encoding="utf-8")
    help_text = _binary_help("get-description")
    for flag in ("--batch", "--format"):
        assert flag in doc, f"pss-get-description.md stopped documenting {flag}"
        assert flag in help_text, f"`pss get-description` no longer accepts {flag}"
    proto = (COMMANDS / "pss-get-description" / "execution-protocol.md").read_text(encoding="utf-8")
    assert "get-description" in proto, "execution protocol lost the get-description verb"


def test_pss_setup_agent_platform_map_binaries_are_all_shipped() -> None:
    """Every binary in /pss-setup-agent's PLATFORM_MAP exists under bin/."""
    exec_doc = (COMMANDS / "pss-setup-agent" / "execution.md").read_text(encoding="utf-8")
    mapped = set(re.findall(r'"(pss-[a-z0-9_]+-[a-z0-9_]+(?:\.exe)?)"', exec_doc))
    assert len(mapped) >= 5, f"PLATFORM_MAP parse returned only {sorted(mapped)}"
    missing = sorted(name for name in mapped if not (BIN / name).is_file())
    assert not missing, f"PLATFORM_MAP points at missing binaries: {missing}"
    assert (ROOT / "agents" / "pss-agent-profiler.md").is_file(), "profiler agent missing"


def test_pss_change_agent_profile_verification_scripts_take_a_toml_positional() -> None:
    """/pss-change-agent-profile's verify+validate scripts accept the .agent.toml positional."""
    doc = _cmd("pss-change-agent-profile").read_text(encoding="utf-8")
    for script in ("pss_verify_profile.py", "pss_validate_agent_toml.py"):
        assert f"scripts/{script}" in doc, f"command doc stopped referencing {script}"
        assert "toml_file" in _script_help(script), f"{script} lost its toml_file positional"


def test_pss_add_to_index_pipeline_flags_are_accepted() -> None:
    """/pss-add-to-index's discover | enrich | merge pipeline flags all still exist."""
    proto = (COMMANDS / "pss-add-to-index" / "execution-protocol.md").read_text(encoding="utf-8")
    assert re.search(r"pss_discover\.py.*--jsonl.*--name", proto, re.S), "discover call drifted"
    for flag in ("--jsonl", "--name"):
        assert flag in _script_help("pss_discover.py"), f"pss_discover.py no longer accepts {flag}"
    assert "--batch-stdin" in proto, "merge step lost --batch-stdin"
    assert "--batch-stdin" in _script_help("pss_merge_queue.py")
    assert "--pass1-batch" in proto, "enrichment step lost --pass1-batch"
    assert "--pass1-batch" in _binary_help(), "binary no longer exposes --pass1-batch"
