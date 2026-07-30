"""Contract tests for the six PSS skills that CPV flagged as having no
discoverable test (RC-TEST-COVERAGE): pss-agent-toml, pss-authoring,
pss-benchmark-agent, pss-cli-reference, pss-design-alignment, and
text-categorization-improver.

A SKILL.md is a data file, so what is genuinely verifiable about it is its
contract with the Claude Code loader and with PSS's own indexer:

* the frontmatter is parseable YAML carrying the required keys, and every key
  is one Claude Code actually understands (a typo like `user_invocable` is
  silently ignored by the loader — the skill then behaves as if the flag were
  never set);
* `name` matches the directory, because CC resolves a skill by directory and
  displays it by `name` — a mismatch makes the skill un-referenceable by the
  name it advertises;
* every relative markdown link resolves on disk and stays inside `skills/`,
  because a broken reference silently truncates progressive discovery: the
  agent reads "see references/foo.md", opens nothing, and proceeds with a
  partial protocol;
* no reference file is orphaned — an unlinked `references/*.md` is content the
  agent can never reach;
* the repo paths a skill documents as its Resources actually exist;
* PSS's own discovery pass can index each skill (dogfooding: the indexer and
  the skill files must agree).

Plus one regression guard: `pss-cli-reference` declares `context: fork` with an
explicit `background: false`. Per docs/CC-COMPATIBILITY.md, CC v2.1.218 made
forked skills run in the BACKGROUND by default; this skill is a synchronous
routing lookup (the caller needs the resolved `pss …` command inline before it
can run it), so PSS v3.10.9 added the opt-out. Dropping that one line would
silently make the skill async again — invisible in any smoke test.

No mocks: every assertion reads the real files shipped in this repo and, for
the discovery test, calls the real `pss_discover.discover_elements`.
"""

from __future__ import annotations

import platform
import re
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / "skills"
SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# The six skills CPV reported as untested.
TARGET_SKILLS = [
    "pss-agent-archetypes",
    "pss-agent-toml",
    "pss-authoring",
    "pss-benchmark-agent",
    "pss-cli-reference",
    "pss-design-alignment",
    "text-categorization-improver",
]

# Frontmatter keys Claude Code understands on a SKILL.md. Anything outside this
# set is either a typo or an unsupported invention — both are silently dropped
# by the loader, so the skill misbehaves with no error anywhere.
KNOWN_FRONTMATTER_KEYS = {
    "name",
    "description",
    "argument-hint",
    "user-invocable",
    "context",
    "background",
    "allowed-tools",
    "disable-model-invocation",
    "model",
    "license",
    "metadata",
    "version",
}

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

# Description ceiling enforced by the Claude Code skill loader.
MAX_DESCRIPTION_CHARS = 1024
MAX_NAME_CHARS = 64


def _skill_md(skill: str) -> Path:
    return SKILLS_DIR / skill / "SKILL.md"


def _frontmatter(skill: str) -> dict:
    """Parse the YAML frontmatter block of a skill, failing loudly if absent."""
    text = _skill_md(skill).read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{skill}: SKILL.md must open with a `---` frontmatter fence"
    end = text.find("\n---\n", 3)
    assert end != -1, f"{skill}: SKILL.md frontmatter block is never closed"
    data = yaml.safe_load(text[4:end])
    assert isinstance(data, dict), f"{skill}: frontmatter must parse to a mapping, got {type(data)}"
    return data


