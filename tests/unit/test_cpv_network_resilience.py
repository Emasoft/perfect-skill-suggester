"""Tests for scripts/cpv_network_resilience.py — the retry budget guard.

The load-bearing behaviour is *when* the module decides to burn a retry:
a permanent failure retried 30× wastes 3 minutes of a release pipeline, and a
transient failure NOT retried breaks the publish on a DNS hiccup. These tests
drive the real classifier and the real `subprocess.run` loop (a flaky child
process written to disk, counting its own invocations) — nothing is mocked,
because a mocked subprocess would prove nothing about the retry loop.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def _load_module(name: str, path: Path):
    """Load a script module by path so the test does not depend on PYTHONPATH."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def net():
    """Load cpv_network_resilience.py without running any CLI."""
    return _load_module(
        "cpv_network_resilience_under_test", SCRIPTS_DIR / "cpv_network_resilience.py"
    )


# A child process that records every invocation and fails with caller-chosen stderr.
_FLAKY_CHILD = """
import pathlib
import sys

pathlib.Path(sys.argv[1]).open("a").write("run\\n")
sys.stderr.write(sys.argv[2] + "\\n")
sys.exit(1)
"""


def _flaky_cmd(tmp_path: Path, counter: Path, stderr_text: str) -> list[str]:
    """Build an argv for a real child process that fails with `stderr_text`."""
    script = tmp_path / "flaky_child.py"
    script.write_text(_FLAKY_CHILD, encoding="utf-8")
    return [sys.executable, str(script), str(counter), stderr_text]


class TestTransientClassification:
    """`is_transient_subprocess_error` decides whether a retry is worth spending."""

    def test_network_signatures_retryable_but_permanent_ones_always_win(self, net) -> None:
        """Network stderr is transient; an auth/non-ff marker vetoes it even beside a 5xx."""
        for stderr in (
            "fatal: unable to access: Could not resolve host: github.com",
            "error: RPC failed; HTTP 502 curl 22 The requested URL returned error",
            "dial tcp 140.82.121.6:443: i/o timeout",
            "Get \"https://api.github.com/user\": context deadline exceeded",
            "You have exceeded a secondary rate limit exceeded",
        ):
            assert net.is_transient_subprocess_error(stderr, 1) is True, stderr
        # Both a permanent (403) and a transient (HTTP 500) marker present.
        mixed = "HTTP 500 while retrying\nremote: 403 Forbidden — bad credentials"
        assert net.is_transient_subprocess_error(mixed, 1) is False
        assert net.is_transient_subprocess_error("! [rejected] non-fast-forward", 1) is False
        # A zero return code is a success — never a retry candidate.
        assert net.is_transient_subprocess_error("Could not resolve host", 0) is False
        assert net.is_transient_subprocess_error("", 1) is False

    def test_http_exception_classification_unwraps_urlerror(self, net) -> None:
        """429/5xx are transient, 404 is not, and URLError defers to its reason."""
        import urllib.error

        assert net.is_transient_http_error(urllib.error.HTTPError(
            "u", 503, "unavailable", {}, None)) is True
        assert net.is_transient_http_error(urllib.error.HTTPError(
            "u", 404, "not found", {}, None)) is False
        assert net.is_transient_http_error(urllib.error.URLError(TimeoutError())) is True
        assert net.is_transient_http_error(urllib.error.URLError(ValueError("nope"))) is False
        assert net.is_transient_http_error(None) is False


class TestRunWithRetry:
    """The retry loop must spend attempts on transients and only on transients."""

    def test_budget_is_spent_on_transients_and_only_on_transients(
        self, net, tmp_path: Path
    ) -> None:
        """A transient child is re-run max_attempts times; a permanent one runs once."""
        transient_counter = tmp_path / "transient.count"
        with pytest.raises(subprocess.CalledProcessError):
            net.run_with_retry(
                _flaky_cmd(tmp_path, transient_counter,
                           "fatal: Could not resolve host: github.com"),
                max_attempts=3, backoff=0.0, timeout=30,
            )
        assert transient_counter.read_text().count("run") == 3

        permanent_counter = tmp_path / "permanent.count"
        result = net.run_with_retry(
            _flaky_cmd(tmp_path, permanent_counter,
                       "remote: Authentication failed for repo"),
            check=False, max_attempts=30, backoff=0.0, timeout=30,
        )
        assert result.returncode == 1
        assert permanent_counter.read_text().count("run") == 1


class TestCliWrappers:
    """gh/git wrappers must inject their documented environment and config."""

    def test_gh_wrapper_defaults_http_timeout_but_respects_an_explicit_one(
        self, net, tmp_path: Path
    ) -> None:
        """GH_HTTP_TIMEOUT is set when absent and left alone when the caller set it."""
        script = tmp_path / "echo_env.py"
        script.write_text(
            "import os, sys\nsys.stdout.write(os.environ.get('GH_HTTP_TIMEOUT', 'UNSET'))\n",
            encoding="utf-8",
        )
        cmd = [sys.executable, str(script)]

        defaulted = net.gh_with_retry(cmd, max_attempts=1, timeout=30)
        assert defaulted.stdout.strip() == str(net.GH_HTTP_TIMEOUT_SEC)

        explicit = net.gh_with_retry(
            cmd, env={"GH_HTTP_TIMEOUT": "7", "PATH": "/usr/bin:/bin"},
            max_attempts=1, timeout=30,
        )
        assert explicit.stdout.strip() == "7"

    def test_git_wrapper_injects_slow_transfer_config_and_rejects_foreign_commands(
        self, net, tmp_path: Path
    ) -> None:
        """`-c http.lowSpeed*` really reaches git; a non-git argv is refused up front."""
        result = net.git_with_retry(
            ["git", "config", "--get", "http.lowSpeedLimit"],
            cwd=str(tmp_path), check=False, max_attempts=1, timeout=30,
        )
        assert result.stdout.strip() == str(net.GIT_LOW_SPEED_LIMIT)

        with pytest.raises(ValueError):
            net.git_with_retry(["gh", "repo", "view"], max_attempts=1)
