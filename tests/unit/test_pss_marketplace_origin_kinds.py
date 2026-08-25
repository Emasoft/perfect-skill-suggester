"""`_marketplace_origins` must disambiguate EVERY marketplace source kind.

Claude Code keeps adding source kinds — `archive` (2.1.224), marketplace
`command` (2.1.229), GitLab repo URLs (2.1.232). The origin map used to branch on
a `github`/`git`/`directory` allow-list, so every newer kind fell through to `""`
and two same-named marketplaces became indistinguishable in the suggestion line.
These tests pin the field-shaped behaviour (repo → owner, url → host+org,
directory → folder) so a future kind name is covered without editing the code.

No mocks: each case writes a real `known_marketplaces.json` and reads it back
through the real function.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"


def _load_discover():
    spec = importlib.util.spec_from_file_location(
        "pss_discover_origin_test", SCRIPTS_DIR / "pss_discover.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _origins_for(discover, tmp_path: Path, entries: dict) -> dict[str, str]:
    """Write a known_marketplaces.json into a fake ~/.claude and read the map."""
    claude_dir = tmp_path / ".claude"
    (claude_dir / "plugins").mkdir(parents=True, exist_ok=True)
    (claude_dir / "plugins" / "known_marketplaces.json").write_text(
        json.dumps(entries), encoding="utf-8"
    )
    discover.get_claude_dir = lambda: claude_dir  # type: ignore[assignment]
    discover._marketplace_origin_memo = None
    return discover._marketplace_origins()


@pytest.fixture()
def discover():
    """Fresh pss_discover module per test (the origin map is memoised)."""
    return _load_discover()


def test_github_source_still_yields_the_repo_owner(discover, tmp_path: Path) -> None:
    """A `github` source keeps resolving to the repo OWNER (no regression)."""
    origins = _origins_for(
        discover, tmp_path, {"mp": {"source": {"source": "github", "repo": "acme/plugins"}}}
    )
    assert origins["mp"] == "acme"


def test_git_url_source_still_yields_host_and_org(discover, tmp_path: Path) -> None:
    """A `git` source keeps resolving to host+org parsed from the clone URL."""
    origins = _origins_for(
        discover,
        tmp_path,
        {"mp": {"source": {"source": "git", "url": "https://github.com/acme/plugins.git"}}},
    )
    assert origins["mp"] == "github.com/acme"


def test_gitlab_repo_source_yields_top_group(discover, tmp_path: Path) -> None:
    """A GitLab source carrying `repo` resolves to its top group, not ''."""
    origins = _origins_for(
        discover,
        tmp_path,
        {"mp": {"source": {"source": "gitlab", "repo": "group/subgroup/plugins"}}},
    )
    assert origins["mp"] == "group"


def test_gitlab_url_source_yields_host_and_group(discover, tmp_path: Path) -> None:
    """A GitLab source carrying a bare `url` resolves to host+group, not ''."""
    origins = _origins_for(
        discover,
        tmp_path,
        {"mp": {"source": {"source": "gitlab", "url": "https://gitlab.com/group/plugins"}}},
    )
    assert origins["mp"] == "gitlab.com/group"


def test_archive_source_yields_host_and_path_segment(discover, tmp_path: Path) -> None:
    """An `archive` source (CC 2.1.224, zip over HTTPS) resolves to host+segment."""
    origins = _origins_for(
        discover,
        tmp_path,
        {"mp": {"source": {"source": "archive", "url": "https://cdn.example.com/acme/kit.zip"}}},
    )
    assert origins["mp"] == "cdn.example.com/acme"


def test_directory_source_still_wins_over_repo_and_url(discover, tmp_path: Path) -> None:
    """A local `directory` resolves to its FOLDER even when it also carries a repo."""
    origins = _origins_for(
        discover,
        tmp_path,
        {
            "mp": {
                "source": {
                    "source": "directory",
                    "path": "/work/local-marketplace",
                    "repo": "acme/plugins",
                }
            }
        },
    )
    assert origins["mp"] == "work/local-marketplace"


def test_command_source_without_repo_or_url_is_empty_not_wrong(
    discover, tmp_path: Path
) -> None:
    """A `command` source (CC 2.1.229) carries no locator, so it yields no origin."""
    origins = _origins_for(
        discover,
        tmp_path,
        {"mp": {"source": {"source": "command", "command": "/usr/local/bin/print-plugin-dir"}}},
    )
    assert origins.get("mp", "") == ""