def _local_links(md: Path) -> list[str]:
    """Relative (non-URL, non-anchor) markdown link targets in one file."""
    out = []
    for match in MD_LINK_RE.finditer(md.read_text(encoding="utf-8")):
        target = match.group(1).split()[0].split("#")[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        out.append(target)
    return out


def _bad_links(skill_dir: Path, boundary: Path) -> tuple[list[str], list[str]]:
    """Return (unresolvable, escaping) relative links across a skill's markdown.

    `boundary` is the directory every link must stay under once resolved.
    """
    broken: list[str] = []
    escaping: list[str] = []
    for md in sorted(skill_dir.rglob("*.md")):
        for target in _local_links(md):
            resolved = (md.parent / target).resolve()
            where = f"{md.name} -> {target}"
            if not resolved.exists():
                broken.append(where)
            elif boundary.resolve() not in resolved.parents:
                escaping.append(where)
    return broken, escaping


def _orphan_references(skill_dir: Path) -> list[str]:
    """references/*.md files unreachable by following links out of SKILL.md."""
    reachable: set[Path] = set()
    frontier = [skill_dir / "SKILL.md"]
    while frontier:
        md = frontier.pop()
        for target in _local_links(md):
            resolved = (md.parent / target).resolve()
            if resolved.suffix == ".md" and resolved.exists() and resolved not in reachable:
                reachable.add(resolved)
                frontier.append(resolved)

    on_disk = {p.resolve() for p in (skill_dir / "references").glob("*.md")}
    return sorted(p.name for p in on_disk - reachable)


@pytest.mark.parametrize("skill", TARGET_SKILLS)
def test_frontmatter_parses_with_required_and_known_keys(skill: str) -> None:
    """Each skill's frontmatter is valid YAML, carries name+description, and uses
    only frontmatter keys Claude Code understands (a typo'd key is dropped
    silently, so the skill would misbehave with no error)."""
    fm = _frontmatter(skill)

    assert "name" in fm, f"{skill}: frontmatter is missing the required `name` key"
    assert "description" in fm, f"{skill}: frontmatter is missing the required `description` key"

    unknown = set(fm) - KNOWN_FRONTMATTER_KEYS
    assert not unknown, (
        f"{skill}: unsupported frontmatter key(s) {sorted(unknown)} — "
        "Claude Code ignores these silently"
    )


@pytest.mark.parametrize("skill", TARGET_SKILLS)
def test_name_matches_directory_and_is_valid_slug(skill: str) -> None:
    """`name` equals the containing directory and is a lowercase kebab-case slug
    within the length limit — CC resolves the skill by directory but advertises
    it by `name`, so a mismatch makes it un-referenceable."""
    name = _frontmatter(skill)["name"]
    assert name == skill, f"{skill}: frontmatter name {name!r} does not match its directory"
    assert NAME_RE.match(name), f"{skill}: name {name!r} is not lowercase kebab-case"
    assert len(name) <= MAX_NAME_CHARS, f"{skill}: name exceeds {MAX_NAME_CHARS} chars"


@pytest.mark.parametrize("skill", TARGET_SKILLS)
def test_description_is_a_usable_single_line_string(skill: str) -> None:
    """`description` is a non-empty single-line string within the loader's
    1024-char ceiling — it is the only text PSS and CC match a prompt against,
    so an empty or over-long one breaks activation."""
    description = _frontmatter(skill)["description"]
    assert isinstance(description, str), f"{skill}: description must be a string, got {type(description)}"
    assert description.strip(), f"{skill}: description is empty"
    assert "\n" not in description, f"{skill}: description must be a single line"
    assert len(description) <= MAX_DESCRIPTION_CHARS, (
        f"{skill}: description is {len(description)} chars, over the {MAX_DESCRIPTION_CHARS} limit"
    )


@pytest.mark.parametrize("skill", TARGET_SKILLS)
def test_declared_loader_flags_have_valid_values(skill: str) -> None:
    """`user-invocable`, `background` parse as real booleans (not the strings
    "false"/"true") and `context`, when present, is a value CC accepts — a
    string "false" is truthy and would flip the flag's meaning."""
    fm = _frontmatter(skill)

    for flag in ("user-invocable", "background", "disable-model-invocation"):
        if flag in fm:
            assert isinstance(fm[flag], bool), (
                f"{skill}: `{flag}: {fm[flag]!r}` is a {type(fm[flag]).__name__}, not a bool — "
                'a quoted "false" is truthy and inverts the flag'
            )

    if "context" in fm:
        assert fm["context"] in {"fork"}, f"{skill}: unknown context value {fm['context']!r}"


def test_pss_cli_reference_keeps_synchronous_fork_optout() -> None:
    """REGRESSION (PSS v3.10.9): pss-cli-reference must keep `context: fork` WITH
    `background: false`. CC v2.1.218 backgrounds forked skills by default, which
    detaches the resolved `pss …` command from the caller that must run it."""
    fm = _frontmatter("pss-cli-reference")
    assert fm.get("context") == "fork", "pss-cli-reference must stay a forked-context skill"
    assert "background" in fm, (
        "pss-cli-reference lost its `background: false` opt-out — CC v2.1.218 would "
        "silently run this synchronous routing lookup in the background"
    )
    assert fm["background"] is False, (
        f"pss-cli-reference `background` must be the boolean False, got {fm['background']!r}"
    )


@pytest.mark.parametrize("skill", TARGET_SKILLS)
def test_every_relative_link_resolves_inside_the_skills_tree(skill: str) -> None:
    """Every relative markdown link in the skill (SKILL.md and its references)
    points at a file that exists and lives under skills/ — a broken link
    silently truncates progressive discovery, and a link escaping skills/ breaks
    once the plugin is installed elsewhere."""
    broken, escaping = _bad_links(SKILLS_DIR / skill, SKILLS_DIR)
    assert not broken, f"{skill}: unresolvable relative link(s): {broken}"
    assert not escaping, f"{skill}: link(s) escaping the skills/ tree: {escaping}"


@pytest.mark.parametrize("skill", TARGET_SKILLS)
def test_no_orphan_reference_files(skill: str) -> None:
    """Every references/*.md is reachable from SKILL.md (directly or through
    another reference) — an unlinked reference is content the agent can never
    discover, which is exactly the progressive-discovery failure PSS authoring
    rules forbid."""
    skill_dir = SKILLS_DIR / skill
    assert (skill_dir / "references").is_dir(), (
        f"{skill}: references/ directory is gone — every target skill ships one"
    )
    orphans = _orphan_references(skill_dir)
    assert not orphans, f"{skill}: reference file(s) never linked from SKILL.md: {orphans}"


@pytest.mark.parametrize(
    ("skill", "documented_path"),
    [
        ("pss-agent-toml", "schemas/pss-agent-toml-schema.json"),
        ("pss-agent-toml", "scripts/pss_validate_agent_toml.py"),
        ("pss-authoring", "schemas/pss-categories.json"),
        ("pss-benchmark-agent", "rust/skill-suggester/src/main.rs"),
        ("pss-benchmark-agent", "scripts/pss_agent_benchmark.py"),
        ("pss-cli-reference", "docs/pss-cli-reference.md"),
        ("pss-design-alignment", "scripts/pss_verify_profile.py"),
        ("pss-design-alignment", "schemas/pss-agent-toml-schema.json"),
    ],
)
def test_documented_repo_paths_exist_and_are_cited(skill: str, documented_path: str) -> None:
    """A repo path a skill names as a Resource is still cited in its SKILL.md and
    still exists — these are the files the agent is told to open, so a rename
    elsewhere in the repo must fail here rather than at agent runtime."""
    assert (REPO_ROOT / documented_path).exists(), (
        f"{skill} documents {documented_path}, which no longer exists in the repo"
    )
    body = _skill_md(skill).read_text(encoding="utf-8")
    assert documented_path in body, (
        f"{skill}: SKILL.md no longer cites {documented_path} — update this test's "
        "expectation together with the skill"
    )


@pytest.mark.skipif(
    platform.system().lower() not in {"darwin", "linux"},
    reason="pss-cli-reference documents a uname-based recipe, which is POSIX-only",
)
def test_pss_cli_reference_binary_recipe_resolves_on_this_platform() -> None:
    """The `bin/pss-$(uname -s|lower)-$(uname -m)` recipe that pss-cli-reference
    tells agents to run resolves to a binary actually shipped in bin/ — this is
    the skill's single executable instruction."""
    body = _skill_md("pss-cli-reference").read_text(encoding="utf-8")
    assert 'bin/pss-$(uname -s | tr \'[:upper:]\' \'[:lower:]\')-$(uname -m)' in body, (
        "pss-cli-reference no longer documents the lowercased uname binary recipe; "
        "update this test alongside the skill"
    )

    expected = f"pss-{platform.system().lower()}-{platform.machine()}"
    binary = REPO_ROOT / "bin" / expected
    assert binary.exists(), (
        f"the documented recipe resolves to bin/{expected}, which is not shipped"
    )
    assert binary.stat().st_mode & 0o111, f"bin/{expected} is not executable"


def test_all_target_skills_are_indexable_by_pss_discover() -> None:
    """PSS's own discovery pass indexes all six skills with their declared names
    and a non-empty description — dogfooding: if PSS cannot index its own
    skills, no consumer's skill of the same shape is indexable either."""
    import pss_discover

    elements = pss_discover.discover_elements([("project", "skill", SKILLS_DIR)])
    by_name = {e["name"]: e for e in elements}

    missing = [s for s in TARGET_SKILLS if s not in by_name]
    assert not missing, f"PSS discovery did not index its own skill(s): {missing}"

    for skill in TARGET_SKILLS:
        entry = by_name[skill]
        assert entry["type"] == "skill", f"{skill}: indexed as {entry['type']!r}, not 'skill'"
        assert entry["description"].strip(), f"{skill}: indexed with an empty description"
        assert Path(entry["path"]) == _skill_md(skill), (
            f"{skill}: indexed path {entry['path']} is not its SKILL.md"
        )


# --- detector self-checks -------------------------------------------------
# The two checks above pass today because the shipped skills are clean. That
# leaves an ambiguity a green suite cannot resolve: is the corpus healthy, or
# is the detector a no-op? These build a deliberately broken synthetic skill
# and require the same functions to flag it.


def test_link_detector_flags_a_broken_and_an_escaping_link(tmp_path: Path) -> None:
    """The link checker really reports an unresolvable link and one that escapes
    the skills/ boundary — proves the green result on the real skills is a
    verdict, not a detector that never fires."""
    boundary = tmp_path / "skills"
    skill = boundary / "synthetic"
    (skill / "references").mkdir(parents=True)
    (tmp_path / "outside.md").write_text("outside\n", encoding="utf-8")
    (skill / "references" / "real.md").write_text("real\n", encoding="utf-8")
    (skill / "SKILL.md").write_text(
        "[ok](references/real.md)\n"
        "[gone](references/missing.md)\n"
        "[out](../../outside.md)\n"
        "[web](https://example.com/x.md)\n",
        encoding="utf-8",
    )

    broken, escaping = _bad_links(skill, boundary)

    assert broken == ["SKILL.md -> references/missing.md"], f"unexpected broken set: {broken}"
    assert escaping == ["SKILL.md -> ../../outside.md"], f"unexpected escaping set: {escaping}"


def test_orphan_detector_flags_an_unlinked_reference_and_follows_transitive_links(
    tmp_path: Path,
) -> None:
    """The orphan checker reports a reference nothing links to, while treating a
    reference reached only via another reference as reachable — the transitive
    walk is what makes the real-skill result trustworthy."""
    skill = tmp_path / "synthetic"
    (skill / "references").mkdir(parents=True)
    (skill / "SKILL.md").write_text("[a](references/a.md)\n", encoding="utf-8")
    (skill / "references" / "a.md").write_text("[b](b.md)\n", encoding="utf-8")
    (skill / "references" / "b.md").write_text("leaf\n", encoding="utf-8")
    (skill / "references" / "lonely.md").write_text("nobody links here\n", encoding="utf-8")

    assert _orphan_references(skill) == ["lonely.md"]
